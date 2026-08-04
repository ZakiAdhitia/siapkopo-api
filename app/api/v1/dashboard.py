"""Read-only dashboard aggregation endpoints (Bagian 10)."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.repositories.auth import UserRepository
from app.schemas.dashboard import (
    DashboardInboxItem, DashboardPerJenis, DashboardStats, DashboardTrendPoint,
)
from app.services.audit_log import AuditLogService
from app.services.dashboard import DashboardService
from app.services.master import VillageProfileService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", response_model=Envelope[DashboardStats])
async def get_dashboard_stats(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:read")),
) -> dict:
    """Total submission counts by status."""
    return success_response(await DashboardService(session).stats())


@router.get("/trend", response_model=Envelope[list[DashboardTrendPoint]])
async def get_dashboard_trend(
    days: int = Query(30, ge=1, le=365),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:read")),
) -> dict:
    """Daily submission counts for the last `days` days."""
    return success_response(await DashboardService(session).trend(days))


@router.get("/per-jenis", response_model=Envelope[list[DashboardPerJenis]])
async def get_dashboard_per_jenis(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:read")),
) -> dict:
    """Submission counts grouped by letter template (jenis surat)."""
    return success_response(await DashboardService(session).per_jenis())


@router.get("/inbox", response_model=Envelope[list[DashboardInboxItem]])
async def get_dashboard_inbox(
    limit: int = Query(20, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("dashboard:read")),
) -> dict:
    """Submissions currently awaiting action, oldest first."""
    return success_response(await DashboardService(session).inbox(limit))


@router.get("/export/excel")
async def export_dashboard_excel(
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("dashboard:read")),
) -> StreamingResponse:
    """Export the Laporan page's data as xlsx (HASIL_UJICOBA_PERROLE.md,
    bendahara item 7)."""
    data = await DashboardService(session).export_excel()
    actor = await UserRepository(session).get_by_id(UUID(current.id))
    await AuditLogService(session).record(actor, "export", "Export laporan pengajuan ke Excel", entity_type="laporan")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=laporan-pengajuan.xlsx"},
    )


@router.get("/export/pdf")
async def export_dashboard_pdf(
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("dashboard:read")),
) -> StreamingResponse:
    """Export the Laporan page's data as a printable PDF."""
    profile = await VillageProfileService(session).get()
    data = await DashboardService(session).export_pdf(profile)
    actor = await UserRepository(session).get_by_id(UUID(current.id))
    await AuditLogService(session).record(actor, "export", "Export laporan pengajuan ke PDF", entity_type="laporan")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=laporan-pengajuan.pdf"},
    )
