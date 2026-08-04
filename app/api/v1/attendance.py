"""Staff daily attendance ("Absen") endpoints."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.attendance import AttendanceImportResult, AttendanceRead
from app.schemas.common import Page
from app.services.attendance import AttendanceService
from app.services.attendance_excel import AttendanceExcelService
from app.services.attendance_report import AttendanceReportService
from app.services.master import VillageProfileService

router = APIRouter(tags=["attendance"])


async def _attendance_read(session: AsyncSession, obj) -> dict:
    user = await session.get(User, obj.user_id)
    data = AttendanceRead.model_validate(obj).model_dump(mode="json")
    data["user_full_name"] = user.full_name if user else None
    return data


@router.post("/attendance/check-in", response_model=Envelope[AttendanceRead])
async def check_in(
    latitude: float = Form(...),
    longitude: float = Form(...),
    selfie: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("attendance:create")),
) -> dict:
    """Record one "Absen" check-in: GPS coordinates + a required selfie.

    Only reachable when already authenticated (the permission dependency
    itself is the "sudah login" check) -- staff click "Absen" from inside
    the admin panel after a normal username/password login, not instead of
    one. Not available to Kepala Desa (position level 1) -- see
    `POSITION_PERMISSIONS` in the RBAC registry.
    """
    content = await selfie.read()
    obj = await AttendanceService(session).check_in(
        UUID(current.id), latitude, longitude,
        content, selfie.filename or "selfie.jpg", selfie.content_type or "image/jpeg",
    )
    return success_response(await _attendance_read(session, obj), "Absen berhasil dicatat")


@router.get("/attendance/me", response_model=Envelope[Page[AttendanceRead]])
async def list_my_attendance(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    current: CurrentUser = Depends(require_permission("attendance:create")),
) -> dict:
    """List the caller's own check-in history, newest first."""
    items, total = await AttendanceService(session).list_own(UUID(current.id), p.page, p.size)
    reads = [await _attendance_read(session, i) for i in items]
    return success_response({"items": reads, "total": total, "page": p.page, "size": p.size})


@router.get("/attendance", response_model=Envelope[Page[AttendanceRead]])
async def list_all_attendance(
    year: int | None = Query(None),
    month: int | None = Query(None, ge=1, le=12),
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _current: CurrentUser = Depends(require_permission("attendance:read_all")),
) -> dict:
    """List every staff member's check-ins (admin oversight / Kepala Desa
    read-only view), optionally scoped to one calendar month."""
    service = AttendanceService(session)
    if year and month:
        items, total = await service.list_by_period(year, month, p.page, p.size)
    else:
        items, total = await service.list(p.page, p.size)
    reads = [await _attendance_read(session, i) for i in items]
    return success_response({"items": reads, "total": total, "page": p.page, "size": p.size})


@router.get("/attendance/{attendance_id}/selfie")
async def download_selfie(
    attendance_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("attendance:create")),
) -> StreamingResponse:
    """Stream a check-in's selfie photo -- own record, or any record for
    an actor with `attendance:read_all`."""
    content, obj = await AttendanceService(session).get_selfie_file(
        attendance_id, UUID(current.id), current.permissions
    )
    content_type = "image/png" if obj.selfie_path.lower().endswith(".png") else "image/jpeg"
    return StreamingResponse(io.BytesIO(content), media_type=content_type)


@router.post("/attendance/import", response_model=Envelope[AttendanceImportResult])
async def import_attendance(
    year: int = Form(...),
    month: int = Form(..., ge=1, le=12),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("attendance:read_all")),
) -> dict:
    """Bulk-import a month's attendance from an xlsx matching the paper
    "Daftar Hadir" layout (NO | NAMA | day-of-month columns | Ket).
    Admin-only (`attendance:read_all`), same as the recap/export it feeds."""
    content = await file.read()
    result = await AttendanceExcelService(session).import_bytes(content, year, month)
    return success_response(result, "Impor absen selesai")


@router.get("/attendance/export-pdf")
async def export_attendance_pdf(
    year: int = Query(...),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("attendance:read_all")),
) -> StreamingResponse:
    """Export one month's "Daftar Hadir" as a printable PDF (landscape,
    NO/NAMA/day-of-month grid), matching the paper roster's layout."""
    profile = await VillageProfileService(session).get()
    pdf_bytes = await AttendanceReportService(session).export_pdf(year, month, profile)
    filename = f"daftar-hadir-{year}-{month:02d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
