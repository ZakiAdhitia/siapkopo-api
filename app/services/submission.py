"""Submission service: creation with answer validation against TemplateField."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.auth import User
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import FamilyCard, Resident
from app.models.submission import (
    HistoryAction,
    Submission,
    SubmissionAttachment,
    SubmissionStatus,
    SubmissionStatusHistory,
)
from app.repositories.base import BaseRepository
from app.services.approval_config import ApprovalStepConfigService
from app.services.file_storage import FileStorageService
from app.services.letter_number import LetterNumberService
from app.services.master import VillageProfileService
from app.services.notification import NotificationService
from app.services.template_render import TemplateRenderService

logger = get_logger("submission")


class SubmissionService:
    """Business logic for the submission lifecycle: creation, querying,
    approval/reject with data-driven turn enforcement, and automatic PDF
    issuance on the final approval step.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, Submission)
        self.template_repo = BaseRepository(session, LetterTemplate)

    async def _notify(self, obj: Submission, event: str, message: str) -> None:
        """Notify the submission's owner of a status change (Bagian 9)."""
        await NotificationService(self.session).notify(
            obj.submitted_by_user_id, f"submission:{event}", "Status Pengajuan Surat", message,
        )

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
            template_id=template_id,
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
        await self._notify(obj, "submitted", "Pengajuan surat Anda telah diterima dan sedang diproses.")
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> Submission:
        """Return the submission with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("Pengajuan tidak ditemukan")
        return obj

    async def get_scoped(
        self, id_: uuid.UUID, actor_user_id: uuid.UUID, actor_permissions: list[str]
    ) -> Submission:
        """Return a submission the actor is allowed to view: their own submission,
        or any submission if they hold submission:read_all or "*".
        """
        obj = await self.get_or_404(id_)
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        if not can_read_all and obj.submitted_by_user_id != actor_user_id:
            raise ForbiddenError("Anda tidak berhak mengakses pengajuan ini")
        return obj

    async def list(
        self, actor_permissions: list[str], actor_user_id: uuid.UUID,
        page: int = 1, size: int = 20,
    ) -> tuple[list[Submission], int]:
        """List submissions: all rows for staff (submission:read_all/"*"), else own only."""
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        filters = {} if can_read_all else {"submitted_by_user_id": actor_user_id}
        return await self.repo.list(page=page, size=size, filters=filters)

    async def add_attachment(
        self, submission_id: uuid.UUID, document_label: str, filename: str,
        content: bytes, content_type: str, actor_user_id: uuid.UUID,
    ) -> SubmissionAttachment:
        """Validate and store an uploaded attachment for a submission.

        Only the submission's own owner may attach documents to it.
        """
        submission = await self.get_or_404(submission_id)
        if submission.submitted_by_user_id != actor_user_id:
            raise ForbiddenError("Anda tidak berhak menambahkan lampiran pada pengajuan ini")
        template = await self.template_repo.get(submission.template_id)
        if template is None or document_label not in template.required_documents:
            raise ValidationAppError(
                f"'{document_label}' bukan lampiran yang diperlukan untuk surat ini"
            )
        storage = FileStorageService()
        storage.validate_upload(content, content_type)
        storage_path = await storage.save(content, filename, subdir="attachments")

        attachment = SubmissionAttachment(
            submission_id=submission_id, document_label=document_label,
            original_filename=filename, stored_filename=storage_path.rsplit("/", 1)[-1],
            content_type=content_type, size_bytes=len(content), storage_path=storage_path,
        )
        self.session.add(attachment)
        await self.session.commit()
        logger.info("Attachment added submission_id=%s label=%s", submission_id, document_label)
        return attachment

    async def list_history(self, submission_id: uuid.UUID) -> list[SubmissionStatusHistory]:
        """Return a submission's status history, oldest first."""
        await self.get_or_404(submission_id)
        stmt = (
            select(SubmissionStatusHistory)
            .where(SubmissionStatusHistory.submission_id == submission_id)
            .order_by(SubmissionStatusHistory.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def _issue(self, submission: Submission, actor: User) -> None:
        """Allocate a real number, render the final PDF, and mark ISSUED."""
        template = await self.template_repo.get(submission.template_id)
        fields = await self._list_template_fields(submission.template_id)
        village = await VillageProfileService(self.session).get()
        submitter = await self.session.get(User, submission.submitted_by_user_id)
        applicant = await self.resolve_applicant_data(submitter)

        year = datetime.now(timezone.utc).year
        seq = await LetterNumberService(self.session).allocate(submission.template_id, year)
        letter_number = template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=seq, year=year
        )
        tanggal = datetime.now(timezone.utc).strftime("%d %B %Y")

        pdf_bytes = TemplateRenderService().render_issued(
            template=template, fields=fields, profile=village,
            answers=submission.answers, applicant=applicant, nomor=letter_number,
            tanggal=tanggal,
        )
        storage_path = await FileStorageService().save(
            pdf_bytes, f"{submission.id}.pdf", subdir="issued"
        )

        submission.status = SubmissionStatus.ISSUED
        submission.letter_number = letter_number
        submission.pdf_storage_path = storage_path
        submission.issued_at = datetime.now(timezone.utc)
        self.session.add(SubmissionStatusHistory(
            submission_id=submission.id, step_index=submission.current_step_index,
            action=HistoryAction.ISSUED, actor_user_id=actor.id, note=None,
        ))
        logger.info(
            "Submission issued id=%s letter_number=%s", submission.id, letter_number,
        )

    async def approve(
        self, submission_id: uuid.UUID, actor: User, note: str | None
    ) -> Submission:
        """Advance a submission one step, or issue it if this was the final step."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")
        steps = await ApprovalStepConfigService(self.session).list_steps()
        if not steps:
            raise ValidationAppError("Alur persetujuan desa belum dikonfigurasi")
        current_step = steps[obj.current_step_index]
        if current_step.role_id != actor.role_id:
            raise ForbiddenError("Bukan giliran Anda untuk memproses pengajuan ini")

        is_last_step = obj.current_step_index == len(steps) - 1
        if is_last_step:
            await self._issue(obj, actor)
        else:
            obj.current_step_index += 1
            self.session.add(SubmissionStatusHistory(
                submission_id=obj.id, step_index=obj.current_step_index,
                action=HistoryAction.APPROVED, actor_user_id=actor.id, note=note,
            ))
        await self.session.commit()
        logger.info("Submission approve processed id=%s by=%s", obj.id, actor.id)
        if is_last_step:
            await self._notify(obj, "issued", "Surat Anda telah terbit dan siap diambil di kantor desa.")
        else:
            await self._notify(
                obj, "approved",
                "Pengajuan surat Anda disetujui pada tahap ini dan lanjut ke tahap berikutnya.",
            )
        return obj

    async def reject(self, submission_id: uuid.UUID, actor: User, reason: str) -> Submission:
        """Reject a submission (terminal) with a mandatory reason."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")
        steps = await ApprovalStepConfigService(self.session).list_steps()
        if not steps:
            raise ValidationAppError("Alur persetujuan desa belum dikonfigurasi")
        current_step = steps[obj.current_step_index]
        if current_step.role_id != actor.role_id:
            raise ForbiddenError("Bukan giliran Anda untuk memproses pengajuan ini")

        obj.status = SubmissionStatus.REJECTED
        obj.rejection_reason = reason
        obj.rejected_by_user_id = actor.id
        obj.rejected_at = datetime.now(timezone.utc)
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=obj.current_step_index,
            action=HistoryAction.REJECTED, actor_user_id=actor.id, note=reason,
        ))
        await self.session.commit()
        logger.info("Submission rejected id=%s by=%s", obj.id, actor.id)
        await self._notify(obj, "rejected", f"Pengajuan surat Anda ditolak. Alasan: {reason}")
        return obj

    async def download_pdf(
        self, submission_id: uuid.UUID, actor_user_id: uuid.UUID, actor_permissions: list[str]
    ) -> bytes:
        """Return the issued PDF's bytes, enforcing ownership or read_all."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.ISSUED or obj.pdf_storage_path is None:
            raise ValidationAppError("Surat belum terbit")
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        if not can_read_all and obj.submitted_by_user_id != actor_user_id:
            raise ForbiddenError("Anda tidak berhak mengunduh surat ini")
        return await FileStorageService().read(obj.pdf_storage_path)
