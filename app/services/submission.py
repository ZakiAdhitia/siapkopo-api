"""Submission service: creation with answer validation against TemplateField."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.auth import User
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import RT, RW
from app.models.submission import (
    HistoryAction,
    Submission,
    SubmissionAttachment,
    SubmissionStatus,
    SubmissionStatusHistory,
)
from app.repositories.base import BaseRepository
from app.services.audit_log import AuditLogService
from app.services.domain_master import (
    REQUIRED_STAFF_FIELDS_BY_JENIS,
    TEMPLATE_CODE_TO_JENIS,
    _flatten_extra_data,
)
from app.services.file_storage import FileStorageService
from app.services.letter_template import _HIDDEN_TEMPLATE_CODES
from app.services.master import VillageProfileService
from app.services.notification import LoggingNotificationProvider
from app.services.template_render import TemplateFileService, TemplateRenderService, format_tanggal_indonesia
from app.services.template_render.service import _hari_indonesia

logger = get_logger("submission")

# Fixed number of approve() calls (by anyone holding submission:approve) a
# submission needs before it's issued -- previously a DB-configured,
# role-gated chain (`approval_step_configs`); simplified to a plain
# constant, no more per-step role restriction.
APPROVAL_STEP_COUNT = 2


class SubmissionService:
    """Business logic for the submission lifecycle: creation, querying,
    approval/reject, and automatic PDF issuance on the final approval step.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, Submission)
        self.template_repo = BaseRepository(session, LetterTemplate)

    async def _notify(
        self, obj: Submission, event: str, message: str,
        attachment: tuple[str, bytes] | None = None,
    ) -> None:
        """Email a guest submission's contact address about a status
        change, optionally with the issued letter PDF attached (e.g. on the
        "issued" event -- MASTER_COLUMN_LETTERS.md item 8's "kirim ketika
        surat sudah siap dan sudah di approve"). Submissions from a logged-in
        account have no email sent -- they check "Status Pengajuan" in the
        app themselves (the in-app notification inbox this used to also
        write to has been removed)."""
        if obj.guest_contact_email:
            LoggingNotificationProvider().send_email(
                obj.guest_contact_email, "Status Pengajuan Surat", message, attachment=attachment,
            )

    async def _list_template_fields(self, template_id: uuid.UUID) -> list[TemplateField]:
        stmt = (
            select(TemplateField)
            .where(TemplateField.template_id == template_id, TemplateField.deleted_at.is_(None))
            .order_by(TemplateField.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    _NIK_RE = re.compile(r"^\d{16}$")
    _RT_RW_RE = re.compile(r"^\d{1,3}$")
    # Fields that legitimately hold the applicant's OWN nik/name -- never
    # compared against themselves in the "harus berbeda dari pemohon" checks.
    _SELF_KEYS = {"nik", "nama"}

    @staticmethod
    def _field_visible(field: TemplateField, answers: dict) -> bool:
        """A field is only shown to (and required from) the applicant when
        its `validation_rules.show_when` condition (if any) is satisfied --
        e.g. NA's "jika Duda/Janda" group is hidden and not required for a
        Jejaka/Perawan applicant. `validation_rules` is otherwise unused
        metadata on TemplateField, repurposed here for this one purpose."""
        rules = field.validation_rules or {}
        show_when = rules.get("show_when")
        if not show_when:
            return True
        return answers.get(show_when["field"]) in show_when.get("in", [])

    def _validate_answers(
        self, fields: list[TemplateField], answers: dict, applicant: dict | None = None,
    ) -> None:
        """Validate submitted answers against the template's field definitions.

        Collects ALL errors before raising (not just the first) so the
        client can fix everything in one round-trip. Beyond required/select-
        choice/number checks, also enforces (HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md):
        conditionally-required fields stay required only while visible, NIK-
        shaped fields must be 16 digits, RT/RW-shaped fields must be numeric,
        birth-date fields can't be today/future, and third-party NIK/name
        fields (ayah/ibu/pasangan) can't equal the applicant's own.
        """
        errors: list[str] = []
        applicant_nik = (applicant or {}).get("nik")
        applicant_nama = (applicant or {}).get("nama")
        for field in fields:
            key = field.field_key
            visible = self._field_visible(field, answers)
            value = answers.get(key)
            is_empty = value is None or value == ""
            if not visible:
                continue
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
            if "nik" in key and field.field_type == FieldType.TEXT:
                text_value = str(value).strip()
                if not self._NIK_RE.match(text_value):
                    errors.append(f"{field.label} harus berupa 16 digit angka")
                elif key not in self._SELF_KEYS and applicant_nik and text_value == applicant_nik:
                    errors.append(f"{field.label} tidak boleh sama dengan NIK pemohon")
            if (key == "rt" or key.startswith("rt_") or key == "rw" or key.startswith("rw_")) \
                    and field.field_type == FieldType.TEXT and not self._RT_RW_RE.match(str(value).strip()):
                errors.append(f"{field.label} harus berupa angka (mis. 01)")
            if field.field_type == FieldType.DATE and "meninggal" not in key \
                    and ("tanggal_lahir" in key or "tgl_lahir" in key):
                parsed = self._parse_date(value)
                if parsed and parsed >= date.today():
                    errors.append(f"{field.label} tidak boleh hari ini atau di masa depan")
            if key not in self._SELF_KEYS and key in ("nama_ayah", "nama_ibu", "nama_pasangan") \
                    and applicant_nama and str(value).strip().lower() == applicant_nama.strip().lower():
                errors.append(f"{field.label} tidak boleh sama dengan nama pemohon")
        if errors:
            raise ValidationAppError("; ".join(errors))

    async def build_applicant_snapshot(self, submission: Submission) -> dict:
        """Build the shared {nama, nik, alamat, no_kk, jk, tempat_lahir,
        tanggal_lahir, pekerjaan, status_kawin, rt, rw, rt_id} block every
        PDF template and domain-master row reads (SYARAT-PENGAJUAN-SURAT.md's
        "Field yang identik di semua surat"), plus (2026-08-08, Fase 1 of
        ALUR_REVIEW_INPUT_MASTER.md) the flattened letter-specific staff
        sesi data from `staff_extra_data` for jenis that have it (Domisili's
        alamat asal, NA's ayah/ibu/CSI, Kematian's almarhum, Kelahiran's
        ayah/ibu) -- see domain_master._flatten_extra_data. Both blocks are
        staff-entered via PUT .../master-data and PUT .../extra-data
        respectively; nama/nik are fixed on the submission itself at
        creation time.
        """
        draft = submission.staff_master_data or {}
        rt_id = draft.get("rt_id")
        rt_number, rw_number = None, None
        if rt_id:
            rt = await self.session.get(RT, rt_id)
            if rt is not None:
                rt_number = rt.number
                rw = await self.session.get(RW, rt.rw_id)
                if rw is not None:
                    rw_number = rw.number
        snapshot = {
            "nama": submission.applicant_nama, "nik": submission.applicant_nik,
            "alamat": draft.get("alamat") or "-", "no_kk": draft.get("no_kk") or "-",
            "jk": draft.get("jk"), "tempat_lahir": draft.get("tempat_lahir"),
            "tanggal_lahir": draft.get("tanggal_lahir"), "pekerjaan": draft.get("pekerjaan"),
            "status_kawin": draft.get("status_kawin"), "rt": rt_number, "rw": rw_number,
            "rt_id": rt_id,
        }
        template = await self.template_repo.get(submission.template_id)
        jenis = TEMPLATE_CODE_TO_JENIS.get(template.code.lower()) if template else None
        if jenis:
            snapshot.update(_flatten_extra_data(jenis, submission.staff_extra_data or {}))
        return snapshot

    async def create(
        self, user: User, template_id: uuid.UUID, answers: dict[str, Any],
        applicant_nik: str, applicant_nama: str,
        physical_documents_promised: bool = False,
    ) -> Submission:
        """Create a new submission after validating answers against the template."""
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active or template.code in _HIDDEN_TEMPLATE_CODES:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers, {"nik": applicant_nik, "nama": applicant_nama})

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=user.id, answers=answers,
            applicant_nik=applicant_nik, applicant_nama=applicant_nama,
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


    async def create_guest(
        self, template_id: uuid.UUID, applicant_nik: str, applicant_nama: str,
        answers: dict[str, Any], contact_whatsapp: str,
        attachments: list[tuple[str, str, bytes, str]],
        contact_email: str | None = None,
    ) -> Submission:
        """Create a submission with no account (Bagian 3.2, STRATEGI doc).

        2026-08-06: the applicant is just nik+nama, stored directly on the
        submission -- no Resident lookup/materialization of any kind
        (SISTEM_PENGOLAHAN_DATA_WARGA.md: a persistent population registry
        couldn't be kept up to date, so it's gone; no more NIK autofill
        anywhere either). Everything else about "who this letter is for"
        (alamat/RT/jk/TTL/pekerjaan/status/no_kk) is now staff-entered from
        KTP/KK photo attachments via PUT .../master-data on the detail page,
        not asked of the citizen at submission time.

        `attachments` is `[(document_label, filename, content, content_type), ...]`
        -- exactly one file per template.required_documents entry is
        mandatory (Bagian 6, STRATEGI doc rev. 2026-07-26 anti-fraud
        requirement: no more "I'll bring it physically" opt-out for guests).
        A label from template.optional_documents ("(Bila Ada)" attachments,
        PERBAIKAN_INPUT_DAN_LAMPIRAN_SURAT.MD) may be included or omitted
        freely -- never required, never rejected as unrecognized. Every
        given file is validated for size/mime and checked for blur before
        anything is written to the database.
        """
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active or template.code in _HIDDEN_TEMPLATE_CODES:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers, {"nik": applicant_nik, "nama": applicant_nama})

        required_docs = set(self._resolve_required_documents(template, answers))
        optional_docs = set(template.optional_documents)
        given_labels = [label for label, _, _, _ in attachments]
        given_set = set(given_labels)
        missing = required_docs - given_set
        unknown = given_set - required_docs - optional_docs
        if missing or unknown or len(given_labels) != len(given_set):
            if missing:
                raise ValidationAppError(
                    "Lampiran wajib diunggah lengkap: " + ", ".join(sorted(required_docs))
                )
            raise ValidationAppError(
                "Lampiran tidak dikenali: " + ", ".join(sorted(unknown or given_set))
            )

        storage = FileStorageService()
        for label, _filename, content, content_type in attachments:
            storage.validate_upload(content, content_type)
            storage.check_not_blurry(content, content_type, label)

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=None,
            applicant_nik=applicant_nik, applicant_nama=applicant_nama,
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
            "Guest submission created id=%s template_id=%s attachments=%d",
            obj.id, template_id, len(attachments),
        )
        if contact_email:
            LoggingNotificationProvider().send_email(
                contact_email, "Pengajuan Surat Diterima",
                "Pengajuan Anda telah diterima dan sedang diproses. "
                "Cek status kapan saja dengan NIK, No. WhatsApp, atau Email Anda di halaman Cek Status.",
            )
        return obj

    async def create_walkin(
        self, actor: User, template_id: uuid.UUID, applicant_nik: str, applicant_nama: str,
        answers: dict[str, Any], master_data: dict[str, Any] | None = None,
    ) -> Submission:
        """Mode Loket (Bagian 3.1, STRATEGI doc): staff enters a walk-in
        citizen's request on their behalf and it is issued immediately --
        the citizen already brought physical KTP/KK for the staff to verify
        in person, so the normal approval chain is skipped entirely.

        `master_data` is the same shape as `SubmissionMasterDataUpdateRequest`
        -- filled in inline here (best-effort, not blocking) since a
        walk-in letter issues immediately and has no later detail-page step
        to fill it in at, unlike a normal submission's Approve gate.
        """
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active or template.code in _HIDDEN_TEMPLATE_CODES:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers, {"nik": applicant_nik, "nama": applicant_nama})

        obj = Submission(
            template_id=template_id,
            submitted_by_user_id=actor.id,
            applicant_nik=applicant_nik, applicant_nama=applicant_nama,
            staff_master_data=master_data,
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
            "Walk-in submission created & issued id=%s template_id=%s by=%s",
            obj.id, template_id, actor.id,
        )
        return obj

    async def update_answers(self, submission_id: uuid.UUID, answers: dict[str, Any]) -> Submission:
        """Staff correction of the citizen's own submitted form data ("Data
        Formulir") from the detail page -- e.g. a typo the citizen made, or
        a value staff needs to align with what's on their physical KTP/KK.
        Allowed while pending, or after issuance (2026-08-04: approval is
        single-step now, so there's no longer a review window between
        approve and issue -- staff fix the frozen letter's data here, then
        use `regenerate_pdf` to refresh the PDF; still blocked once
        rejected). Re-validated against the template's own field rules
        exactly like a fresh submission would be.
        """
        obj = await self.get_or_404(submission_id)
        if obj.status not in (SubmissionStatus.PENDING, SubmissionStatus.ISSUED):
            raise ValidationAppError("Data formulir tidak bisa diedit untuk pengajuan yang ditolak")
        fields = await self._list_template_fields(obj.template_id)
        applicant = await self.build_applicant_snapshot(obj)
        self._validate_answers(fields, answers, applicant)
        obj.answers = answers
        await self.session.commit()
        logger.info("Submission answers updated by staff submission_id=%s", submission_id)
        return obj

    async def update_master_data(self, submission_id: uuid.UUID, data: dict[str, Any]) -> Submission:
        """Staff fills in the shared identity block (alamat/RT/jk/tempat_
        lahir/tanggal_lahir/pekerjaan/status_kawin/no_kk) from the citizen's
        KTP/KK photo attachments -- what feeds the per-letter-type domain-
        master table at issuance (`_build_domain_master_fields`) and blocks
        Approve until complete for letter types that need it
        (`get_missing_staff_fields`, `REQUIRED_STAFF_FIELDS_BY_JENIS`).
        Full-replace semantics, same convention as `update_answers`.
        """
        obj = await self.get_or_404(submission_id)
        if obj.status not in (SubmissionStatus.PENDING, SubmissionStatus.ISSUED):
            raise ValidationAppError("Data master tidak bisa diedit untuk pengajuan yang ditolak")
        obj.staff_master_data = data
        await self.session.commit()
        logger.info("Submission master data updated submission_id=%s", submission_id)
        return obj

    async def search_guest_submissions(self, nik: str) -> list[Submission]:
        """Find every guest/Mode-Loket submission matching the given NIK."""
        stmt = (
            select(Submission)
            .where(Submission.applicant_nik == nik, Submission.deleted_at.is_(None))
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
        if template is None or (
            document_label not in template.required_documents
            and document_label not in template.optional_documents
        ):
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

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """Parse a form answer's date value ("YYYY-MM-DD" from an HTML date
        input) into a real `date` -- Date-typed columns need an actual date
        object, not a raw string, when assigned through the ORM."""
        if not value:
            return None
        if isinstance(value, date):
            return value
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    @staticmethod
    def _add_months(start: date, months: int) -> date:
        """Add a whole number of months to a date, clamping the day if the
        target month is shorter (e.g. 31 Jan + 1 month -> 28/29 Feb)."""
        import calendar
        month_index = start.month - 1 + months
        year = start.year + month_index // 12
        month = month_index % 12 + 1
        day = min(start.day, calendar.monthrange(year, month)[1])
        return date(year, month, day)

    def _compute_berlaku(self, issued_date: date, masa_berlaku_bulan: Any) -> date | None:
        """Domisili's "valid until" date: issued_date + the chosen duration
        ("1 Bulan"/"2 Bulan"/...). Computed once in _issue() and reused for
        both the PDF body and the MasterDomisili row so they never disagree."""
        try:
            months = int(str(masa_berlaku_bulan or "").split()[0])
            return self._add_months(issued_date, months)
        except (ValueError, IndexError):
            return None

    @classmethod
    def _combine_ttl(cls, tempat: Any, tanggal: Any) -> str | None:
        """Combine a place + a date answer into one "Tempat, DD Bulan YYYY"
        string -- MASTER_COLUMN_LETTERS.md's tables mostly store a single
        "TTL" (tempat tanggal lahir) column, matching the real Excel sheets'
        single combined cell, rather than the two separately-typed form
        answers this app collects (which stay split so the date stays a real
        date for validation)."""
        parsed = cls._parse_date(tanggal)
        tgl_str = format_tanggal_indonesia(parsed) if parsed else None
        tempat = tempat or None
        if tempat and tgl_str:
            return f"{tempat}, {tgl_str}"
        return tempat or tgl_str

    @staticmethod
    def _weekday_indonesia(value: Any) -> str | None:
        """ISO date (string or `date`) -> Indonesian weekday name, or None."""
        if value is None:
            return None
        iso = value.isoformat() if isinstance(value, date) else str(value)
        name = _hari_indonesia(iso)
        return name if name != "-" else None

    @staticmethod
    def _persyaratan_text(template: LetterTemplate) -> str | None:
        """Comma-joined required + optional document labels, matching the
        real sheets' free-text "PERSYARATAN" column. Optional labels already
        carry their own "(Bila Ada)" marker in the label text itself."""
        docs = list(template.required_documents) + list(template.optional_documents)
        return ", ".join(docs) if docs else None

    @staticmethod
    def _pindah_anggota_summary(answers: dict[str, Any]) -> str | None:
        """Rebuild the old free-text "Nama - NIK - SHDK, satu per baris"
        summary from the numbered anggota_<n>_{nik,nama,shdk} fields
        (06/08/2026: replaced the single free-text daftar_anggota_pindah
        answer with N structured sub-forms -- MasterPindah's own column is
        unchanged, only its source). 7 is _PINDAH_MAX_ANGGOTA in
        app/seed/letter_template_data.py -- keep in sync if that changes.
        """
        lines = []
        for n in range(1, 8):
            nama = answers.get(f"anggota_{n}_nama")
            if not nama:
                continue
            nik = answers.get(f"anggota_{n}_nik") or "-"
            shdk = answers.get(f"anggota_{n}_shdk") or "-"
            lines.append(f"{nama} - {nik} - {shdk}")
        return "\n".join(lines) if lines else None

    async def _save_to_domain_master(
        self, submission: Submission, template: LetterTemplate, applicant: dict,
        berlaku_date: date | None = None,
    ) -> None:
        """Save submission data to domain-specific master tables upon final
        approval. Column shapes follow MASTER_COLUMN_LETTERS.md exactly (see
        app/models/master.py's module docstring) -- the shared applicant
        snapshot (nama/nik/jk/ttl/pekerjaan/status/alamat/rt/rw) covers the
        identity block every table repeats; only the letter-specific extra
        fields come from the submission's own answers.
        """
        from app.models.master import (
            MasterDomisili, MasterKelahiran, MasterKematian, MasterKK, MasterNA,
            MasterPindah, MasterSKU, MasterUbahData, MasterUHC,
        )
        answers = submission.answers or {}
        code = template.code.lower()
        issued_date = submission.issued_at.date() if submission.issued_at else datetime.now(timezone.utc).date()
        applicant_ttl = self._combine_ttl(applicant.get("tempat_lahir"), applicant.get("tanggal_lahir"))

        if code == "domisili":
            berlaku = berlaku_date or self._compute_berlaku(issued_date, answers.get("masa_berlaku_bulan"))
            self.session.add(MasterDomisili(
                tgl_surat=issued_date,
                nama=applicant.get("nama", "-"),
                jk=applicant.get("jk"),
                ttl=applicant_ttl,
                pkj=applicant.get("pekerjaan"),
                status=applicant.get("status_kawin"),
                nik=applicant.get("nik", "-"),
                almt_asal=answers.get("alamat_asal"),
                rt_asal=answers.get("rt_asal"), rw_asal=answers.get("rw_asal"),
                kelurahan_atau_desa_asal=answers.get("kel_desa_asal"), kecamatan_asal=answers.get("kec_asal"),
                kabupaten_atau_kota_asal=answers.get("kab_kota_asal"), provinsi_asal=answers.get("provinsi_asal"),
                almt_domisili=answers.get("alamat_domisili"),
                rt_domisili=answers.get("rt_domisili"), rw_domisili=answers.get("rw_domisili"),
                persyaratan=self._persyaratan_text(template),
                berlaku=berlaku,
                submission_id=submission.id,
            ))
        elif code == "lahir":
            tgl_lahir_anak = answers.get("tgl_lahir_anak")
            self.session.add(MasterKelahiran(
                jk=answers.get("gender_anak"),
                nama_anak=answers.get("nama_anak", "Anak"),
                anak_ke=answers.get("anak_ke"),
                lahir_hari=self._weekday_indonesia(tgl_lahir_anak),
                tempat_lahir=answers.get("tempat_lahir_anak"),
                ttl_anak=self._combine_ttl(answers.get("tempat_lahir_anak"), tgl_lahir_anak),
                jam_lahir=answers.get("jam_lahir_anak"),
                nama_ayah=answers.get("nama_ayah"),
                ttl_ayah=self._combine_ttl(answers.get("tempat_lahir_ayah"), answers.get("tanggal_lahir_ayah")),
                pkj_ayah=answers.get("pekerjaan_ayah"),
                nik_ayah=answers.get("nik_ayah"),
                almt_ayah=answers.get("alamat_ayah"),
                rt_almt_ayah=answers.get("rt_ayah"), rw_almt_ayah=answers.get("rw_ayah"),
                nama_ibu=answers.get("nama_ibu"),
                ttl_ibu=self._combine_ttl(answers.get("tempat_lahir_ibu"), answers.get("tanggal_lahir_ibu")),
                pkj_ibu=answers.get("pekerjaan_ibu"),
                nik_ibu=answers.get("nik_ibu"),
                almt_ibu=answers.get("alamat_ibu"),
                rt_almt_ibu=answers.get("rt_ibu"), rw_almt_ibu=answers.get("rw_ibu"),
                tgl_surat=issued_date,
                submission_id=submission.id,
            ))
        elif code == "mati":
            usia = answers.get("usia_tahun")
            tgl_meninggal = answers.get("tgl_meninggal")
            self.session.add(MasterKematian(
                tgl_surat=issued_date,
                nama=answers.get("nama_almarhum", "Almarhum"),
                jk=answers.get("jk_almarhum"),
                nik=answers.get("nik_almarhum", "-"),
                usia=str(usia) if usia not in (None, "") else None,
                pkj=answers.get("pekerjaan_almarhum"),
                almt=answers.get("alamat_almarhum"),
                rt=answers.get("rt_almarhum"), rw=answers.get("rw_almarhum"),
                hari=self._weekday_indonesia(tgl_meninggal),
                tgl_meninggal=self._parse_date(tgl_meninggal),
                jam=answers.get("jam_meninggal"),
                lokasi_meninggal=answers.get("tempat_meninggal"),
                alasan_meninggal=answers.get("sebab_meninggal"),
                submission_id=submission.id,
            ))
        elif code == "usaha":
            self.session.add(MasterSKU(
                nama=applicant.get("nama", "-"),
                nik=applicant.get("nik", "-"),
                ttl=applicant_ttl,
                jk=applicant.get("jk"),
                pkj=applicant.get("pekerjaan"),
                status=applicant.get("status_kawin"),
                alamat=applicant.get("alamat"),
                rt=applicant.get("rt"), rw=applicant.get("rw"),
                jenis_usaha=answers.get("jenis_usaha", "Usaha Warga"),
                lokasi_usaha=answers.get("lokasi_usaha"),
                rt_lokasi_usaha=answers.get("rt_usaha"), rw_lokasi_usaha=answers.get("rw_usaha"),
                desa=answers.get("desa_usaha"),
                persyaratan=self._persyaratan_text(template),
                tgl_surat=issued_date,
                submission_id=submission.id,
            ))
        elif code == "na":
            jk_calon = answers.get("jk_calon")
            status_calon = answers.get("status_calon")
            is_perempuan = str(jk_calon or "").strip().lower().startswith("p")
            self.session.add(MasterNA(
                tgl_surat=issued_date,
                nama=applicant.get("nama", "-"),
                nik=applicant.get("nik", "-"),
                jk=jk_calon,
                ttl=self._combine_ttl(answers.get("tempat_lahir_calon"), answers.get("tanggal_lahir_calon")),
                kewarganegaraan=answers.get("kewarganegaraan"),
                agama=answers.get("agama_calon"),
                pkj=answers.get("pekerjaan_calon"),
                almt=answers.get("alamat_calon"),
                rt=answers.get("rt_calon"), rw=answers.get("rw_calon"),
                janda_atau_duda=status_calon if not is_perempuan else None,
                jumlah_istri=answers.get("jumlah_istri"),
                perawan_atau_janda=status_calon if is_perempuan else None,
                nomor_akta_cerai=answers.get("no_akta_cerai"),
                suami_atau_istri_terdahulu=answers.get("pasangan_terdahulu"),
                ayah=answers.get("nama_ayah"),
                nik_ayah=answers.get("nik_ayah"),
                ttl_ayah=self._combine_ttl(answers.get("tempat_lahir_ayah"), answers.get("tanggal_lahir_ayah")),
                pkj_ayah=answers.get("pekerjaan_ayah"),
                almt_ayah=answers.get("alamat_ayah"),
                rt_almt_ayah=answers.get("rt_ayah"), rw_almt_ayah=answers.get("rw_ayah"),
                kelurahan_atau_desa_ayah=answers.get("kel_desa_ayah"), kecamatan_ayah=answers.get("kec_ayah"),
                kabupaten_atau_kota_ayah=answers.get("kab_kota_ayah"),
                ibu=answers.get("nama_ibu"),
                nik_ibu=answers.get("nik_ibu"),
                ttl_ibu=self._combine_ttl(answers.get("tempat_lahir_ibu"), answers.get("tanggal_lahir_ibu")),
                pkj_ibu=answers.get("pekerjaan_ibu"),
                alamat_ibu=answers.get("alamat_ibu"),
                rt_almt_ibu=answers.get("rt_ibu"), rw_almt_ibu=answers.get("rw_ibu"),
                kelurahan_atau_desa_ibu=answers.get("kel_desa_ibu"), kecamatan_ibu=answers.get("kec_ibu"),
                kabupaten_atau_kota_ibu=answers.get("kab_kota_ibu"),
                calon_suami_atau_istri=answers.get("nama_pasangan"),
                bin_atau_binti=answers.get("bin_binti_pasangan"),
                nik_csi=answers.get("nik_pasangan"),
                jk_csi=answers.get("jk_pasangan"),
                ttl_csi=answers.get("ttl_pasangan"),
                agama_csi=answers.get("agama_pasangan"),
                pkj_csi=answers.get("pekerjaan_pasangan"),
                almt_csi=answers.get("alamat_pasangan"),
                rt_csi=answers.get("rt_pasangan"), rw_csi=answers.get("rw_pasangan"),
                kelurahan_atau_desa_csi=answers.get("kel_desa_pasangan"), kecamatan_csi=answers.get("kec_pasangan"),
                kabupaten_atau_kota_csi=answers.get("kab_kota_pasangan"), provinsi_csi=answers.get("provinsi_pasangan"),
                shdk=answers.get("shdk"),
                hari=self._weekday_indonesia(issued_date),
                submission_id=submission.id,
            ))
        elif code == "uhc":
            self.session.add(MasterUHC(
                tgl_surat=issued_date,
                nama_pasien=applicant.get("nama", "-"),
                nik_pasien=applicant.get("nik", "-"),
                ttl_pasien=applicant_ttl,
                jk=applicant.get("jk"),
                status=applicant.get("status_kawin"),
                pekerjaan=applicant.get("pekerjaan"),
                nama_kepala_keluarga=answers.get("nama_kepala_keluarga") or applicant.get("nama"),
                nik_kepala_keluarga=answers.get("nik_kepala_keluarga") or applicant.get("nik"),
                nama_pemohon=answers.get("nama_pemohon") or applicant.get("nama"),
                nik_pemohon=answers.get("nik_pemohon") or applicant.get("nik"),
                no_kk=answers.get("no_kk") or applicant.get("no_kk"),
                tgl_dikeluarkan_kk=self._parse_date(answers.get("tgl_dikeluarkan_kk")),
                alamat=applicant.get("alamat"),
                rt=applicant.get("rt"), rw=applicant.get("rw"),
                terdaftar_dtks=answers.get("terdaftar_dtks"),
                peruntukan=answers.get("peruntukan"),
                rujukan=answers.get("rujukan"),
                nama_2=answers.get("nama_2"), nik_2=answers.get("nik_2"),
                nama_3=answers.get("nama_3"), nik_3=answers.get("nik_3"),
                nama_4=answers.get("nama_4"), nik_4=answers.get("nik_4"),
                nama_5=answers.get("nama_5"), nik_5=answers.get("nik_5"),
                nama_6=answers.get("nama_6"), nik_6=answers.get("nik_6"),
                nama_7=answers.get("nama_7"), nik_7=answers.get("nik_7"),
                nama_8=answers.get("nama_8"), nik_8=answers.get("nik_8"),
                nama_9=answers.get("nama_9"), nik_9=answers.get("nik_9"),
                nama_10=answers.get("nama_10"), nik_10=answers.get("nik_10"),
                nama_ketua_rt=answers.get("nama_ketua_rt"),
                submission_id=submission.id,
            ))
        elif code == "pindah":
            anggota = answers.get("anggota_yang_ikut")
            self.session.add(MasterPindah(
                tgl_surat=issued_date,
                nama_pemohon=applicant.get("nama", "-"),
                nik_pemohon=applicant.get("nik", "-"),
                no_kk=applicant.get("no_kk"),
                alamat_asal=applicant.get("alamat"),
                alamat_tujuan=answers.get("alamat_tujuan"),
                rt_tujuan=answers.get("rt_tujuan"), rw_tujuan=answers.get("rw_tujuan"),
                kel_desa_tujuan=answers.get("kel_desa_tujuan"), kec_tujuan=answers.get("kec_tujuan"),
                kab_kota_tujuan=answers.get("kab_kota_tujuan"), provinsi_tujuan=answers.get("provinsi_tujuan"),
                klasifikasi_kepindahan=answers.get("klasifikasi_kepindahan"),
                alasan_pindah=answers.get("alasan_pindah"),
                jenis_kepindahan=answers.get("jenis_kepindahan"),
                anggota_yang_ikut=int(anggota) if anggota not in (None, "") else None,
                daftar_anggota_pindah=self._pindah_anggota_summary(answers),
                submission_id=submission.id,
            ))
        elif code == "kk":
            # Real per-member data collection (F1.02/F1.06, up to 10
            # members) isn't built yet -- KK's citizen form still only asks
            # status_perubahan (see KK_CATEGORY_DOCS docstring in seed
            # data). Best-effort:
            # header fields from the applicant snapshot, applicant as
            # member #1 (they submitted the request, most often the kepala
            # keluarga), members 2-10 left null and schema-ready.
            self.session.add(MasterKK(
                no_kk=applicant.get("no_kk"),
                nama_kk=applicant.get("nama"),
                alamat=applicant.get("alamat"),
                rt=applicant.get("rt"), rw=applicant.get("rw"),
                nama1=applicant.get("nama"), nik1=applicant.get("nik"),
                jkel1=applicant.get("jk"), tmpLahir1=applicant.get("tempat_lahir"),
                tglLahir1=self._parse_date(applicant.get("tanggal_lahir")),
                status1=applicant.get("status_kawin"),
                tgl_surat=issued_date,
                submission_id=submission.id,
            ))
        elif code == "ubah_data":
            self.session.add(MasterUbahData(
                tgl_surat=issued_date,
                nama=applicant.get("nama", "-"),
                nik=applicant.get("nik", "-"),
                no_kk=applicant.get("no_kk"),
                alamat=applicant.get("alamat"),
                elemen_diubah=answers.get("elemen_diubah"),
                data_lama=answers.get("data_lama"),
                data_baru=answers.get("data_baru"),
                alasan_perubahan=answers.get("alasan_perubahan"),
                submission_id=submission.id,
            ))

    async def _issue(self, submission: Submission, actor: User) -> bytes:
        """Render the final PDF (plus any sub-documents), save each as a new
        file, and mark ISSUED. Returns the main PDF's bytes so the caller
        can attach it to the "issued" notification (MASTER_COLUMN_LETTERS.md
        item 8).

        The letter number is left blank (``nomor`` rendered as an empty
        string) -- surat terbit belum ditandatangani, and staff fill in the
        number by hand at the desa office along with the signature; there is
        no automatic per-template/year sequence allocation.
        """
        template = await self.template_repo.get(submission.template_id)
        fields = await self._list_template_fields(submission.template_id)
        village = await VillageProfileService(self.session).get()
        applicant = await self.build_applicant_snapshot(submission)

        now = datetime.now(timezone.utc)
        tanggal = format_tanggal_indonesia(now)

        render_answers = dict(submission.answers or {})
        berlaku_date: date | None = None
        if template.code == "domisili":
            berlaku_date = self._compute_berlaku(now.date(), render_answers.get("masa_berlaku_bulan"))
            render_answers["berlaku"] = format_tanggal_indonesia(berlaku_date) if berlaku_date else "-"

        file_service = TemplateFileService()
        pdf_bytes, storage_path = await file_service.render_and_save(
            template=template, fields=fields, profile=village,
            answers=render_answers, applicant=applicant, nomor="",
            tanggal=tanggal,
        )

        submission.status = SubmissionStatus.ISSUED
        submission.pdf_storage_path = storage_path
        submission.issued_at = now

        if template.sub_documents:
            sub_paths: dict[str, str] = {}
            for sub_doc in template.sub_documents:
                sub_doc_code = sub_doc["code"]
                _, sub_storage_path = await file_service.render_and_save_sub_document(
                    template=template, profile=village, answers=render_answers,
                    applicant=applicant, nomor="", tanggal=tanggal,
                    sub_doc_code=sub_doc_code,
                )
                sub_paths[sub_doc_code] = sub_storage_path
            submission.sub_document_storage_paths = sub_paths

        # Save record to specific domain master data table
        if template:
            await self._save_to_domain_master(submission, template, applicant, berlaku_date)

        self.session.add(SubmissionStatusHistory(
            submission_id=submission.id, step_index=submission.current_step_index,
            action=HistoryAction.ISSUED, actor_user_id=actor.id, note=None,
        ))
        logger.info("Submission issued id=%s", submission.id)
        return pdf_bytes

    async def regenerate_pdf(self, submission_id: uuid.UUID, actor: User) -> Submission:
        """Re-render an already-issued submission's PDF (and any sub-
        documents) from its current answers/resident data, overwriting the
        stored file(s) in place.

        A deliberate, staff-triggered action distinct from the approve
        button: staff may correct Data Formulir/Data Identitas Warga after
        issuance (the "Setujui" flow only checks completeness once, at
        approval time), and the frozen PDF from `_issue()` doesn't pick that
        up on its own -- see the repeated "PDF sekali render" notes on
        `_issue()`. The letter number stays blank (same as `_issue()`) and
        this does NOT re-run `_save_to_domain_master` (that already ran once
        at real issuance; re-running would insert a duplicate domain-master
        row for the same submission).
        """
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.ISSUED:
            raise ValidationAppError("Hanya pengajuan yang sudah terbit yang bisa digenerate ulang PDF-nya")
        template = await self.template_repo.get(obj.template_id)
        fields = await self._list_template_fields(obj.template_id)
        village = await VillageProfileService(self.session).get()
        applicant = await self.build_applicant_snapshot(obj)

        issued_at = obj.issued_at or datetime.now(timezone.utc)
        tanggal = format_tanggal_indonesia(issued_at)
        render_answers = dict(obj.answers or {})
        if template.code == "domisili":
            # Anchored to the ORIGINAL issuance date, not "now" -- the
            # letter's validity window shouldn't shift just because staff
            # fixed something days/weeks after it was first issued.
            berlaku_date = self._compute_berlaku(issued_at.date(), render_answers.get("masa_berlaku_bulan"))
            render_answers["berlaku"] = format_tanggal_indonesia(berlaku_date) if berlaku_date else "-"

        file_service = TemplateFileService()
        _, storage_path = await file_service.render_and_save(
            template=template, fields=fields, profile=village,
            answers=render_answers, applicant=applicant, nomor="",
            tanggal=tanggal,
        )
        obj.pdf_storage_path = storage_path

        if template.sub_documents:
            sub_paths: dict[str, str] = {}
            for sub_doc in template.sub_documents:
                sub_doc_code = sub_doc["code"]
                _, sub_storage_path = await file_service.render_and_save_sub_document(
                    template=template, profile=village, answers=render_answers,
                    applicant=applicant, nomor="", tanggal=tanggal,
                    sub_doc_code=sub_doc_code,
                )
                sub_paths[sub_doc_code] = sub_storage_path
            obj.sub_document_storage_paths = sub_paths

        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=obj.current_step_index,
            action=HistoryAction.PDF_REGENERATED, actor_user_id=actor.id, note=None,
        ))
        await self.session.commit()
        logger.info("Submission PDF regenerated id=%s by=%s", obj.id, actor.id)
        return obj

    # generic staff_master_data key -> label, for get_missing_staff_fields'
    # REQUIRED_STAFF_FIELDS_BY_JENIS-driven completeness check.
    _MASTER_DATA_LABELS: dict[str, str] = {
        "alamat": "Alamat (Data Master)",
        "rt_id": "RT (Data Master)",
        "jk": "Jenis Kelamin (Data Master)",
        "tempat_lahir": "Tempat Lahir (Data Master)",
        "tanggal_lahir": "Tanggal Lahir (Data Master)",
        "pekerjaan": "Pekerjaan (Data Master)",
        "status_kawin": "Status Kawin (Data Master)",
        "no_kk": "No. KK (Data Master)",
    }

    async def get_missing_staff_fields(self, submission: Submission) -> list[str]:
        """Labels of data staff still needs to fill in before Approve:
        is_staff_only TemplateFields blank in `answers` ("Data Formulir")
        plus, for letter types that need it, whichever
        REQUIRED_STAFF_FIELDS_BY_JENIS keys are still blank in
        `staff_master_data` ("Data Master", filled via PUT .../master-data
        from the citizen's KTP/KK photo attachments -- 2026-08-06, replaces
        the old Resident-identity-column check).

        is_staff_only fields are intentionally is_required=False so a
        CITIZEN's own submission never gets rejected for a field only staff
        can supply. But by the time staff hits Approve, both this and the
        master-data block should be complete -- otherwise the issued PDF
        and domain-master row ship with blank placeholders. Used both to
        hard-block approve() and to warn on the detail page before the click.
        """
        fields = await self._list_template_fields(submission.template_id)
        answers = submission.answers or {}
        missing = [f.label for f in fields if f.is_staff_only and not answers.get(f.field_key)]

        template = await self.template_repo.get(submission.template_id)
        jenis = TEMPLATE_CODE_TO_JENIS.get(template.code.lower()) if template else None
        if jenis:
            draft = submission.staff_master_data or {}
            missing += [
                self._MASTER_DATA_LABELS[key]
                for key in REQUIRED_STAFF_FIELDS_BY_JENIS.get(jenis, [])
                if not draft.get(key)
            ]
        return missing

    async def _check_staff_only_fields_filled(self, submission: Submission) -> None:
        missing = await self.get_missing_staff_fields(submission)
        if missing:
            raise ValidationAppError(
                "Lengkapi data berikut sebelum menyetujui: " + ", ".join(missing)
            )

    async def approve(
        self, submission_id: uuid.UUID, actor: User, note: str | None
    ) -> Submission:
        """Advance a submission one step, or issue it if this was the final step.

        No role-gating per step -- anyone holding the `submission:approve`
        permission (endpoint-level gate) may act at any step of the fixed
        `APPROVAL_STEP_COUNT`-step chain.
        """
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")
        await self._check_staff_only_fields_filled(obj)

        is_last_step = obj.current_step_index == APPROVAL_STEP_COUNT - 1
        issued_pdf: bytes | None = None
        if is_last_step:
            issued_pdf = await self._issue(obj, actor)
        else:
            obj.current_step_index += 1
            self.session.add(SubmissionStatusHistory(
                submission_id=obj.id, step_index=obj.current_step_index,
                action=HistoryAction.APPROVED, actor_user_id=actor.id, note=note,
            ))
        await self.session.commit()
        logger.info("Submission approve processed id=%s by=%s", obj.id, actor.id)
        await AuditLogService(self.session).record(
            actor, "approve",
            f"Menyetujui pengajuan {obj.id}" + (" (surat terbit)" if is_last_step else ""),
            entity_type="submission", entity_id=obj.id,
        )
        if is_last_step:
            attachment = (f"{obj.id}.pdf", issued_pdf) if issued_pdf else None
            await self._notify(
                obj, "issued", "Surat Anda telah terbit dan siap diambil di kantor desa.",
                attachment=attachment,
            )
        else:
            await self._notify(
                obj, "approved",
                "Pengajuan surat Anda disetujui pada tahap ini dan lanjut ke tahap berikutnya.",
            )
        return obj

    async def reject(self, submission_id: uuid.UUID, actor: User, reason: str) -> Submission:
        """Reject a submission (terminal) with a mandatory reason.

        No role-gating per step -- see `approve`'s docstring."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")

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
        await AuditLogService(self.session).record(
            actor, "reject", f"Menolak pengajuan {obj.id}: {reason}",
            entity_type="submission", entity_id=obj.id,
        )
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

    async def download_sub_document_pdf(
        self, submission_id: uuid.UUID, sub_doc_code: str,
        actor_user_id: uuid.UUID, actor_permissions: list[str],
    ) -> bytes:
        """Return one sub-document's PDF bytes (e.g. one of NA's 5 documents).

        Issued since MASTER_COLUMN_LETTERS.md item 8: each sub-document is
        now rendered and saved as its own file at issuance time (`_issue`),
        so this just serves that saved file. Falls back to rendering on
        demand for submissions issued before that change (no
        `sub_document_storage_paths` yet).

        NA's N.4/N.5 forms are the exception (HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md
        poin 1): they need no Kepala Desa/Sekdes signature at all, so the
        applicant can download them the moment the data is filled in --
        while still PENDING -- unlike every other (sub-)document, which
        stays gated behind ISSUED.
        """
        obj = await self.get_or_404(submission_id)
        template = await self.template_repo.get(obj.template_id)
        unsigned_preview_ok = (
            template is not None and template.code == "na" and sub_doc_code in ("na_n4", "na_n5")
        )
        if not unsigned_preview_ok and obj.status != SubmissionStatus.ISSUED:
            raise ValidationAppError("Surat belum terbit")
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        if not can_read_all and obj.submitted_by_user_id != actor_user_id:
            raise ForbiddenError("Anda tidak berhak mengunduh surat ini")
        if unsigned_preview_ok and obj.status != SubmissionStatus.ISSUED:
            village = await VillageProfileService(self.session).get()
            applicant = await self.build_applicant_snapshot(obj)
            tanggal = format_tanggal_indonesia(datetime.now(timezone.utc))
            return TemplateRenderService().render_issued_sub_document(
                template=template, profile=village, answers=obj.answers, applicant=applicant,
                nomor="-", tanggal=tanggal, sub_doc_code=sub_doc_code,
            )
        saved_path = (obj.sub_document_storage_paths or {}).get(sub_doc_code)
        if saved_path:
            return await FileStorageService().read(saved_path)
        village = await VillageProfileService(self.session).get()
        applicant = await self.build_applicant_snapshot(obj)
        tanggal = format_tanggal_indonesia(obj.issued_at or datetime.now(timezone.utc))
        return TemplateRenderService().render_issued_sub_document(
            template=template, profile=village, answers=obj.answers, applicant=applicant,
            nomor="", tanggal=tanggal, sub_doc_code=sub_doc_code,
        )
