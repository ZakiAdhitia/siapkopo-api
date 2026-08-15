"""Submission domain models: submissions, status history, and attachments."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class SubmissionStatus(str, enum.Enum):
    """Lifecycle status of a Submission."""

    PENDING = "pending"
    REJECTED = "rejected"
    ISSUED = "issued"


class HistoryAction(str, enum.Enum):
    """Kind of event recorded in SubmissionStatusHistory."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ISSUED = "issued"
    PDF_REGENERATED = "pdf_regenerated"


def _values_callable(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum VALUES ("pending"), not member NAMES ("PENDING")."""
    return [member.value for member in enum_cls]


class Submission(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A citizen's letter request, tracked through approval to issuance."""

    __tablename__ = "submissions"

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    # Null for a guest submission (Bagian 3.2, STRATEGI doc) -- no account was
    # ever created, so there is no user to attribute the submission to.
    submitted_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), index=True, nullable=True
    )
    # 2026-08-06: the applicant is identified by NIK+nama stored directly on
    # the submission -- no more persistent Resident registry (couldn't be
    # kept up to date, per SISTEM_PENGOLAHAN_DATA_WARGA.md). Always required,
    # every submission path (create/create_guest/create_walkin).
    applicant_nik: Mapped[str] = mapped_column(String(20), index=True)
    applicant_nama: Mapped[str] = mapped_column(String(150))
    # Guest-only contact for status notifications (no user account to read an
    # email from) and as an alternate lookup key for the no-login status
    # check (Bagian 8, STRATEGI doc rev. 2026-07-26). WhatsApp is stored as
    # plain contact metadata only -- no outbound WhatsApp channel exists
    # anywhere in this system; notifications still only go out by email.
    guest_contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    guest_contact_whatsapp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # Staff-entered from the submission detail page (PUT .../master-data),
    # from the citizen's photographed KTP/KK -- alamat/rt_id/jk/tempat_lahir/
    # tanggal_lahir/pekerjaan/status_kawin/no_kk. Blocking for Approve on
    # letter types that need it (SubmissionService.get_missing_staff_fields,
    # REQUIRED_STAFF_FIELDS_BY_JENIS). This is what feeds the per-letter-type
    # domain-master tables (MasterDomisili etc.) now, replacing what used to
    # be auto-derived from a Resident row.
    staff_master_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Letter-specific staff blocks that don't fit the generic 8-field
    # identity shape above -- Domisili's alamat asal, NA's ayah/ibu/CSI,
    # Kematian's almarhum, Kelahiran's ayah/ibu, KK's anggota keluarga
    # table. Shape is jenis-dependent, validated by
    # app.schemas.staff_extra_data.STAFF_EXTRA_DATA_SCHEMA_BY_JENIS.
    # Populated via PUT .../extra-data (SubmissionService.update_extra_data).
    staff_extra_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    physical_documents_promised: Mapped[bool] = mapped_column(default=False)
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, native_enum=False, length=20, values_callable=_values_callable),
        default=SubmissionStatus.PENDING,
    )
    current_step_index: Mapped[int | None] = mapped_column(nullable=True, default=0)
    # Left blank at issuance -- no automatic per-template/year sequence
    # allocation; staff fill it in by hand at the desa office along with the
    # signature (surat terbit belum ditandatangani).
    letter_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pdf_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # {sub_doc_code: storage_path}, populated at issuance for templates with
    # sub_documents (e.g. NA's 5 documents) -- each sub-document is rendered
    # and saved once at issuance instead of on every download request.
    sub_document_storage_paths: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # 2026-08-13 (Tahap 4 WYSIWYG editor): staff-edited full letter HTML,
    # only meaningful for letter types with no docx specimen (currently just
    # "ubah_data" -- see SubmissionService.update_preview_html's guard).
    # When set, this becomes the source of truth for the issued/regenerated
    # PDF instead of a fresh render from answers+template.
    edited_preview_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubmissionStatusHistory(UUIDMixin, TimestampMixin, Base):
    """Append-only audit trail entry for a Submission's lifecycle."""

    __tablename__ = "submission_status_history"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("submissions.id"), index=True
    )
    step_index: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[HistoryAction] = mapped_column(
        SAEnum(HistoryAction, native_enum=False, length=20, values_callable=_values_callable)
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubmissionAttachment(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An uploaded supporting document attached to a Submission."""

    __tablename__ = "submission_attachments"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("submissions.id"), index=True
    )
    document_label: Mapped[str] = mapped_column(String(150))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    storage_path: Mapped[str] = mapped_column(String(500))
