"""LAPDUK (Laporan Penduduk) endpoints: scoped upsert/list + Excel import/export.

Every endpoint requires only baseline authentication (`auth:me`) at the router
gate -- the real, fine-grained authorization (RT/own-only, RW/own-RW-only,
staff+admin/all) is data-driven inside LapdukService from the caller's
resolved permission codes, mirroring how SubmissionService scopes
read access beyond its router's baseline permission gate.
"""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.repositories.auth import UserRepository
from app.schemas.common import Page
from app.schemas.lapduk import LapdukImportResult, LapdukRead, LapdukUpsert
from app.schemas.master import RTRead
from app.services.lapduk import LapdukService

router = APIRouter(tags=["lapduk"])


async def _load_actor(session: AsyncSession, current: CurrentUser):
    return await UserRepository(session).get_by_id(UUID(current.id))


# Static route: must precede parameterized routes with the same prefix (none
# exist on this router today, but keeping the convention from letter_template.py/
# public_submission.py in case one is added later).
@router.get("/lapduk/rts", response_model=Envelope[list[RTRead]])
async def list_lapduk_rts(
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """RTs the caller may fill a LAPDUK report for (own RT, own RW's RTs, or all)."""
    actor = await _load_actor(session, current)
    rts = await LapdukService(session).list_visible_rts(actor, current.permissions)
    return success_response([RTRead.model_validate(r).model_dump(mode="json") for r in rts])


@router.post("/lapduk", response_model=Envelope[LapdukRead])
async def upsert_lapduk(
    body: LapdukUpsert,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Create or update a single RT+period LAPDUK report."""
    actor = await _load_actor(session, current)
    obj = await LapdukService(session).upsert(
        actor, current.permissions, body.model_dump(exclude_unset=True)
    )
    return success_response(LapdukRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.put("/lapduk", response_model=Envelope[LapdukRead])
async def upsert_lapduk_put(
    body: LapdukUpsert,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Alias of POST /lapduk (upsert semantics apply to both verbs)."""
    return await upsert_lapduk(body, session, current)


@router.get("/lapduk", response_model=Envelope[Page[LapdukRead]])
async def list_lapduk(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    period: str | None = Query(None),
    rw_id: UUID | None = Query(None),
    rt_id: UUID | None = Query(None),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """List LAPDUK reports visible to the caller, filtered by period/rw/rt."""
    actor = await _load_actor(session, current)
    items, total = await LapdukService(session).list(
        actor, current.permissions, p.page, p.size, period, rw_id, rt_id
    )
    return success_response({
        "items": [LapdukRead.model_validate(i).model_dump(mode="json") for i in items],
        "total": total, "page": p.page, "size": p.size,
    })


@router.get("/lapduk/export")
async def export_lapduk(
    session: AsyncSession = Depends(get_db),
    period: str | None = Query(None),
    rw_id: UUID | None = Query(None),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> StreamingResponse:
    """Export visible LAPDUK reports as an xlsx download."""
    actor = await _load_actor(session, current)
    data = await LapdukService(session).export_bytes(actor, current.permissions, period, rw_id)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=lapduk.xlsx"},
    )


@router.post("/lapduk/import", response_model=Envelope[LapdukImportResult])
async def import_lapduk(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Bulk-import LAPDUK reports from an uploaded xlsx file."""
    actor = await _load_actor(session, current)
    content = await file.read()
    result = await LapdukService(session).import_bytes(actor, current.permissions, content)
    return success_response(result, "Import selesai")
