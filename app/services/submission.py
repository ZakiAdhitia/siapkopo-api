"""Submission service: creation with answer validation against TemplateField."""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.auth import User
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import FamilyCard, Resident
from app.models.submission import Submission, SubmissionStatus, SubmissionStatusHistory, HistoryAction
from app.repositories.base import BaseRepository
from app.services.notification import notify_status_change

logger = get_logger("submission")


class SubmissionService:
    """Business logic for the submission lifecycle: creation and querying.

    Approval/reject/issuance are added to this same class in Task 12.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, Submission)
        self.template_repo = BaseRepository(session, LetterTemplate)

    async def _list_template_fields(self, template_id: uuid.UUID) -> list[TemplateField]:
        stmt = (
            select(TemplateField)
            .where(TemplateField.template_id == template_id, TemplateField.deleted_at.is_(None))
            .order_by(TemplateField.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    def _validate_answers(self, fields: list[TemplateField], answers: dict) -> None:
        """Validate submitted answers against the template's field definitions.

        Collects ALL errors before raising (not just the first) so the
        client can fix everything in one round-trip.
        """
        errors: list[str] = []
        for field in fields:
            value = answers.get(field.field_key)
            is_empty = value is None or value == ""
            if field.is_required and is_empty:
                errors.append(f"{field.label} wajib diisi")
                continue
            if is_empty:
                continue
            if field.field_type == FieldType.SELECT and field.options and value not in field.options:
                errors.append(f"{field.label}: pilihan tidak valid")
            if field.field_type == FieldType.NUMBER:
                try:
                    float(value)
                except (TypeError, ValueError):
                    errors.append(f"{field.label} harus berupa angka")
        if errors:
            raise ValidationAppError("; ".join(errors))

    async def resolve_applicant_data(self, user: User) -> dict:
        """Build {nama, nik, alamat, no_kk} for auto-fill and PDF placeholders.

        Falls back to User fields if the user has no linked Resident (should
        not happen for the seeded demo warga account after Task 15's seed
        link, but keeps this from hard-failing if it ever does).
        """
        fallback = {"nama": user.full_name, "nik": user.nik or "-", "alamat": "-", "no_kk": "-"}
        if user.resident_id is None:
            return fallback
        resident = await self.session.get(Resident, user.resident_id)
        if resident is None:
            return fallback
        kk_number = "-"
        if resident.family_card_id is not None:
            fc = await self.session.get(FamilyCard, resident.family_card_id)
            if fc is not None:
                kk_number = fc.kk_number
        return {
            "nama": resident.full_name, "nik": resident.nik,
            "alamat": resident.address or "-", "no_kk": kk_number,
        }

    async def create(self, user: User, template_id: uuid.UUID, answers: dict[str, Any]) -> Submission:
        """Create a new submission after validating answers against the template."""
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers)

        obj = Submission(
            village_id=template.village_id, template_id=template_id,
            submitted_by_user_id=user.id, answers=answers,
            status=SubmissionStatus.PENDING, current_step_index=0,
        )
        self.session.add(obj)
        await self.session.flush()
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=0, action=HistoryAction.SUBMITTED,
            actor_user_id=user.id, note=None,
        ))
        await self.session.commit()
        logger.info("Submission created id=%s template_id=%s user_id=%s", obj.id, template_id, user.id)
        notify_status_change(obj, "submitted")
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> Submission:
        """Return the submission with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("Pengajuan tidak ditemukan")
        return obj

    async def list(
        self, actor_permissions: list[str], actor_user_id: uuid.UUID,
        page: int = 1, size: int = 20,
    ) -> tuple[list[Submission], int]:
        """List submissions: all rows for staff (submission:read_all/"*"), else own only."""
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        filters = {} if can_read_all else {"submitted_by_user_id": actor_user_id}
        return await self.repo.list(page=page, size=size, filters=filters)
