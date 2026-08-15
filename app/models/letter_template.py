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
    TIME = "time"


class LetterOutputCategory(str, enum.Enum):
    """Where a letter's output lands once issued (Bagian 4.3, STRATEGI doc).

    DESA_DIRECT letters are final once issued by the village. DUKCAPIL_PENGANTAR
    letters are a cover form the applicant must still take to Kecamatan/Disdukcapil
    for further processing. KUA_PENGANTAR is the same idea but for NA (marriage
    recommendation) letters, which the applicant takes to the KUA instead.
    """

    DESA_DIRECT = "desa_direct"
    DUKCAPIL_PENGANTAR = "dukcapil_pengantar"
    KUA_PENGANTAR = "kua_pengantar"


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
    # Optional attachments (PERBAIKAN_INPUT_DAN_LAMPIRAN_SURAT.MD, 2026-08-02):
    # documents marked "(Bila Ada)" -- may be uploaded but never block
    # submission if skipped. Unlike required_documents, guest/attachment
    # validation only rejects a label that's in NEITHER list; every
    # optional_documents label is always allowed, never required.
    optional_documents: Mapped[list[str]] = mapped_column(JSON, default=list)
    # Conditional Sub-Category Form (Bagian 4.2, STRATEGI doc): when set,
    # required documents vary by the value of one dynamic field instead of
    # being a fixed list -- e.g. KK's 5 permohonan categories (Baru,
    # Kelahiran, Menumpang, Pengurangan, Hilang/Rusak) each need different
    # supporting documents (SYARAT-PENGAJUAN-SURAT.md). `category_field_key`
    # names which TemplateField.field_key drives the choice;
    # `required_documents_by_category` maps that field's answer value to its
    # own required_documents list. Both null means "not conditional" --
    # required_documents above is used as-is, same as every other template.
    category_field_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    required_documents_by_category: Mapped[dict[str, list[str]] | None] = mapped_column(
        JSON, nullable=True
    )
    numbering_prefix: Mapped[str] = mapped_column(String(20))
    numbering_pattern: Mapped[str] = mapped_column(String(100))
    pdf_body_template: Mapped[str] = mapped_column(Text)
    output_category: Mapped[LetterOutputCategory] = mapped_column(
        SAEnum(
            LetterOutputCategory, native_enum=False, length=30,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        default=LetterOutputCategory.DESA_DIRECT,
    )
    post_issuance_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Multi-sub-document letters (e.g. NA's N.1/N.4/N.5 + 2 supporting
    # letters, all from one submission's answers): list of {code, name}.
    # Null/empty means "single document", the default for every other
    # template. Drives which sub-document download buttons the admin/loket
    # screens render (see TemplateRenderService.render_issued_sub_document).
    sub_documents: Mapped[list[dict] | None] = mapped_column(JSON, nullable=True)


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
    # Filled in by staff/admin while processing (e.g. SKTM's DTKS
    # registration check, MASTER_COLUMN_LETTERS.md item 11) rather than
    # asked of the citizen at submission -- hidden from the citizen-facing
    # form, still editable via the staff "Data Formulir" edit view.
    is_staff_only: Mapped[bool] = mapped_column(default=False)
