"""Schemas for approval-step config, submissions, history, and attachments."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.submission import HistoryAction, SubmissionStatus


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ApprovalStepConfigRead(_Read):
    village_id: UUID
    order_index: int
    role_id: UUID


class ApprovalStepReplaceItem(BaseModel):
    role_id: UUID


class ApprovalStepsReplaceRequest(BaseModel):
    steps: list[ApprovalStepReplaceItem] = Field(min_length=1)


class SubmissionCreate(BaseModel):
    template_id: UUID
    answers: dict = Field(default_factory=dict)


class SubmissionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class SubmissionApproveRequest(BaseModel):
    note: str | None = None


class SubmissionRead(_Read):
    village_id: UUID
    template_id: UUID
    submitted_by_user_id: UUID
    answers: dict
    status: SubmissionStatus
    current_step_index: int | None = None
    letter_number: str | None = None
    verification_code: str | None = None
    rejection_reason: str | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    issued_at: datetime | None = None
    created_at: datetime


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


class PublicVerifyRead(BaseModel):
    """Public-safe view of an issued letter — no PII beyond the applicant's own name."""

    letter_number: str
    template_name: str
    applicant_name: str
    issued_at: datetime
    signed_by: str
