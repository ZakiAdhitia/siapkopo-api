"""Schemas for approval-step config, submissions, history, and attachments."""
from datetime import date, datetime
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


class SubmissionAnswersUpdateRequest(BaseModel):
    """Staff correction of a pending submission's own form answers."""

    answers: dict = Field(default_factory=dict)


class ApplicantDataCompleteRequest(BaseModel):
    """Staff-supplied master-data completion for a guest submission whose NIK
    wasn't already on file (Bagian 5, Master Data rework) -- entered from the
    submission detail page, applied to residents/family_cards on approval.

    jk/tempat_lahir/tanggal_lahir/pekerjaan/status_kawin (2026-08-02 fix):
    the shared identity snapshot every PDF reads via _applicant_data_from_
    resident -- captured here because there's no Resident row to edit via
    the separate "Data Identitas Warga" panel until issuance materializes
    one from these same fields (SubmissionService._materialize_pending_
    applicant).
    """

    no_kk: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^\d{16}$")
    rt_id: UUID | None = None
    alamat: str | None = None
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    pekerjaan: str | None = None
    status_kawin: str | None = None


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
    # Set by staff from the detail page (see complete_applicant_data) for a
    # guest submission whose NIK wasn't already in master data -- used to
    # actually create the Resident/FamilyCard rows once this submission is
    # approved (see SubmissionService._issue).
    pending_applicant_no_kk: str | None = None
    pending_applicant_rt_id: UUID | None = None
    pending_applicant_jk: str | None = None
    pending_applicant_tempat_lahir: str | None = None
    pending_applicant_tanggal_lahir: date | None = None
    pending_applicant_pekerjaan: str | None = None
    pending_applicant_status_kawin: str | None = None
    # Populated by the router (not the ORM object) from resolve_applicant_data
    # -- staff/admin reviewing a submission need to see who it's for and
    # verify their identity (nik/alamat) before approving.
    applicant_nama: str | None = None
    applicant_nik: str | None = None
    applicant_alamat: str | None = None
    applicant_no_kk: str | None = None
    # Populated by the router: whether this submission's applicant is
    # already linked to a Resident row (master data). False means the
    # applicant-data/KK completion step is still pending for this NIK.
    applicant_in_master_data: bool = False
    # Populated by the router: the linked Resident's id (None if not yet in
    # master data) plus the shared identity snapshot fields every letter
    # type's PDF reads (jk/tempat_lahir/tanggal_lahir/pekerjaan/status_kawin,
    # see _applicant_data_from_resident) -- lets the detail page offer a
    # "Lengkapi Data Identitas Warga" panel (PUT /residents/{id}) instead of
    # citizens seeing a blank PDF field with no way for staff to fix it.
    applicant_resident_id: UUID | None = None
    applicant_jk: str | None = None
    applicant_tempat_lahir: str | None = None
    applicant_tanggal_lahir: str | None = None
    applicant_pekerjaan: str | None = None
    applicant_status_kawin: str | None = None
    applicant_rt_id: UUID | None = None
    # Populated by the router: labels of is_staff_only TemplateFields still
    # blank in `answers` -- approve() hard-blocks on this list server-side
    # (SubmissionService._check_staff_only_fields_filled); surfaced here too
    # so the detail page can warn and disable Approve before the click.
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
