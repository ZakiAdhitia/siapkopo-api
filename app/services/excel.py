"""Resident Excel import/export."""
import io
import uuid
from datetime import date, datetime
from typing import Any

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.master import ResidentService

logger = get_logger("master.excel")

COLUMNS = [
    "nik",
    "full_name",
    "gender",
    "birth_place",
    "birth_date",
    "occupation",
    "phone",
    "address",
]


class ResidentExcelService:
    """Import residents from and export residents to xlsx."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.residents = ResidentService(session)

    @staticmethod
    def _parse_date(value: Any) -> date | None:
        """Parse a cell value into a date, or None if empty."""
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    async def import_bytes(self, file_bytes: bytes, village_id: uuid.UUID) -> dict:
        """Import residents from an xlsx file; return counts + per-row errors."""
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
        ws = wb.active
        header = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
        imported, errors = 0, []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            record = dict(zip(header, row))
            try:
                # Each row runs inside its own SAVEPOINT so a DB-level failure
                # (e.g. IntegrityError from a duplicate NIK) only rolls back
                # this row instead of poisoning the whole outer transaction,
                # which would otherwise turn every later flush/commit into a
                # PendingRollbackError and lose all previously-valid rows.
                async with self.session.begin_nested():
                    nik = str(record.get("nik") or "").strip()
                    name = str(record.get("full_name") or "").strip()
                    if not nik or not name:
                        raise ValueError("nik dan full_name wajib diisi")
                    await self.residents.repo.create(
                        village_id=village_id,
                        nik=nik,
                        full_name=name,
                        gender=(record.get("gender") or None),
                        birth_place=(record.get("birth_place") or None),
                        birth_date=self._parse_date(record.get("birth_date")),
                        occupation=(record.get("occupation") or None),
                        phone=(str(record["phone"]) if record.get("phone") else None),
                        address=(record.get("address") or None),
                    )
                imported += 1
            except Exception as exc:  # row-level failure isolated
                errors.append({"row": idx, "message": str(exc)})
        await self.session.commit()
        logger.info(
            "Resident import village_id=%s imported=%d errors=%d",
            village_id,
            imported,
            len(errors),
        )
        return {"imported": imported, "errors": errors}

    async def export_bytes(self, filters: dict[str, Any] | None = None) -> bytes:
        """Export residents matching filters to xlsx bytes."""
        items, _ = await self.residents.list(page=1, size=100000, filters=filters or {})
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Residents"
        ws.append(COLUMNS)
        for r in items:
            ws.append(
                [
                    r.nik,
                    r.full_name,
                    r.gender,
                    r.birth_place,
                    r.birth_date.isoformat() if r.birth_date else "",
                    r.occupation,
                    r.phone,
                    r.address,
                ]
            )
        buf = io.BytesIO()
        wb.save(buf)
        logger.info("Resident export rows=%d", len(items))
        return buf.getvalue()
