"""Master data CRUD endpoints: village hierarchy, family cards, residents."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.master import (
    FamilyCardCreate,
    FamilyCardRead,
    FamilyCardUpdate,
    RTCreate,
    RTRead,
    RTUpdate,
    RWCreate,
    RWRead,
    RWUpdate,
    ResidentCreate,
    ResidentImportResult,
    ResidentRead,
    ResidentUpdate,
    VillageProfileRead,
    VillageProfileUpdate,
)
from app.models.master import RT, RW, FamilyCard
from app.services.excel import ResidentExcelService
from app.services.master import (
    FamilyCardService,
    RTService,
    RWService,
    ResidentService,
    VillageProfileService,
)

router = APIRouter(tags=["master-data"])


async def _resident_read(session: AsyncSession, obj) -> dict:
    """Build a ResidentRead dict enriched with denormalized kk/rt/rw
    display fields (see ResidentRead's docstring for why this lives here
    instead of requiring rt:manage/rw:manage/family_card:manage)."""
    data = ResidentRead.model_validate(obj).model_dump(mode="json")
    if obj.family_card_id is not None:
        fc = await session.get(FamilyCard, obj.family_card_id)
        if fc is not None:
            data["kk_number"] = fc.kk_number
    if obj.rt_id is not None:
        rt = await session.get(RT, obj.rt_id)
        if rt is not None:
            data["rt_number"] = rt.number
            rw = await session.get(RW, rt.rw_id)
            if rw is not None:
                data["rw_number"] = rw.number
    return data


# ---- Village Profile (singleton) ----
@router.get("/village-profile", response_model=Envelope[VillageProfileRead])
async def get_village_profile(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("auth:me")),
) -> dict:
    """Get the village's profile. Any authenticated user may read it."""
    obj = await VillageProfileService(session).get()
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"))


@router.put("/village-profile", response_model=Envelope[VillageProfileRead])
async def update_village_profile(
    body: VillageProfileUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("village:manage")),
) -> dict:
    """Update the village's profile."""
    obj = await VillageProfileService(session).update(body.model_dump(exclude_unset=True))
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


# ---- RW ----
@router.post("/rw", response_model=Envelope[RWRead])
async def create_rw(
    body: RWCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rw:manage")),
) -> dict:
    """Create a new RW."""
    obj = await RWService(session).create(body.model_dump(exclude_unset=True))
    return success_response(RWRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/rw", response_model=Envelope[Page[RWRead]])
async def list_rw(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("rw:read")),
) -> dict:
    """List RW, paginated."""
    items, total = await RWService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, RWRead))


@router.get("/rw/{item_id}", response_model=Envelope[RWRead])
async def get_rw(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rw:manage")),
) -> dict:
    """Get a single RW by id."""
    obj = await RWService(session).get_or_404(item_id)
    return success_response(RWRead.model_validate(obj).model_dump(mode="json"))


@router.put("/rw/{item_id}", response_model=Envelope[RWRead])
async def update_rw(
    item_id: UUID,
    body: RWUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rw:manage")),
) -> dict:
    """Update a RW."""
    obj = await RWService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(RWRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/rw/{item_id}", response_model=Envelope[None])
async def delete_rw(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rw:manage")),
) -> dict:
    """Soft-delete a RW."""
    await RWService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- RT ----
@router.post("/rt", response_model=Envelope[RTRead])
async def create_rt(
    body: RTCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rt:manage")),
) -> dict:
    """Create a new RT."""
    obj = await RTService(session).create(body.model_dump(exclude_unset=True))
    return success_response(RTRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/rt", response_model=Envelope[Page[RTRead]])
async def list_rt(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("rt:read")),
) -> dict:
    """List RT, paginated."""
    items, total = await RTService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, RTRead))


@router.get("/rt/{item_id}", response_model=Envelope[RTRead])
async def get_rt(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rt:manage")),
) -> dict:
    """Get a single RT by id."""
    obj = await RTService(session).get_or_404(item_id)
    return success_response(RTRead.model_validate(obj).model_dump(mode="json"))


