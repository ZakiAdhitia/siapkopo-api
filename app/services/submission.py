"""Submission service: creation with answer validation against TemplateField."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import or_, select
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
from app.services.master import FamilyCardService, ResidentService, VillageProfileService
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
        """Notify the submission's owner of a status change (Bagian 9).

        Guest submissions (no user account) have no in-app inbox to write
        to -- notify by email directly to the contact address they gave
        instead.
        """
        if obj.submitted_by_user_id is not None:
            await NotificationService(self.session).notify(
                obj.submitted_by_user_id, f"submission:{event}", "Status Pengajuan Surat", message,
            )
        elif obj.guest_contact_email:
            NotificationService(self.session).provider.send_email(
                obj.guest_contact_email, "Status Pengajuan Surat", message,
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

    async def _applicant_data_from_resident(self, resident: Resident) -> dict:
        """Build {nama, nik, alamat, no_kk} directly from a Resident row."""
        kk_number = "-"
        if resident.family_card_id is not None:
            fc = await self.session.get(FamilyCard, resident.family_card_id)
            if fc is not None:
                kk_number = fc.kk_number
        return {
            "nama": resident.full_name, "nik": resident.nik,
            "alamat": resident.address or "-", "no_kk": kk_number,
        }

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
        return await self._applicant_data_from_resident(resident)

    async def resolve_applicant_data_for_submission(self, submission: Submission) -> dict:
        """Like resolve_applicant_data, but for a Submission of any origin:
        a logged-in user's own submission, a guest submission, or a Mode
        Loket walk-in (where submitted_by_user_id is the STAFF, not the
        applicant). applicant_resident_id -- who the letter is actually
        for -- always takes priority when set; a guest submission whose NIK
        wasn't in master data yet falls back to its own pending_applicant_*
        fields (Bagian 5, Master Data rework); only a normal logged-in
        warga submission (neither of the above) falls back to resolving the
        applicant from the submitting user.
        """
        if submission.applicant_resident_id is not None:
            resident = await self.session.get(Resident, submission.applicant_resident_id)
            if resident is None:
                return {"nama": "-", "nik": "-", "alamat": "-", "no_kk": "-"}
            return await self._applicant_data_from_resident(resident)
        if submission.pending_applicant_nik is not None:
            return {
                "nama": submission.pending_applicant_nama or "-",
                "nik": submission.pending_applicant_nik,
                "alamat": submission.pending_applicant_alamat or "-",
                "no_kk": submission.pending_applicant_no_kk or "-",
            }
        if submission.submitted_by_user_id is not None:
            user = await self.session.get(User, submission.submitted_by_user_id)
            return await self.resolve_applicant_data(user)
        return {"nama": "-", "nik": "-", "alamat": "-", "no_kk": "-"}

    async def lookup_applicant_by_nik(self, nik: str) -> dict | None:
        """Public autofill lookup for the guest submission form: exact NIK
        match only, or None if no Resident has that NIK on file."""
        resident = await self.session.scalar(
            select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
        )
        if resident is None:
            return None
        return await self._applicant_data_from_resident(resident)

    async def create(
        self, user: User, template_id: uuid.UUID, answers: dict[str, Any],
        physical_documents_promised: bool = False,
    ) -> Submission:
        """Create a new submission after validating answers against the template."""
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers)

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=user.id, answers=answers,
            physical_documents_promised=physical_documents_promised,
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

    @staticmethod
    def _resolve_required_documents(template: LetterTemplate, answers: dict[str, Any]) -> list[str]:
        """Conditional Sub-Category Form (Bagian 4.2, STRATEGI doc): if the
        template has a category_field_key configured, required documents
        depend on that field's answer (e.g. KK's 5 permohonan categories
        each need different supporting documents). Falls back to the flat
        required_documents list otherwise -- every non-conditional template.
        """
        if template.category_field_key and template.required_documents_by_category:
            category_value = answers.get(template.category_field_key)
            docs = template.required_documents_by_category.get(category_value)
            if docs is not None:
                return docs
        return template.required_documents

    async def _resolve_or_create_resident(
        self, nik: str, applicant_nama: str | None, applicant_alamat: str | None,
    ) -> Resident:
        """Look up a Resident by NIK, auto-creating a minimal row if none
        exists yet -- the "every transaction enriches the population master
        data" pattern Mode Loket uses (Bagian 3.1 STRATEGI doc). Staff has
        already verified the physical KTP/KK in person for a walk-in, so an
        immediate insert is safe -- unlike the guest flow (Bagian 5, Master
        Data rework), which defers this to approval instead; see
        `_lookup_resident_by_nik`.
        """
        resident = await self.session.scalar(
            select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
        )
        if resident is None:
            if not applicant_nama:
                raise ValidationAppError("NIK belum terdaftar, mohon isi nama lengkap pemohon")
            resident = await ResidentService(self.session).create({
                "nik": nik, "full_name": applicant_nama, "address": applicant_alamat,
            })
        return resident

    async def _lookup_resident_by_nik(self, nik: str) -> Resident | None:
        """Read-only NIK lookup -- never writes to master data."""
        return await self.session.scalar(
            select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
        )

    async def create_guest(
        self, template_id: uuid.UUID, nik: str, answers: dict[str, Any], contact_email: str,
        attachments: list[tuple[str, str, bytes, str]],
        applicant_nama: str | None = None, applicant_alamat: str | None = None,
        contact_whatsapp: str | None = None,
    ) -> Submission:
        """Create a submission with no account (Bagian 3.2, STRATEGI doc).

        Looks up the applicant by NIK, but -- unlike Mode Loket -- never
        writes to master data at this point (Bagian 5, Master Data rework):
        a NIK already on file is linked via applicant_resident_id, but an
        unknown NIK is only stored as raw pending_applicant_* fields on the
        submission itself. The actual Resident row (if needed) is only
        created once staff has reviewed and approved the submission (see
        `complete_applicant_data` and `_issue`), preventing unverified guest
        input from polluting the population master data before anyone at
        the village has checked it.

        `attachments` is `[(document_label, filename, content, content_type), ...]`
        -- exactly one file per template.required_documents entry is
        mandatory (Bagian 6, STRATEGI doc rev. 2026-07-26 anti-fraud
        requirement: no more "I'll bring it physically" opt-out for guests),
        each validated for size/mime and checked for blur before anything is
        written to the database.
        """
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers)

        required_docs = set(self._resolve_required_documents(template, answers))
        given_labels = [label for label, _, _, _ in attachments]
        if set(given_labels) != required_docs or len(given_labels) != len(required_docs):
            raise ValidationAppError(
                "Lampiran wajib diunggah lengkap: " + ", ".join(sorted(required_docs))
            )

        storage = FileStorageService()
        for label, _filename, content, content_type in attachments:
            storage.validate_upload(content, content_type)
            storage.check_not_blurry(content, content_type, label)

        resident = await self._lookup_resident_by_nik(nik)
        if resident is None and not applicant_nama:
            raise ValidationAppError("NIK belum terdaftar, mohon isi nama lengkap pemohon")

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=None,
            applicant_resident_id=resident.id if resident else None,
            pending_applicant_nik=None if resident else nik,
            pending_applicant_nama=None if resident else applicant_nama,
            pending_applicant_alamat=None if resident else applicant_alamat,
            guest_contact_email=contact_email, guest_contact_whatsapp=contact_whatsapp,
            answers=answers,
            physical_documents_promised=False,
            status=SubmissionStatus.PENDING, current_step_index=0,
        )
        self.session.add(obj)
        await self.session.flush()
        for label, filename, content, content_type in attachments:
            storage_path = await storage.save(content, filename, subdir="attachments")
            self.session.add(SubmissionAttachment(
                submission_id=obj.id, document_label=label,
                original_filename=filename, stored_filename=storage_path.rsplit("/", 1)[-1],
                content_type=content_type, size_bytes=len(content), storage_path=storage_path,
            ))
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=0, action=HistoryAction.SUBMITTED,
            actor_user_id=None, note=None,
        ))
        await self.session.commit()
        logger.info(
            "Guest submission created id=%s template_id=%s resident_id=%s attachments=%d",
            obj.id, template_id, resident.id if resident else None, len(attachments),
        )
        NotificationService(self.session).provider.send_email(
            contact_email, "Pengajuan Surat Diterima",
            f"Pengajuan Anda telah diterima dan sedang diproses. Nomor Pengajuan: {obj.id}. "
            "Cek status kapan saja dengan NIK, No. WhatsApp, atau Email Anda di halaman Cek Status.",
        )
        return obj

    async def create_walkin(
        self, actor: User, template_id: uuid.UUID, nik: str, answers: dict[str, Any],
        applicant_nama: str | None = None, applicant_alamat: str | None = None,
    ) -> Submission:
        """Mode Loket (Bagian 3.1, STRATEGI doc): staff enters a walk-in
        citizen's request on their behalf and it is issued immediately --
        the citizen already brought physical KTP/KK for the staff to verify
        in person, so the normal approval chain is skipped entirely.
        """
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers)

        resident = await self._resolve_or_create_resident(nik, applicant_nama, applicant_alamat)

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=actor.id, applicant_resident_id=resident.id,
            answers=answers, physical_documents_promised=True,
            status=SubmissionStatus.PENDING, current_step_index=0,
        )
        self.session.add(obj)
        await self.session.flush()
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=0, action=HistoryAction.SUBMITTED,
            actor_user_id=actor.id, note="Diinput via Mode Loket",
        ))
        await self._issue(obj, actor)
        await self.session.commit()
        logger.info(
            "Walk-in submission created & issued id=%s template_id=%s by=%s resident_id=%s",
            obj.id, template_id, actor.id, resident.id,
        )
        return obj

    async def complete_applicant_data(
        self, submission_id: uuid.UUID, no_kk: str | None, rt_id: uuid.UUID | None,
    ) -> Submission:
        """Staff fills in the master-data fields (Bagian 5, Master Data
        rework) a guest didn't provide -- No. KK and/or RT -- from the
        submission detail page. Only stored on the submission for now; the
        actual Resident/FamilyCard rows are created at approval (`_issue`),
        not here.
        """
        obj = await self.get_or_404(submission_id)
        if obj.applicant_resident_id is not None:
            raise ValidationAppError("Pemohon pengajuan ini sudah tercatat di master data")
        if obj.pending_applicant_nik is None:
            raise ValidationAppError("Pengajuan ini tidak memerlukan pelengkapan data pemohon")
        obj.pending_applicant_no_kk = no_kk
        obj.pending_applicant_rt_id = rt_id
        await self.session.commit()
        logger.info("Applicant data completed submission_id=%s", submission_id)
        return obj

    async def search_guest_submissions(
        self, nik: str | None = None, whatsapp: str | None = None, email: str | None = None,
    ) -> list[Submission]:
        """Find every guest/Mode-Loket submission matching NIK, WhatsApp, or
        email (Bagian 8, STRATEGI doc rev. 2026-07-26) -- no tracking number
        required, at least one identifier must be given. Only ever resolves
        submissions with an applicant_resident_id set (guest or walk-in); a
        logged-in user's own submission is never reachable this way.
        """
        conditions = []
        if nik:
            resident = await self.session.scalar(
                select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
            )
            if resident is not None:
                conditions.append(Submission.applicant_resident_id == resident.id)
        if whatsapp:
            conditions.append(Submission.guest_contact_whatsapp == whatsapp)
        if email:
            conditions.append(Submission.guest_contact_email == email)
        if not conditions:
            return []
        stmt = (
            select(Submission)
            .where(or_(*conditions), Submission.deleted_at.is_(None))
            .order_by(Submission.created_at.desc())
        )
        return list((await self.session.scalars(stmt)).all())

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

    async def list_attachments(self, submission_id: uuid.UUID) -> list[SubmissionAttachment]:
        """Return a submission's uploaded supporting documents."""
        stmt = (
            select(SubmissionAttachment)
            .where(
                SubmissionAttachment.submission_id == submission_id,
                SubmissionAttachment.deleted_at.is_(None),
            )
            .order_by(SubmissionAttachment.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def get_attachment_file(
        self, submission_id: uuid.UUID, attachment_id: uuid.UUID,
        actor_user_id: uuid.UUID, actor_permissions: list[str],
    ) -> tuple[bytes, SubmissionAttachment]:
        """Return an attachment's file bytes, enforcing the same ownership/
        read_all scope as the submission it belongs to."""
        await self.get_scoped(submission_id, actor_user_id, actor_permissions)
        attachment = await self.session.scalar(
            select(SubmissionAttachment).where(
                SubmissionAttachment.id == attachment_id,
                SubmissionAttachment.submission_id == submission_id,
                SubmissionAttachment.deleted_at.is_(None),
            )
        )
        if attachment is None:
            raise NotFoundError("Lampiran tidak ditemukan")
        content = await FileStorageService().read(attachment.storage_path)
        return content, attachment

    async def list_history(self, submission_id: uuid.UUID) -> list[SubmissionStatusHistory]:
        """Return a submission's status history, oldest first."""
        await self.get_or_404(submission_id)
        stmt = (
            select(SubmissionStatusHistory)
            .where(SubmissionStatusHistory.submission_id == submission_id)
            .order_by(SubmissionStatusHistory.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def _materialize_pending_resident(self, submission: Submission) -> None:
        """Write a guest submission's applicant to master data for the
        first time, now that it has been approved (Bagian 5, Master Data
        rework). No-op if the applicant was already linked (NIK existed at
        submit time, or this isn't a guest submission at all).

        A No. KK from `complete_applicant_data` resolves/creates the
        matching FamilyCard; RT is optional. Neither is required -- staff
        may approve before finishing that step, and the Resident is still
        created (just without a family_card_id/rt_id yet).
        """
        if submission.applicant_resident_id is not None or submission.pending_applicant_nik is None:
            return
        family_card_id = None
        if submission.pending_applicant_no_kk:
            fc = await self.session.scalar(
                select(FamilyCard).where(FamilyCard.kk_number == submission.pending_applicant_no_kk)
            )
            if fc is None:
                fc = await FamilyCardService(self.session).create({
                    "kk_number": submission.pending_applicant_no_kk,
                })
            family_card_id = fc.id
        resident = await ResidentService(self.session).create({
            "nik": submission.pending_applicant_nik,
            "full_name": submission.pending_applicant_nama,
            "address": submission.pending_applicant_alamat,
            "family_card_id": family_card_id,
            "rt_id": submission.pending_applicant_rt_id,
        })
        submission.applicant_resident_id = resident.id
        submission.pending_applicant_nik = None
        submission.pending_applicant_nama = None
        submission.pending_applicant_alamat = None
        logger.info(
            "Pending applicant materialized into master data submission_id=%s resident_id=%s",
            submission.id, resident.id,
        )

    async def _issue(self, submission: Submission, actor: User) -> None:
        """Allocate a real number, render the final PDF, and mark ISSUED."""
        await self._materialize_pending_resident(submission)
        template = await self.template_repo.get(submission.template_id)
        fields = await self._list_template_fields(submission.template_id)
        village = await VillageProfileService(self.session).get()
        applicant = await self.resolve_applicant_data_for_submission(submission)

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
