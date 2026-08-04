"""Attendance Excel import -- digitizes a paper "Daftar Hadir" roster
(NO | NAMA | 1 | 2 | ... | <days of month> | Ket) into `Attendance` rows.
Mirrors `ResidentExcelService`'s per-row-savepoint import pattern.
"""
import io
from datetime import date
from typing import Any

import openpyxl
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.attendance import Attendance, AttendanceStatus
from app.models.auth import User

logger = get_logger("attendance.excel")

_STATUS_CODES = {"I": AttendanceStatus.IZIN, "S": AttendanceStatus.SAKIT, "A": AttendanceStatus.ALFA}


class AttendanceExcelService:
    """Import one month's attendance from an xlsx matching the paper
    roster's layout. Each day cell is either blank (no data, skipped), an
    I/S/A code, or any other non-empty mark (a signature/paraf on the real
    sheet) -- counted as HADIR. Idempotent per (user, day): a cell for a
    date that already has a record is skipped, not overwritten.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    def _day_columns(self, header_row: tuple) -> dict[int, int]:
        """Map day-of-month (1-31) -> column index, from any header cell
        that parses as a plain integer in range."""
        columns: dict[int, int] = {}
        for i, value in enumerate(header_row):
            if value is None:
                continue
            try:
                day = int(value)
            except (TypeError, ValueError):
                continue
            if 1 <= day <= 31:
                columns[day] = i
        return columns

    async def import_bytes(self, file_bytes: bytes, year: int, month: int) -> dict[str, Any]:
        """Import a month's roster; return counts + per-row errors."""
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
        ws = wb.active
        header = [c.value for c in ws[1]]
        name_col = next(
            (i for i, h in enumerate(header) if h and str(h).strip().lower() in ("nama", "name")), None
        )
        if name_col is None:
            return {"imported": 0, "errors": [{"row": 1, "message": 'Kolom "NAMA" tidak ditemukan pada baris pertama'}]}
        day_cols = self._day_columns(tuple(header))
        if not day_cols:
            return {"imported": 0, "errors": [{"row": 1, "message": "Tidak ada kolom tanggal (1-31) yang ditemukan"}]}

        imported, skipped, errors = 0, 0, []
        for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            name = str(row[name_col] or "").strip() if name_col < len(row) else ""
            if not name:
                continue
            try:
                async with self.session.begin_nested():
                    user = await self.session.scalar(
                        select(User).where(User.full_name.ilike(name), User.deleted_at.is_(None))
                    )
                    if user is None:
                        raise ValueError(f'Nama "{name}" tidak cocok dengan akun manapun')
                    for day, col_idx in day_cols.items():
                        try:
                            attendance_date = date(year, month, day)
                        except ValueError:
                            continue  # e.g. day 31 in a 30-day month
                        cell = row[col_idx] if col_idx < len(row) else None
                        if cell in (None, ""):
                            continue
                        existing = await self.session.scalar(
                            select(Attendance).where(
                                Attendance.user_id == user.id,
                                Attendance.attendance_date == attendance_date,
                                Attendance.deleted_at.is_(None),
                            )
                        )
                        if existing is not None:
                            skipped += 1
                            continue
                        code = str(cell).strip().upper()
                        status = _STATUS_CODES.get(code, AttendanceStatus.HADIR)
                        self.session.add(Attendance(
                            user_id=user.id, attendance_date=attendance_date, status=status,
                        ))
                        imported += 1
            except Exception as exc:  # row-level failure isolated via begin_nested
                errors.append({"row": row_idx, "message": str(exc)})
        await self.session.commit()
        logger.info(
            "Attendance import year=%d month=%d imported=%d skipped=%d errors=%d",
            year, month, imported, skipped, len(errors),
        )
        return {"imported": imported, "skipped": skipped, "errors": errors}
