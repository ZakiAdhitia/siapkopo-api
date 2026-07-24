"""Letter template service: template CRUD, field CRUD, and reordering."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.letter_template import LetterTemplate, TemplateField
from app.repositories.base import BaseRepository

logger = get_logger("letter_template")


class LetterTemplateService:
    """CRUD orchestration for LetterTemplate and its TemplateField rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, LetterTemplate)
        self.field_repo = BaseRepository(session, TemplateField)

    async def create(self, data: dict[str, Any]) -> LetterTemplate:
        """Create a new letter template (no fields yet)."""
        obj = await self.repo.create(**data)
        await self.session.commit()
        logger.info("LetterTemplate created id=%s code=%s", obj.id, obj.code)
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> LetterTemplate:
        """Return the template with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("Template surat tidak ditemukan")
        return obj

    async def list(
        self, page: int = 1, size: int = 20,
        is_active: bool | None = None, search: str | None = None,
    ) -> tuple[list[LetterTemplate], int]:
        """Return a page of templates, optionally filtered by active flag and name search."""
        search_tuple = ([LetterTemplate.name], search) if search else None
        return await self.repo.list(
            page=page, size=size, filters={"is_active": is_active}, search=search_tuple
        )

    async def update(self, id_: uuid.UUID, data: dict[str, Any]) -> LetterTemplate:
        """Update a template's metadata."""
        obj = await self.get_or_404(id_)
        obj = await self.repo.update(obj, **data)
        await self.session.commit()
        logger.info("LetterTemplate updated id=%s", id_)
        return obj

    async def delete(self, id_: uuid.UUID) -> None:
        """Soft-delete a template."""
        obj = await self.get_or_404(id_)
        await self.repo.soft_delete(obj)
        await self.session.commit()
        logger.info("LetterTemplate deleted id=%s", id_)

    async def list_fields(self, template_id: uuid.UUID) -> list[TemplateField]:
        """Return all non-deleted fields of a template, ordered by order_index."""
        await self.get_or_404(template_id)
        stmt = (
            select(TemplateField)
            .where(TemplateField.template_id == template_id, TemplateField.deleted_at.is_(None))
            .order_by(TemplateField.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_field(self, template_id: uuid.UUID, data: dict[str, Any]) -> TemplateField:
        """Add a new field to a template, appended at the end of the order."""
        await self.get_or_404(template_id)
        existing = await self.list_fields(template_id)
        next_order = max((f.order_index for f in existing), default=-1) + 1
        obj = await self.field_repo.create(template_id=template_id, order_index=next_order, **data)
        await self.session.commit()
        logger.info("TemplateField created id=%s template_id=%s", obj.id, template_id)
        return obj

    async def get_field_or_404(self, template_id: uuid.UUID, field_id: uuid.UUID) -> TemplateField:
        """Return a field scoped to its template, or raise NotFoundError."""
        obj = await self.field_repo.get(field_id)
        if obj is None or obj.template_id != template_id:
            raise NotFoundError("Field template tidak ditemukan")
        return obj

    async def update_field(
        self, template_id: uuid.UUID, field_id: uuid.UUID, data: dict[str, Any]
    ) -> TemplateField:
        """Update a single field's metadata.

        ``field_key`` is never written here even if present in ``data`` — it
        is immutable after creation (referenced by future submission data and
        by PDF placeholders). The API schema already omits it; this is a
        service-layer backstop for any other caller.
        """
        obj = await self.get_field_or_404(template_id, field_id)
        data = {k: v for k, v in data.items() if k != "field_key"}
        obj = await self.field_repo.update(obj, **data)
        await self.session.commit()
        logger.info("TemplateField updated id=%s", field_id)
        return obj

    async def delete_field(self, template_id: uuid.UUID, field_id: uuid.UUID) -> None:
        """Soft-delete a single field."""
        obj = await self.get_field_or_404(template_id, field_id)
        await self.field_repo.soft_delete(obj)
        await self.session.commit()
        logger.info("TemplateField deleted id=%s", field_id)

    async def reorder_fields(
        self, template_id: uuid.UUID, field_ids: list[uuid.UUID]
    ) -> list[TemplateField]:
        """Rewrite order_index for all of a template's fields from a full ordered id list.

        ``field_ids`` must exactly match the set of the template's current
        non-deleted field ids (no missing, no extra, no duplicates) — this
        keeps ordering consistent without a DB-level unique constraint on
        order_index, which would risk transient collisions when two fields
        swap positions within the same transaction.
        """
        await self.get_or_404(template_id)
        existing = await self.list_fields(template_id)
        existing_ids = {f.id for f in existing}
        given_ids = set(field_ids)
        if given_ids != existing_ids or len(field_ids) != len(existing_ids):
            raise ValidationAppError(
                "Daftar field harus memuat seluruh field template ini tanpa duplikat"
            )
        by_id = {f.id: f for f in existing}
        for index, fid in enumerate(field_ids):
            by_id[fid].order_index = index
        await self.session.commit()
        logger.info("TemplateField reordered template_id=%s", template_id)
        return await self.list_fields(template_id)
