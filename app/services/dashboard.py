"""Read-only dashboard aggregation over Submission (Bagian 10).

Content is identical for every role with `dashboard:read` access -- only
menu/endpoint access is permission-gated, not the data itself (spec Bagian
10). Single-desa: no village_id scoping anywhere (multi-desa was removed).
"""
import io
import socket
from datetime import datetime, timedelta, timezone

import openpyxl
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.letter_template import LetterTemplate
from app.models.master import VillageProfile
from app.models.submission import Submission, SubmissionStatus
from app.services.template_render._base import (
    _RENDER_SOCKET_TIMEOUT_SECONDS,
    _block_external_resources,
    format_tanggal_indonesia,
)

_STATUS_LABELS = {"pending": "Sedang Diproses", "issued": "Terbit", "rejected": "Ditolak"}


class DashboardService:
    """Aggregation queries over Submission.

    No caching layer -- these are cheap COUNT/GROUP BY queries over a
    single village's submissions, not worth the staleness tradeoff of a
    cache at this app's scale.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def stats(self) -> dict:
        """Total submission counts by status."""
        rows = await self.session.execute(
            select(Submission.status, func.count()).group_by(Submission.status)
        )
        counts = {status.value: 0 for status in SubmissionStatus}
        for status, count in rows.all():
            counts[status.value] = count
        return {"total": sum(counts.values()), **counts}

    async def trend(self, days: int = 30) -> list[dict]:
        """Daily submission counts for the last `days` days."""
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

    async def per_jenis(self) -> list[dict]:
        """Submission counts grouped by letter template (jenis surat)."""
        rows = await self.session.execute(
            select(LetterTemplate.name, func.count(Submission.id))
            .join(Submission, Submission.template_id == LetterTemplate.id)
            .group_by(LetterTemplate.name)
            .order_by(func.count(Submission.id).desc())
        )
        return [{"template_name": name, "count": count} for name, count in rows.all()]

    async def inbox(self, limit: int = 20) -> list[dict]:
        """Submissions currently awaiting action, oldest first."""
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

    async def _report_data(self) -> tuple[dict, list[dict], list[dict]]:
        """Shared data for both export formats -- exactly what the Laporan
        page itself shows (stat cards + 30-day trend), plus per-jenis
        (HASIL_UJICOBA_PERROLE.md, bendahara item 7: "belum bisa export
        excel dan pdf")."""
        stats = await self.stats()
        trend = await self.trend(30)
        per_jenis = await self.per_jenis()
        return stats, trend, per_jenis

    async def export_excel(self) -> bytes:
        """Export the Laporan page's data (status summary, per-jenis,
        30-day trend) to a 3-sheet xlsx workbook."""
        stats, trend, per_jenis = await self._report_data()

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Ringkasan"
        ws.append(["Status", "Jumlah"])
        ws.append(["Total Pengajuan", stats["total"]])
        for key, label in _STATUS_LABELS.items():
            ws.append([label, stats.get(key, 0)])

        ws2 = wb.create_sheet("Per Jenis Surat")
        ws2.append(["Jenis Surat", "Jumlah Pengajuan"])
        for row in per_jenis:
            ws2.append([row["template_name"], row["count"]])

        ws3 = wb.create_sheet("Tren Harian (30 Hari)")
        ws3.append(["Tanggal", "Jumlah Pengajuan"])
        for row in trend:
            ws3.append([row["date"], row["count"]])

        buffer = io.BytesIO()
        wb.save(buffer)
        return buffer.getvalue()

    async def export_pdf(self, profile: VillageProfile) -> bytes:
        """Export the same Laporan data as a printable PDF summary."""
        stats, trend, per_jenis = await self._report_data()
        today = datetime.now(timezone.utc)

        rows_status = "".join(
            f"<tr><td>{label}</td><td style='text-align:right;'>{stats.get(key, 0)}</td></tr>"
            for key, label in _STATUS_LABELS.items()
        )
        rows_jenis = "".join(
            f"<tr><td>{row['template_name']}</td><td style='text-align:right;'>{row['count']}</td></tr>"
            for row in per_jenis
        ) or "<tr><td colspan='2'>Belum ada data.</td></tr>"
        rows_trend = "".join(
            f"<tr><td>{row['date']}</td><td style='text-align:right;'>{row['count']}</td></tr>"
            for row in trend if row["count"] > 0
        ) or "<tr><td colspan='2'>Belum ada data.</td></tr>"

        html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  @page {{ size: A4; margin: 2cm; }}
  body {{ font-family: Helvetica, sans-serif; font-size: 10.5pt; color: #182420; }}
  h1 {{ font-size: 15pt; text-align: center; margin-bottom: 2px; }}
  .sub {{ text-align: center; font-size: 10pt; color: #555; margin-bottom: 18px; }}
  h2 {{ font-size: 12pt; margin: 18px 0 6px; border-bottom: 1px solid #182420; padding-bottom: 3px; }}
  table {{ width: 100%; border-collapse: collapse; }}
  td, th {{ border: 0.5pt solid #999; padding: 4px 8px; }}
  th {{ background: #EAF6FF; text-align: left; }}
</style></head>
<body>
  <h1>Laporan Pengajuan Surat</h1>
  <div class="sub">Desa {profile.name} -- dicetak {format_tanggal_indonesia(today)}</div>
  <h2>Ringkasan Status (Total: {stats['total']})</h2>
  <table><tr><th>Status</th><th>Jumlah</th></tr>{rows_status}</table>
  <h2>Per Jenis Surat</h2>
  <table><tr><th>Jenis Surat</th><th>Jumlah</th></tr>{rows_jenis}</table>
  <h2>Tren Harian (30 Hari Terakhir)</h2>
  <table><tr><th>Tanggal</th><th>Jumlah</th></tr>{rows_trend}</table>
</body></html>"""

        buffer = io.BytesIO()
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_RENDER_SOCKET_TIMEOUT_SECONDS)
            result = pisa.CreatePDF(html, dest=buffer, link_callback=_block_external_resources)
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if result.err:  # type: ignore[union-attr]
            raise AppException("Gagal membuat PDF laporan", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()
