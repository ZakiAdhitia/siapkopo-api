"""Read-only browsing endpoints for the per-letter-type domain master tables.

Gated by the existing `resident:read` permission (staff/admin already hold
it for the universal Resident master data) rather than a new permission
code -- these tables are just that same "master data" concept, split per
letter type (see app/models/master.py's module docstring).
"""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.repositories.auth import UserRepository
from app.services.audit_log import AuditLogService
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.domain_master import (
    MasterDomisiliRead,
    MasterKelahiranRead,
    MasterKematianRead,
    MasterKKRead,
    MasterNARead,
    MasterPindahRead,
    MasterSKURead,
    MasterUbahDataRead,
    MasterUHCRead,
)
from app.services.domain_master import (
    DOMAIN_MASTER_SERVICES,
    MasterDomisiliService,
    MasterKelahiranService,
    MasterKematianService,
    MasterKKService,
    MasterNAService,
    MasterPindahService,
    MasterSKUService,
    MasterUbahDataService,
    MasterUHCService,
    export_domain_master_excel,
)

router = APIRouter(tags=["domain-master-data"])


@router.get("/master-data/export")
async def export_domain_master(
    jenis: str = Query(..., description="|".join(DOMAIN_MASTER_SERVICES)),
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("resident:export")),
) -> StreamingResponse:
    """Export one domain master-data table (KK/domisili/NA/.../ubah_data) as
    an xlsx download (HASIL_UJICOBA_PERROLE.md, kades item 5)."""
    data = await export_domain_master_excel(session, jenis)
    actor = await UserRepository(session).get_by_id(UUID(current.id))
    await AuditLogService(session).record(
        actor, "export", f"Export master data '{jenis}' ke Excel", entity_type="master_data",
    )
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=master-{jenis}.xlsx"},
    )


@router.get("/master-domisili", response_model=Envelope[Page[MasterDomisiliRead]])
async def list_master_domisili(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List Domisili master data, paginated, searchable by NIK/nama."""
    items, total = await MasterDomisiliService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterDomisiliRead))


@router.get("/master-kelahiran", response_model=Envelope[Page[MasterKelahiranRead]])
async def list_master_kelahiran(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List Kelahiran master data, paginated, searchable by nama anak/NIK ortu."""
    items, total = await MasterKelahiranService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterKelahiranRead))


@router.get("/master-kematian", response_model=Envelope[Page[MasterKematianRead]])
async def list_master_kematian(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List Kematian master data, paginated, searchable by NIK/nama almarhum."""
    items, total = await MasterKematianService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterKematianRead))


@router.get("/master-sku", response_model=Envelope[Page[MasterSKURead]])
async def list_master_sku(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List SKU master data, paginated, searchable by NIK/nama pemohon."""
    items, total = await MasterSKUService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterSKURead))


@router.get("/master-na", response_model=Envelope[Page[MasterNARead]])
async def list_master_na(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List NA master data, paginated, searchable by NIK/nama calon or pasangan."""
    items, total = await MasterNAService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterNARead))


@router.get("/master-uhc", response_model=Envelope[Page[MasterUHCRead]])
async def list_master_uhc(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List UHC master data, paginated, searchable by NIK/nama pasien."""
    items, total = await MasterUHCService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterUHCRead))


@router.get("/master-pindah", response_model=Envelope[Page[MasterPindahRead]])
async def list_master_pindah(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List Pindah master data, paginated, searchable by NIK/nama pemohon."""
    items, total = await MasterPindahService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterPindahRead))


@router.get("/master-kk", response_model=Envelope[Page[MasterKKRead]])
async def list_master_kk(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List KK master data, paginated, searchable by No. KK/nama kepala keluarga."""
    items, total = await MasterKKService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterKKRead))


@router.get("/master-ubah-data", response_model=Envelope[Page[MasterUbahDataRead]])
async def list_master_ubah_data(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    search: str | None = Query(None),
    _=Depends(require_permission("resident:read")),
) -> dict:
    """List Ubah Data master data, paginated, searchable by NIK/nama."""
    items, total = await MasterUbahDataService(session).list(p.page, p.size, search=search)
    return success_response(build_page(items, total, p.page, p.size, MasterUbahDataRead))
