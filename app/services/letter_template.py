"""Letter template service: template CRUD, field CRUD, and reordering."""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
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