@router.put("/rt/{item_id}", response_model=Envelope[RTRead])
async def update_rt(
    item_id: UUID,
    body: RTUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rt:manage")),
) -> dict:
    """Update a RT."""
    obj = await RTService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(RTRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/rt/{item_id}", response_model=Envelope[None])
async def delete_rt(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("rt:manage")),
) -> dict:
    """Soft-delete a RT."""
    await RTService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- Family Cards ----
@router.post("/family-cards", response_model=Envelope[FamilyCardRead])
async def create_family_card(
    body: FamilyCardCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("family_card:manage")),
) -> dict:
    """Create a new family card (KK)."""
    obj = await FamilyCardService(session).create(body.model_dump(exclude_unset=True))
    return success_response(FamilyCardRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/family-cards", response_model=Envelope[Page[FamilyCardRead]])
async def list_family_cards(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("family_card:manage")),
) -> dict:
    """List family cards, paginated."""
    items, total = await FamilyCardService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, FamilyCardRead))


@router.get("/family-cards/{item_id}", response_model=Envelope[FamilyCardRead])
async def get_family_card(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("family_card:manage")),
) -> dict:
    """Get a single family card by id."""
    obj = await FamilyCardService(session).get_or_404(item_id)
    return success_response(FamilyCardRead.model_validate(obj).model_dump(mode="json"))


@router.put("/family-cards/{item_id}", response_model=Envelope[FamilyCardRead])
async def update_family_card(
    item_id: UUID,
    body: FamilyCardUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("family_card:manage")),
) -> dict:
    """Update a family card."""
    obj = await FamilyCardService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(FamilyCardRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/family-cards/{item_id}", response_model=Envelope[None])
async def delete_family_card(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("family_card:manage")),
) -> dict:
    """Soft-delete a family card."""
    await FamilyCardService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- Residents (with search + filters; static routes precede {item_id}) ----
@router.post("/residents", response_model=Envelope[ResidentRead])
async def create_resident(
    body: ResidentCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:create")),
) -> dict:
    """Create a new resident."""
    obj = await ResidentService(session).create(body.model_dump(exclude_unset=True))
    return success_response(await _resident_read(session, obj), "Tersimpan")


@router.get("/residents", response_model=Envelope[Page[ResidentRead]])
async def list_residents(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    rt_id: UUID | None = Query(None),
    family_card_id: UUID | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List residents, paginated, with optional search and rt/family-card filters."""
    filters = {"rt_id": rt_id, "family_card_id": family_card_id}
    items, total = await ResidentService(session).list(
        p.page, p.size, filters=filters, search=search
    )
    return success_response({
        "items": [await _resident_read(session, i) for i in items],
        "total": total, "page": p.page, "size": p.size,
    })


@router.post("/residents/import", response_model=Envelope[ResidentImportResult])
async def import_residents(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:import")),
) -> dict:
    """Bulk-import residents from an uploaded xlsx file."""
    content = await file.read()
    result = await ResidentExcelService(session).import_bytes(content)
    return success_response(result, "Import selesai")


@router.get("/residents/export")
async def export_residents(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:export")),
) -> StreamingResponse:
    """Export all residents as an xlsx download."""
    data = await ResidentExcelService(session).export_bytes()
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=residents.xlsx"},
    )


@router.get("/residents/{item_id}", response_model=Envelope[ResidentRead])
async def get_resident(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """Get a single resident by id."""
    obj = await ResidentService(session).get_or_404(item_id)
    return success_response(await _resident_read(session, obj))


@router.put("/residents/{item_id}", response_model=Envelope[ResidentRead])
async def update_resident(
    item_id: UUID,
    body: ResidentUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:update")),
) -> dict:
    """Update a resident."""
    obj = await ResidentService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(await _resident_read(session, obj), "Diperbarui")


@router.delete("/residents/{item_id}", response_model=Envelope[None])
async def delete_resident(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:delete")),
) -> dict:
    """Soft-delete a resident."""
    await ResidentService(session).delete(item_id)
    return success_response(None, "Dihapus")
