"""Letter template schemas: template + field Create/Update/Read, reorder request."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.letter_template import FieldType, LetterOutputCategory


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TemplateFieldCreate(BaseModel):
    field_key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool = True
    validation_rules: dict | None = None
    is_staff_only: bool = False


class TemplateFieldUpdate(BaseModel):
    """Note: field_key is intentionally absent — immutable after creation."""

    label: str | None = None
    field_type: FieldType | None = None
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool | None = None
    validation_rules: dict | None = None
    is_staff_only: bool | None = None


class TemplateFieldRead(_Read):
    template_id: UUID
    order_index: int
    field_key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool
    validation_rules: dict | None = None
    is_staff_only: bool


class LetterTemplateCreate(BaseModel):
    code: str
    name: str
    description: str | None = None
    icon: str
    color_bg: str
    color_fg: str
    is_active: bool = True
    required_documents: list[str] = Field(default_factory=list)
    optional_documents: list[str] = Field(default_factory=list)
    # Conditional Sub-Category Form (Bagian 4.2, STRATEGI doc): both null
    # means required_documents above is used as-is (every non-KK template
    # today). See app/models/letter_template.py for the full explanation.
    category_field_key: str | None = None
    required_documents_by_category: dict[str, list[str]] | None = None
    numbering_prefix: str
    numbering_pattern: str
    pdf_body_template: str
    output_category: LetterOutputCategory = LetterOutputCategory.DESA_DIRECT
    post_issuance_note: str | None = None
    sub_documents: list[dict] | None = None


class TemplateActiveRequest(BaseModel):
    is_active: bool


class LetterTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color_bg: str | None = None
    color_fg: str | None = None
    is_active: bool | None = None
    required_documents: list[str] | None = None
    optional_documents: list[str] | None = None
    category_field_key: str | None = None
    required_documents_by_category: dict[str, list[str]] | None = None
    numbering_prefix: str | None = None
    numbering_pattern: str | None = None
    pdf_body_template: str | None = None
    output_category: LetterOutputCategory | None = None
    post_issuance_note: str | None = None
    sub_documents: list[dict] | None = None


class LetterTemplateRead(_Read):
    code: str
    name: str
    description: str | None = None
    icon: str
    color_bg: str
    color_fg: str
    is_active: bool
    required_documents: list[str]
    optional_documents: list[str]
    category_field_key: str | None = None
    required_documents_by_category: dict[str, list[str]] | None = None
    numbering_prefix: str
    numbering_pattern: str
    pdf_body_template: str
    output_category: LetterOutputCategory
    post_issuance_note: str | None = None
    sub_documents: list[dict] | None = None
    # 2026-08-13 (Tahap 4 preview redesign): populated by the router
    # (DocxLetterRenderer.supports(code)), same pattern as SubmissionRead's
    # applicant_* fields -- lets the frontend decide whether Tahap 4 shows
    # the real docx-rendered PDF (view-only, official F-1.02/F-1.03/etc
    # format) or the editable HTML preview (the one letter type with no
    # docx specimen, "ubah_data").
    uses_docx_template: bool = False


class ReorderFieldsRequest(BaseModel):
    field_ids: list[UUID]
