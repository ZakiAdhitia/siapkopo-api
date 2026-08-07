"""Master data CRUD endpoints: village hierarchy (profile, RW, RT).

No population registry here (Resident/FamilyCard) -- removed 2026-08-06,
see app/models/master.py's module docstring. Per-letter-type domain master
browsing lives in app/api/v1/domain_master.py, unaffected by that removal.
"""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.master import (
    RTCreate,
    RTRead,
    RTUpdate,
    RWCreate,
    RWRead,
    RWUpdate,
    VillageProfileRead,
)
from app.services.master import RTService, RWService, VillageProfileService

router = APIRouter(tags=["master-data"])


# ---- Village Profile (fixed identity, no longer editable -- see
# app.models.master.VillageProfile's docstring) ----
@router.get("/village-profile", response_model=Envelope[VillageProfileRead])
async def get_village_profile(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("auth:me")),
) -> dict:
    """Get the village's identity data. Any authenticated user may read it."""
    obj = await VillageProfileService(session).get()
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"))


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
