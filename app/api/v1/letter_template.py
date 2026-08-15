"""Letter template CRUD endpoints: template + field management, PDF preview."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.letter_template import (
    LetterTemplateCreate,
    LetterTemplateRead,
    LetterTemplateUpdate,
    ReorderFieldsRequest,
    TemplateActiveRequest,
    TemplateFieldCreate,
    TemplateFieldRead,
    TemplateFieldUpdate,
)
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageProfileService
from app.services.template_render import TemplateRenderService

router = APIRouter(tags=["letter-templates"])


@router.post("/templates", response_model=Envelope[LetterTemplateRead])
async def create_template(
    body: LetterTemplateCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Create a new letter template."""
    obj = await LetterTemplateService(session).create(body.model_dump(exclude_unset=True))
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/templates", response_model=Envelope[Page[LetterTemplateRead]])
async def list_templates(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List letter templates, paginated, with optional active filter and name search."""
    items, total = await LetterTemplateService(session).list(
        p.page, p.size, is_active=is_active, search=search
    )
    return success_response(build_page(items, total, p.page, p.size, LetterTemplateRead))


@router.get("/templates/{template_id}", response_model=Envelope[LetterTemplateRead])
async def get_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """Get a single letter template by id."""
    obj = await LetterTemplateService(session).get_or_404(template_id)
    data = LetterTemplateRead.model_validate(obj).model_dump(mode="json")
    data["uses_docx_template"] = TemplateRenderService().uses_docx_template(obj.code)
    return success_response(data)


@router.put("/templates/{template_id}", response_model=Envelope[LetterTemplateRead])
async def update_template(
    template_id: UUID,
    body: LetterTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Update a letter template's metadata."""
    obj = await LetterTemplateService(session).update(template_id, body.model_dump(exclude_unset=True))
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.patch("/templates/{template_id}/active", response_model=Envelope[LetterTemplateRead])
async def set_template_active(
    template_id: UUID,
    body: TemplateActiveRequest,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:configure")),
) -> dict:
    """Toggle whether warga can submit this template -- the only template
    change allowed from `template:configure` alone (no `template:manage`),
    e.g. Sekretaris Desa (HASIL_UJICOBA_PERROLE.md sekdes item 1)."""
    obj = await LetterTemplateService(session).set_active(template_id, body.is_active)
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/templates/{template_id}", response_model=Envelope[None])
async def delete_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Soft-delete a letter template."""
    await LetterTemplateService(session).delete(template_id)
    return success_response(None, "Dihapus")


@router.get("/templates/{template_id}/fields", response_model=Envelope[list[TemplateFieldRead]])
async def list_template_fields(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List a template's fields, ordered."""
    fields = await LetterTemplateService(session).list_fields(template_id)
    return success_response(
        [TemplateFieldRead.model_validate(f).model_dump(mode="json") for f in fields]
    )


@router.post("/templates/{template_id}/fields", response_model=Envelope[TemplateFieldRead])
async def add_template_field(
    template_id: UUID,
    body: TemplateFieldCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Add a new field to a template, appended at the end of the order."""
    obj = await LetterTemplateService(session).add_field(
        template_id, body.model_dump(exclude_unset=True)
    )
    return success_response(TemplateFieldRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


# Static "reorder" route MUST precede the parameterized "{field_id}" route below,
# mirroring the /residents/import-before-/residents/{item_id} pattern in master.py.
@router.put(
    "/templates/{template_id}/fields/reorder",
    response_model=Envelope[list[TemplateFieldRead]],
)
async def reorder_template_fields(
    template_id: UUID,
    body: ReorderFieldsRequest,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Rewrite field order from a full ordered list of field ids."""
    fields = await LetterTemplateService(session).reorder_fields(template_id, body.field_ids)
    return success_response(
        [TemplateFieldRead.model_validate(f).model_dump(mode="json") for f in fields],
        "Urutan diperbarui",
    )


@router.put("/templates/{template_id}/fields/{field_id}", response_model=Envelope[TemplateFieldRead])
async def update_template_field(
    template_id: UUID,
    field_id: UUID,
    body: TemplateFieldUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Update a single template field."""
    obj = await LetterTemplateService(session).update_field(
        template_id, field_id, body.model_dump(exclude_unset=True)
    )
    return success_response(TemplateFieldRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/templates/{template_id}/fields/{field_id}", response_model=Envelope[None])
async def delete_template_field(
    template_id: UUID,
    field_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Soft-delete a single template field."""
    await LetterTemplateService(session).delete_field(template_id, field_id)
    return success_response(None, "Dihapus")


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> Response:
    """Render a PDF preview of the template using auto-generated sample data."""
    service = LetterTemplateService(session)
    template = await service.get_or_404(template_id)
    fields = await service.list_fields(template_id)
    profile = await VillageProfileService(session).get()
    pdf_bytes = TemplateRenderService().render_preview(template, fields, profile)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="preview-{template.code}.pdf"'},
    )
