"""Submission domain models: approval step config, submissions, status
history, attachments, and per-template/year letter-number counters."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
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


def _values_callable(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum VALUES ("pending"), not member NAMES ("PENDING")."""
    return [member.value for member in enum_cls]


class ApprovalStepConfig(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One ordered step in the global, configurable approval chain."""

    __tablename__ = "approval_step_configs"
    __table_args__ = (
        UniqueConstraint("order_index", name="uq_approval_step_order"),
    )

    order_index: Mapped[int] = mapped_column()
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))


class Submission(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A citizen's letter request, tracked through approval to issuance."""

    __tablename__ = "submissions"

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id"), index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, native_enum=False, length=20, values_callable=_values_callable),
        default=SubmissionStatus.PENDING,
    )
    current_step_index: Mapped[int | None] = mapped_column(nullable=True, default=0)
    letter_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verification_code: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True
    )
    pdf_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
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


class LetterNumberCounter(UUIDMixin, TimestampMixin, Base):
    """Tracks the last allocated sequence number per (template, year)."""

    __tablename__ = "letter_number_counters"
    __table_args__ = (
        UniqueConstraint("template_id", "year", name="uq_letter_number_counter_template_year"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    year: Mapped[int] = mapped_column()
    last_seq: Mapped[int] = mapped_column(default=0)
