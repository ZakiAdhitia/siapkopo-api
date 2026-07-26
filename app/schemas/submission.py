"""Schemas for approval-step config, submissions, history, and attachments."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.letter_template import LetterOutputCategory
from app.models.submission import HistoryAction, SubmissionStatus


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ApprovalStepConfigRead(_Read):
    order_index: int
    role_id: UUID


class ApprovalStepReplaceItem(BaseModel):
    role_id: UUID


class ApprovalStepsReplaceRequest(BaseModel):
    steps: list[ApprovalStepReplaceItem] = Field(min_length=1)


class SubmissionCreate(BaseModel):
    template_id: UUID
    answers: dict = Field(default_factory=dict)
    physical_documents_promised: bool = False


class SubmissionWalkinCreate(BaseModel):
    """Mode Loket (Bagian 3.1, STRATEGI doc): staff submits on behalf of a
    walk-in citizen. Issued immediately -- no guest contact needed."""

    template_id: UUID
    nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    answers: dict = Field(default_factory=dict)
    applicant_nama: str | None = None
    applicant_alamat: str | None = None


class ApplicantDataRead(BaseModel):
    """Auto-fill data for the submission form: {nama, nik, alamat, no_kk}."""

    nama: str
    nik: str
    alamat: str
    no_kk: str


class SubmissionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class SubmissionApproveRequest(BaseModel):
    note: str | None = None


class SubmissionRead(_Read):
    template_id: UUID
    submitted_by_user_id: UUID | None = None
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
    # Populated by the router (not the ORM object) from resolve_applicant_data
    # -- staff/admin reviewing a submission need to see who it's for and
    # verify their identity (nik/alamat) before approving.
    applicant_nama: str | None = None
    applicant_nik: str | None = None
    applicant_alamat: str | None = None
    applicant_no_kk: str | None = None


class SubmissionStatusHistoryRead(_Read):
    step_index: int | None = None
    action: HistoryAction
    actor_user_id: UUID | None = None
    note: str | None = None
    created_at: datetime


class SubmissionAttachmentRead(_Read):
    document_label: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class ApplicantLookupRead(BaseModel):
    """Public NIK autofill result for the guest submission form."""

    nama: str
    alamat: str
    no_kk: str


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
