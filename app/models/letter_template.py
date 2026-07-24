"""Letter template models: dynamic template + field definitions."""
import enum
import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class FieldType(str, enum.Enum):
    """Supported dynamic form field types for a letter template."""

    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    DATE = "date"
    TEXTAREA = "textarea"


class LetterTemplate(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A letter type's metadata, dynamic-form definition, and PDF body template."""

    __tablename__ = "letter_templates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_letter_templates_code"),
    )

    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(50))
    color_bg: Mapped[str] = mapped_column(String(20))
    color_fg: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    required_documents: Mapped[list[str]] = mapped_column(JSON, default=list)
    numbering_prefix: Mapped[str] = mapped_column(String(20))
    numbering_pattern: Mapped[str] = mapped_column(String(100))
    pdf_body_template: Mapped[str] = mapped_column(Text)


class TemplateField(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A single dynamic form field belonging to a letter template."""

    __tablename__ = "template_fields"
    __table_args__ = (
        UniqueConstraint("template_id", "field_key", name="uq_template_fields_template_key"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    order_index: Mapped[int] = mapped_column(default=0)
    field_key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(150))
    field_type: Mapped[FieldType] = mapped_column(
        SAEnum(
            FieldType, native_enum=False, length=20,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        )
    )
    options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    validation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
