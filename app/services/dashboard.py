"""Read-only dashboard aggregation over Submission, Redis-cached (Bagian 10).

Content is identical for every role with `dashboard:read` access -- only
menu/endpoint access is permission-gated, not the data itself (spec Bagian
10). Single-desa: no village_id scoping anywhere (multi-desa was removed).
"""
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redis import get_redis
from app.models.letter_template import LetterTemplate
from app.models.submission import Submission, SubmissionStatus

_CACHE_TTL_SECONDS = 45


class DashboardService:
    """Aggregation queries over Submission, cached briefly in Redis."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.redis = get_redis()

    async def _cached(self, key: str, compute) -> dict | list:
        cached = await self.redis.get(key)
        if cached is not None:
            return json.loads(cached)
        result = await compute()
        await self.redis.set(key, json.dumps(result), ex=_CACHE_TTL_SECONDS)
        return result

    async def _compute_stats(self) -> dict:
        rows = await self.session.execute(
            select(Submission.status, func.count()).group_by(Submission.status)
        )
        counts = {status.value: 0 for status in SubmissionStatus}
        for status, count in rows.all():
            counts[status.value] = count
        return {"total": sum(counts.values()), **counts}

    async def stats(self) -> dict:
        """Total submission counts by status."""
        return await self._cached("dashboard:stats", self._compute_stats)

    async def _compute_trend(self, days: int) -> list[dict]:
        since = datetime.now(timezone.utc) - timedelta(days=days - 1)
        rows = await self.session.execute(
            select(func.date(Submission.created_at), func.count())
            .where(Submission.created_at >= since)
            .group_by(func.date(Submission.created_at))
            .order_by(func.date(Submission.created_at))
        )
        counts = {str(d): c for d, c in rows.all()}
        today = datetime.now(timezone.utc).date()
        return [
            {"date": (today - timedelta(days=offset)).isoformat(),
             "count": counts.get((today - timedelta(days=offset)).isoformat(), 0)}
            for offset in range(days - 1, -1, -1)
        ]

    async def trend(self, days: int = 30) -> list[dict]:
        """Daily submission counts for the last `days` days."""
        return await self._cached(f"dashboard:trend:{days}", lambda: self._compute_trend(days))

    async def _compute_per_jenis(self) -> list[dict]:
        rows = await self.session.execute(
            select(LetterTemplate.name, func.count(Submission.id))
            .join(Submission, Submission.template_id == LetterTemplate.id)
            .group_by(LetterTemplate.name)
            .order_by(func.count(Submission.id).desc())
        )
        return [{"template_name": name, "count": count} for name, count in rows.all()]

    async def per_jenis(self) -> list[dict]:
        """Submission counts grouped by letter template (jenis surat)."""
        return await self._cached("dashboard:per_jenis", self._compute_per_jenis)

    async def _compute_inbox(self, limit: int) -> list[dict]:
        rows = await self.session.execute(
            select(Submission)
            .where(Submission.status == SubmissionStatus.PENDING)
            .order_by(Submission.created_at.asc())
            .limit(limit)
        )
        return [
            {
                "id": str(s.id), "template_id": str(s.template_id),
                "current_step_index": s.current_step_index,
                "created_at": s.created_at.isoformat(),
            }
            for s in rows.scalars().all()
        ]

    async def inbox(self, limit: int = 20) -> list[dict]:
        """Submissions currently awaiting action, oldest first."""
        return await self._cached(f"dashboard:inbox:{limit}", lambda: self._compute_inbox(limit))
