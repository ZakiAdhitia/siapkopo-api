"""Audit trail recording + querying (CLAUDE.md "Logging" section)."""
from __future__ import annotations

import uuid
from datetime import date, datetime, time, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit_log import AuditLog
from app.models.auth import User

logger = get_logger("audit_log")


class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def record(
        self, actor: User | None, action: str, description: str,
        entity_type: str | None = None, entity_id: str | None = None,
    ) -> None:
        """Append one audit entry. Never raises into the caller's flow --
        a logging failure must not block the action it's describing (e.g.
        a submission approval should still succeed even if, hypothetically,
        writing the audit row failed for some unrelated reason)."""
        try:
            self.session.add(AuditLog(
                actor_user_id=actor.id if actor else None,
                actor_name=actor.full_name if actor else "Sistem",
                action=action, entity_type=entity_type,
                entity_id=str(entity_id) if entity_id is not None else None,
                description=description,
            ))
            await self.session.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Gagal mencatat audit log: action=%s description=%s", action, description)
            await self.session.rollback()

    async def list(
        self, page: int = 1, size: int = 20, search: str | None = None,
        action: str | None = None, date_from: date | None = None, date_to: date | None = None,
    ) -> tuple[list[AuditLog], int]:
        stmt = select(AuditLog)
        if search:
            like = f"%{search}%"
            stmt = stmt.where(or_(AuditLog.actor_name.ilike(like), AuditLog.description.ilike(like)))
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if date_from:
            stmt = stmt.where(AuditLog.created_at >= datetime.combine(date_from, time.min, timezone.utc))
        if date_to:
            stmt = stmt.where(AuditLog.created_at <= datetime.combine(date_to, time.max, timezone.utc))
        count_stmt = stmt.with_only_columns(func.count()).order_by(None)
        total = await self.session.scalar(count_stmt)
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * size).limit(size)
        items = list((await self.session.scalars(stmt)).all())
        return items, total
