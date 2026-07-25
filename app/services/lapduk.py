"""LAPDUK service: scoped upsert/list + Excel import/export.

Scoping rules (spec Bagian 7, data-driven via permission codes -- never a
hardcoded role/position check):
- "*" or "lapduk:read_all"/"lapduk:import": unrestricted (any RT).
- "lapduk:read_rw": restricted to RTs under the actor's own RW (`actor.rw_id`).
- "lapduk:manage_own": restricted to the actor's own RT (`actor.rt_id`).
- none of the above: no access at all.
"""
# NOTE: required because this class defines its own `list` method, which
# shadows the builtin `list` type for every `list[...]` annotation written
# later in the class body (evaluated eagerly at class-definition time
# without this import) -- same issue as app/services/user_management.py.
from __future__ import annotations

import io
import uuid
from typing import Any

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.core.logging import get_logger
from app.models.auth import User
from app.models.lapduk import LapdukReport
from app.models.master import RT

logger = get_logger("lapduk")

_FIELDS = ("jumlah_kk", "laki_laki", "perempuan", "pindah", "datang", "lahir", "meninggal")
IMPORT_COLUMNS = ("rt_id", "period", *_FIELDS)


class LapdukService:
    """Business logic for LAPDUK reports: scoped CRUD + Excel import/export."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _rt_ids_under_rw(self, rw_id: uuid.UUID) -> list[uuid.UUID]:
        stmt = select(RT.id).where(RT.rw_id == rw_id, RT.deleted_at.is_(None))
        return list((await self.session.scalars(stmt)).all())

    async def _authorize_write(
        self, actor: User, actor_permissions: list[str], rt_id: uuid.UUID
    ) -> None:
        """Enforce write scope for a single-row upsert: unrestricted actors
        may write any RT; `lapduk:manage_own` may only write their own RT.
        """
        if "*" in actor_permissions or "lapduk:import" in actor_permissions:
            return
        if "lapduk:manage_own" in actor_permissions and actor.rt_id == rt_id:
            return
        raise ForbiddenError("Anda tidak berwenang mengisi LAPDUK RT ini")

    async def _authorize_import_row(
        self, actor: User, actor_permissions: list[str], rt_id: uuid.UUID
    ) -> bool:
        """Return True if `actor` may import a row for `rt_id` (used per-row
        during bulk import, where an invalid row should be skipped with an
        error rather than aborting the whole file).
        """
        if "*" in actor_permissions or "lapduk:import" in actor_permissions:
            return True
        if "lapduk:read_rw" in actor_permissions:
            if actor.rw_id is None:
                return False
            return rt_id in await self._rt_ids_under_rw(actor.rw_id)
        if "lapduk:manage_own" in actor_permissions:
            return actor.rt_id == rt_id
        return False

    async def list(
        self, actor: User, actor_permissions: list[str], page: int, size: int,
        period: str | None, rw_id: uuid.UUID | None, rt_id: uuid.UUID | None,
    ) -> tuple[list[LapdukReport], int]:
        """List reports visible to `actor`, optionally filtered by period/rw/rt."""
        stmt = select(LapdukReport).where(LapdukReport.deleted_at.is_(None))

        if "*" in actor_permissions or "lapduk:read_all" in actor_permissions:
            pass
        elif "lapduk:read_rw" in actor_permissions:
            if actor.rw_id is None:
                raise ForbiddenError("Akun Anda tidak terhubung ke RW manapun")
            stmt = stmt.where(LapdukReport.rt_id.in_(await self._rt_ids_under_rw(actor.rw_id)))
        elif "lapduk:manage_own" in actor_permissions:
            if actor.rt_id is None:
                raise ForbiddenError("Akun Anda tidak terhubung ke RT manapun")
            stmt = stmt.where(LapdukReport.rt_id == actor.rt_id)
        else:
            raise ForbiddenError("Anda tidak memiliki akses LAPDUK")

        if period:
            stmt = stmt.where(LapdukReport.period == period)
        if rw_id is not None:
            stmt = stmt.where(LapdukReport.rt_id.in_(await self._rt_ids_under_rw(rw_id)))
        if rt_id is not None:
            stmt = stmt.where(LapdukReport.rt_id == rt_id)

        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = stmt.order_by(LapdukReport.period.desc()).offset((page - 1) * size).limit(size)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def upsert(
        self, actor: User, actor_permissions: list[str], data: dict[str, Any]
    ) -> LapdukReport:
        """Create or update the report for (rt_id, period)."""
        rt_id = data["rt_id"]
        period = data["period"]
        await self._authorize_write(actor, actor_permissions, rt_id)

        rt = await self.session.get(RT, rt_id)
        if rt is None or rt.deleted_at is not None:
            raise ValidationAppError("RT tidak ditemukan")

        existing = await self.session.scalar(
            select(LapdukReport).where(
                LapdukReport.rt_id == rt_id, LapdukReport.period == period,
                LapdukReport.deleted_at.is_(None),
            )
        )
        values = {k: data.get(k, 0) for k in _FIELDS}
        if existing:
            for k, v in values.items():
                setattr(existing, k, v)
            existing.submitted_by_user_id = actor.id
            obj = existing
        else:
            obj = LapdukReport(
                rt_id=rt_id, period=period, submitted_by_user_id=actor.id, **values
            )
            self.session.add(obj)
        await self.session.commit()
        logger.info("LAPDUK upsert rt_id=%s period=%s by=%s", rt_id, period, actor.id)
        return obj

    async def export_bytes(
        self, actor: User, actor_permissions: list[str],
        period: str | None, rw_id: uuid.UUID | None,
    ) -> bytes:
        """Export visible reports matching filters to xlsx bytes."""
        if not ({"*", "lapduk:export"} & set(actor_permissions)):
            raise ForbiddenError("Anda tidak berwenang mengekspor LAPDUK")
        items, _ = await self.list(actor, actor_permissions, page=1, size=100000,
                                    period=period, rw_id=rw_id, rt_id=None)
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "LAPDUK"
        ws.append(list(IMPORT_COLUMNS))
        for r in items:
            ws.append([str(r.rt_id), r.period, *[getattr(r, f) for f in _FIELDS]])
        buf = io.BytesIO()
        wb.save(buf)
        logger.info("LAPDUK export rows=%d by=%s", len(items), actor.id)
        return buf.getvalue()

    async def import_bytes(
        self, actor: User, actor_permissions: list[str], file_bytes: bytes
    ) -> dict:
        """Bulk upsert reports from an xlsx file; each row authorized/validated
        independently so one bad row doesn't abort the whole file.
        """
        if not ({"*", "lapduk:import", "lapduk:read_rw", "lapduk:manage_own"} & set(actor_permissions)):
            raise ForbiddenError("Anda tidak berwenang mengimpor LAPDUK")

        wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
        ws = wb.active
        header = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
        imported, errors = 0, []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            record = dict(zip(header, row))
            try:
                async with self.session.begin_nested():
                    rt_id = uuid.UUID(str(record.get("rt_id") or ""))
                    period = str(record.get("period") or "").strip()
                    if not period:
                        raise ValueError("period wajib diisi")
                    if not await self._authorize_import_row(actor, actor_permissions, rt_id):
                        raise ValueError("Tidak berwenang mengisi RT ini")
                    rt = await self.session.get(RT, rt_id)
                    if rt is None or rt.deleted_at is not None:
                        raise ValueError("RT tidak ditemukan")

                    existing = await self.session.scalar(
                        select(LapdukReport).where(
                            LapdukReport.rt_id == rt_id, LapdukReport.period == period,
                            LapdukReport.deleted_at.is_(None),
                        )
                    )
                    values = {f: int(record.get(f) or 0) for f in _FIELDS}
                    if existing:
                        for k, v in values.items():
                            setattr(existing, k, v)
                        existing.submitted_by_user_id = actor.id
                    else:
                        self.session.add(LapdukReport(
                            rt_id=rt_id, period=period, submitted_by_user_id=actor.id, **values
                        ))
                imported += 1
            except Exception as exc:  # row-level failure isolated
                errors.append({"row": idx, "message": str(exc)})
        await self.session.commit()
        logger.info("LAPDUK import imported=%d errors=%d by=%s", imported, len(errors), actor.id)
        return {"imported": imported, "errors": errors}
