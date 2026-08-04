"""Monthly "Daftar Hadir" (attendance roster) PDF export -- reproduces the
paper roster's layout (NO | NAMA | day-of-month grid | Ket) from digital
`Attendance` records.
"""
from __future__ import annotations

import calendar
import io
import socket
from datetime import date

from jinja2.sandbox import SandboxedEnvironment
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.attendance import Attendance
from app.models.auth import User
from app.models.master import VillageProfile
from app.services.attendance import AttendanceService
from app.services.auth import AuthService
from app.services.template_render._base import (
    _RENDER_SOCKET_TIMEOUT_SECONDS,
    _block_external_resources,
)

_BULAN_INDONESIA = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]

_STATUS_MARK = {"hadir": "&#10003;", "izin": "I", "sakit": "S", "alfa": "A"}

_TEMPLATE = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><style>
  @page { size: A4 landscape; margin: 1.2cm; }
  body { font-family: Helvetica, sans-serif; font-size: 9pt; color: #182420; }
  .judul { text-align: center; margin-bottom: 4px; }
  .judul .title { font-size: 13pt; font-weight: bold; }
  .judul .sub { font-size: 10.5pt; font-weight: bold; }
  .bulan { font-size: 9.5pt; font-weight: bold; margin: 8px 0 4px; }
  table.grid { width: 100%; border-collapse: collapse; table-layout: fixed; }
  th, td { border: 0.75pt solid #182420; text-align: center; padding: 2px 1px; font-size: 7.5pt; overflow: hidden; }
  th.nama, td.nama { text-align: left; padding-left: 4px; width: 95px; }
  th.no, td.no { width: 18px; }
  th.ket, td.ket { width: 32px; }
  th.day, td.day { width: 16px; }
  td.weekend, th.weekend { background: #f6c9c9; }
  .footer { width: 100%; margin-top: 26px; font-size: 9.5pt; }
  .footer td { border: none; text-align: left; vertical-align: top; padding: 0; font-size: 9.5pt; }
  .ttd-space { margin: 46px 0 4px; }
  .catatan { margin-top: 18px; font-size: 8.5pt; }
</style></head>
<body>
  <div class="judul">
    <div class="title">DAFTAR HADIR</div>
    <div class="sub">PERANGKAT DESA {{ village_name|upper }} KEC. {{ kecamatan|upper }}</div>
    <div class="sub">KABUPATEN {{ kabupaten|upper }} TAHUN {{ year }}</div>
  </div>
  <div class="bulan">BULAN : {{ month_name|upper }}</div>
  <table class="grid">
    <tr>
      <th class="no" rowspan="2">NO.</th>
      <th class="nama" rowspan="2">NAMA</th>
      <th colspan="{{ days|length }}">TANGGAL</th>
      <th class="ket" rowspan="2">Ket</th>
    </tr>
    <tr>
      {% for d in days %}<th class="day{{ ' weekend' if d.weekend else '' }}">{{ d.day }}</th>{% endfor %}
    </tr>
    {% for row in rows %}
    <tr>
      <td class="no">{{ loop.index }}</td>
      <td class="nama">{{ row.name|upper }}</td>
      {% for d in days %}
      <td class="day{{ ' weekend' if d.weekend else '' }}">{{ row.marks.get(d.day, '') | safe }}</td>
      {% endfor %}
      <td class="ket"></td>
    </tr>
    {% endfor %}
  </table>
  <table class="footer">
    <tr>
      <td style="width:50%;">
        Mengetahui :<br>KEPALA DESA {{ village_name|upper }}
        <div class="ttd-space">&nbsp;</div>
        ( ......................................... )
      </td>
      <td style="width:50%;">
        {{ village_name }}, {{ export_date }}<br>KAUR UMUM
        <div class="ttd-space">&nbsp;</div>
        ( ......................................... )
      </td>
    </tr>
  </table>
  <div class="catatan">
    Catatan :<br>
    Hadir ditandai otomatis dari absen digital (GPS + foto selfie).<br>
    I = Izin &nbsp;&nbsp; S = Sakit &nbsp;&nbsp; A = Alfa
  </div>
</body></html>
"""


class AttendanceReportService:
    """Builds the monthly "Daftar Hadir" PDF from `Attendance` rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.attendance = AttendanceService(session)
        self._env = SandboxedEnvironment(autoescape=True)

    async def _eligible_users(self) -> list[User]:
        """Every active user who currently holds `attendance:create` --
        same people the "Absen" check-in button is shown to. Resolved via
        the same Role ∪ Position logic as everywhere else in the RBAC
        system (`AuthService.permissions_for`), not a hardcoded role list.
        """
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None), User.is_active.is_(True))
            .options(
                selectinload(User.role),
                selectinload(User.position),
            )
        )
        users = list((await self.session.scalars(stmt)).all())
        auth = AuthService(self.session)
        eligible = []
        for user in users:
            perms = auth.permissions_for(user)
            if "*" in perms or "attendance:create" in perms:
                eligible.append(user)
        eligible.sort(key=lambda u: u.full_name or "")
        return eligible

    async def export_pdf(self, year: int, month: int, profile: VillageProfile) -> bytes:
        users = await self._eligible_users()
        rows_result, _ = await self.attendance.list_by_period(year, month, size=100000)

        marks_by_user: dict = {}
        for record in rows_result:
            marks_by_user.setdefault(record.user_id, {})[record.attendance_date.day] = (
                _STATUS_MARK.get(record.status.value, "")
            )

        days_in_month = calendar.monthrange(year, month)[1]
        days = [
            {"day": d, "weekend": date(year, month, d).weekday() >= 5}
            for d in range(1, days_in_month + 1)
        ]
        rows = [
            {"name": u.full_name, "marks": marks_by_user.get(u.id, {})}
            for u in users
        ]

        html = self._env.from_string(_TEMPLATE).render(
            village_name=profile.name, kecamatan=profile.kecamatan or "-",
            kabupaten=profile.kabupaten or "-", year=year,
            month_name=_BULAN_INDONESIA[month - 1], days=days, rows=rows,
            export_date=f"{date.today().day} {_BULAN_INDONESIA[date.today().month - 1]} {date.today().year}",
        )

        buffer = io.BytesIO()
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_RENDER_SOCKET_TIMEOUT_SECONDS)
            result = pisa.CreatePDF(html, dest=buffer, link_callback=_block_external_resources)
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if result.err:  # type: ignore[union-attr]
            raise AppException("Gagal membuat PDF daftar hadir", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()
