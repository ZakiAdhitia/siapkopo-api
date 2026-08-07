"""Schemas for approval-step config, submissions, history, and attachments."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.letter_template import LetterOutputCategory
from app.models.submission import HistoryAction, SubmissionStatus


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class SubmissionCreate(BaseModel):
    template_id: UUID
    applicant_nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    applicant_nama: str = Field(min_length=1)
    answers: dict = Field(default_factory=dict)
    physical_documents_promised: bool = False


class SubmissionMasterDataUpdateRequest(BaseModel):
    """Staff-entered identity fields (from KTP/KK photo attachments),
    generic across all letter types -- the same shape every PDF template
    and domain-master row reads (SubmissionService.build_applicant_snapshot).
    Full-replace semantics, same convention as SubmissionAnswersUpdateRequest."""

    alamat: str | None = None
    rt_id: UUID | None = None
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    pekerjaan: str | None = None
    status_kawin: str | None = None
    no_kk: str | None = None

    @field_validator("tanggal_lahir")
    @classmethod
    def _tanggal_lahir_not_today_or_future(cls, value: date | None) -> date | None:
        if value is not None and value >= date.today():
            raise ValueError("Tanggal lahir tidak boleh hari ini atau di masa depan")
        return value


class SubmissionWalkinCreate(BaseModel):
    """Mode Loket (Bagian 3.1, STRATEGI doc): staff submits on behalf of a
    walk-in citizen. Issued immediately -- no guest contact needed."""

    template_id: UUID
    applicant_nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    applicant_nama: str = Field(min_length=1)
    answers: dict = Field(default_factory=dict)
    # Best-effort, not blocking -- see SubmissionService.create_walkin.
    master_data: SubmissionMasterDataUpdateRequest | None = None


class SubmissionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class SubmissionApproveRequest(BaseModel):
    note: str | None = None


class SubmissionAnswersUpdateRequest(BaseModel):
    """Staff correction of a pending submission's own form answers."""

    answers: dict = Field(default_factory=dict)


class SubmissionAttachmentRead(_Read):
    submission_id: UUID
    document_label: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class SubmissionRead(_Read):
    template_id: UUID
    submitted_by_user_id: UUID | None = None
    # 2026-08-06: real columns now (no more Resident lookup) -- who this
    # letter is for, fixed at creation time.
    applicant_nik: str
    applicant_nama: str
    answers: dict
    physical_documents_promised: bool
    status: SubmissionStatus
    current_step_index: int | None = None
    letter_number: str | None = None
    rejection_reason: str | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    issued_at: datetime | None = None
    created_at: datetime
    # Guest-only contact info (Bagian 3.2/8, STRATEGI doc) -- shown on the
    # staff detail page so a reviewer can reach the applicant directly.
    guest_contact_email: str | None = None
    guest_contact_whatsapp: str | None = None
    # Populated by the router (not the ORM object) from
    # SubmissionService.build_applicant_snapshot -- the shared identity
    # block staff fills in via PUT .../master-data (SubmissionMasterDataUpdateRequest),
    # read back out here flat (not nested) for the detail page's "Isi Data
    # Master" panel and for crosscheck before approving.
    applicant_alamat: str | None = None
    applicant_no_kk: str | None = None
    applicant_jk: str | None = None
    applicant_tempat_lahir: str | None = None
    applicant_tanggal_lahir: str | None = None
    applicant_pekerjaan: str | None = None
    applicant_status_kawin: str | None = None
    applicant_rt_id: UUID | None = None
    # Populated by the router: labels of is_staff_only TemplateFields still
    # blank in `answers`, plus any still-missing REQUIRED_STAFF_FIELDS_BY_JENIS
    # master-data key for this letter type -- approve() hard-blocks on this
    # list server-side (SubmissionService._check_staff_only_fields_filled);
    # surfaced here too so the detail page can warn and disable Approve
    # before the click.
    missing_staff_fields: list[str] = []
    # Populated by the router from SubmissionAttachment rows.
    attachments: list[SubmissionAttachmentRead] = []


class SubmissionStatusHistoryRead(_Read):
    step_index: int | None = None
    action: HistoryAction
    actor_user_id: UUID | None = None
    # Populated by the router: the acting user's username, so staff/guest
    # tracking can show "disetujui oleh <username>" instead of a raw UUID.
    actor_username: str | None = None
    note: str | None = None
    created_at: datetime


class GuestTrackRead(BaseModel):
    """Combined guest status view: one public lookup instead of separate
    submission/history/template calls the guest has no permission to make."""

    submission: SubmissionRead
    history: list[SubmissionStatusHistoryRead]
    template_name: str
    template_icon: str
    template_color_bg: str
    template_color_fg: str
    template_output_category: LetterOutputCategory
    template_post_issuance_note: str | None = None
