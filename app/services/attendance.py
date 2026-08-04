"""Staff daily attendance ("Absen") service."""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import extract, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.core.logging import get_logger
from app.models.attendance import Attendance, AttendanceStatus
from app.services.file_storage import FileStorageService
from app.services.master import _CrudService

logger = get_logger("attendance")


class AttendanceService(_CrudService):
    """Records and lists staff check-ins. Selfie upload/validation reuses
    `FileStorageService` (size/mime + blur check) exactly like submission
    attachments -- a check-in selfie must actually be legible, not just
    present, same anti-fraud rationale."""

    model = Attendance
    name = "Absen"

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)
        self.storage = FileStorageService()

    async def check_in(
        self, user_id: uuid.UUID, latitude: float, longitude: float,
        selfie_content: bytes, selfie_filename: str, selfie_content_type: str,
    ) -> Attendance:
        """Validate + store the selfie, then record today's check-in row.
        One check-in per user per day -- checked at the application layer
        (not a DB constraint, which would need to special-case soft-deleted
        rows) so a repeat click gets a clear error instead of a duplicate
        row."""
        today = datetime.now(timezone.utc).date()
        existing = await self.session.scalar(
            select(Attendance).where(
                Attendance.user_id == user_id, Attendance.attendance_date == today,
                Attendance.deleted_at.is_(None),
            )
        )
        if existing is not None:
            raise ValidationAppError("Anda sudah absen hari ini")
        self.storage.validate_upload(selfie_content, selfie_content_type)
        self.storage.check_not_blurry(selfie_content, selfie_content_type, "Selfie Absen")
        selfie_path = await self.storage.save(selfie_content, selfie_filename, subdir="attendance")
        return await self.create({
            "user_id": user_id,
            "attendance_date": datetime.now(timezone.utc).date(),
            "status": AttendanceStatus.HADIR,
            "latitude": latitude, "longitude": longitude, "selfie_path": selfie_path,
        })

    async def list_own(self, user_id: uuid.UUID, page: int, size: int) -> tuple[list[Any], int]:
        return await self.list(page, size, filters={"user_id": user_id})

    async def list_by_period(
        self, year: int, month: int, page: int = 1, size: int = 1000,
    ) -> tuple[list[Attendance], int]:
        """List every attendance row for a given calendar month, oldest
        first -- backs both the admin "Rekap Bulanan" view and the PDF
        export (which wants the whole month in one go, hence the large
        default size)."""
        stmt = (
            select(Attendance)
            .where(
                Attendance.deleted_at.is_(None),
                extract("year", Attendance.attendance_date) == year,
                extract("month", Attendance.attendance_date) == month,
            )
            .order_by(Attendance.attendance_date.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return rows, len(rows)

    async def get_selfie_file(
        self, attendance_id: uuid.UUID, actor_user_id: uuid.UUID, actor_permissions: list[str],
    ) -> tuple[bytes, Attendance]:
        """Return a check-in's selfie bytes -- own record, or any record
        with `attendance:read_all` (admin oversight)."""
        obj = await self.get_or_404(attendance_id)
        has_all = "*" in actor_permissions or "attendance:read_all" in actor_permissions
        if not has_all and obj.user_id != actor_user_id:
            raise ForbiddenError("Anda tidak punya akses ke data absen ini")
        if not obj.selfie_path:
            raise ForbiddenError("Absen ini tidak punya foto selfie (data hasil impor)")
        content = await self.storage.read(obj.selfie_path)
        return content, obj
