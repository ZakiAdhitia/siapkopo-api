"""Shared infrastructure for the letter PDF rendering engine.

All per-domain renderer modules import from here so the xhtml2pdf security
hardening (link_callback + socket timeout) is defined and enforced in exactly
one place.
"""
from __future__ import annotations

import io
import logging
import socket

from jinja2.sandbox import SandboxedEnvironment
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import VillageProfile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Indonesian date formatting
# ---------------------------------------------------------------------------
# Every real village letter template date-stamps itself "Kopo, 15 Juli 2026"
# -- Indonesian month names, not English -- but `date.strftime("%B")` follows
# the process locale (typically "C"/English on a server), so this can't be
# left to strftime.
_BULAN_INDONESIA = [
    "Januari", "Februari", "Maret", "April", "Mei", "Juni",
    "Juli", "Agustus", "September", "Oktober", "November", "Desember",
]


def format_tanggal_indonesia(d) -> str:
    """Format a date/datetime as "15 Juli 2026" (Indonesian month name)."""
    return f"{d.day} {_BULAN_INDONESIA[d.month - 1]} {d.year}"


def _ddmmyyyy(value) -> str:
    """Jinja filter: "1995-05-15" -> "15-05-1995". Passes through anything
    that isn't a plain ISO date string (None, already-formatted text, etc.)
    unchanged rather than raising -- template bodies should never 500 on a
    field that happens to be blank or non-date."""
    if not value or not isinstance(value, str):
        return value or "-"
    parts = value.split("-")
    if len(parts) != 3 or len(parts[0]) != 4:
        return value
    year, month, day = parts
    return f"{day}-{month}-{year}"


_HARI_INDONESIA = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]


def _hari_indonesia(value) -> str:
    """Jinja filter: ISO date string -> Indonesian weekday name, e.g.
    "2026-06-01" -> "Senin". Real letter templates ("Pada hari ---Senin---")
    always print this alongside the date; not worth a separate form field
    since it's always derivable from the date itself."""
    import datetime as _dt
    if not value or not isinstance(value, str):
        return "-"
    try:
        d = _dt.date.fromisoformat(value[:10])
    except ValueError:
        return "-"
    return _HARI_INDONESIA[d.weekday()]


# ---------------------------------------------------------------------------
# xhtml2pdf security hardening
# ---------------------------------------------------------------------------

# 1x1 transparent GIF used as inert stand-in for any blocked external resource.
# It is a `data:` URI so resolving it never touches the filesystem or network.
_BLOCKED_RESOURCE_PLACEHOLDER = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
)

# Defense-in-depth backstop: nothing in a single-page government letter render
# should legitimately need more than a few seconds.  This bounds any blocking
# I/O xhtml2pdf might still attempt despite the link_callback below.
_RENDER_SOCKET_TIMEOUT_SECONDS = 5


def _block_external_resources(uri: str, _relative: str | None) -> str:
    """xhtml2pdf `link_callback`: refuse to resolve any external resource.

    The letter engine's HTML (letterhead + admin-authored ``pdf_body_template``)
    is fully self-contained inline HTML/CSS and never legitimately needs to load
    an external image, stylesheet, or font, nor read an arbitrary local file.
    Without this callback, xhtml2pdf performs a REAL outbound fetch (or local
    file read) for any ``<img src>``, ``<link>``, or CSS ``url()`` it finds --
    an SSRF/DoS vector that entirely bypasses the sandboxed Jinja2 environment.

    Important: returning a falsy value (``None``/``""``) here does NOT block
    resolution -- xhtml2pdf only overrides the URI when the callback returns a
    truthy value.  So every external reference is redirected to an inert local
    ``data:`` URI instead.
    """
    if isinstance(uri, str) and uri.startswith("data:"):
        return uri
    logger.warning("Blocked external resource resolution in letter template render: %r", uri)
    return _BLOCKED_RESOURCE_PLACEHOLDER


# ---------------------------------------------------------------------------
# Shared letterhead template (Jinja2)
# ---------------------------------------------------------------------------

LETTERHEAD = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page { size: A4; margin: 2.5cm 2cm; }
  body { font-family: Helvetica, sans-serif; font-size: 12pt; color: #182420; }
  .kop { text-align: center; border-bottom: 3px solid #182420; padding-bottom: 10px; margin-bottom: 20px; }
  .kop .instansi { font-size: 11pt; font-weight: bold; letter-spacing: 1px; }
  .kop .desa { font-size: 13pt; font-weight: bold; }
  .judul { text-align: center; margin: 20px 0; }
  .judul .title { font-size: 13pt; font-weight: bold; text-decoration: underline; }
  .judul .nomor { font-size: 11pt; margin-top: 4px; }
  .body { text-align: justify; line-height: 1.6; margin-bottom: 40px; }
  .ttd { text-align: right; margin-top: 40px; }
  .ttd .tempat-tanggal { margin-bottom: 60px; }
  .ttd .tanda-tangan-kosong { font-weight: bold; }
  .ttd .ttd-label { font-size: 10pt; margin-top: 4px; }
</style>
</head>
<body>
  {% if kop %}{{ kop|safe }}{% else %}
  <div class="kop">
    <div class="instansi">PEMERINTAH KABUPATEN {{ kabupaten|upper }}<br/>KECAMATAN {{ kecamatan|upper }}</div>
    <div class="desa">DESA {{ village_name|upper }}</div>
  </div>
  {% endif %}
  <div class="judul">
    <div class="title">{{ letter_title }}</div>
    <div class="nomor">Nomor: {{ nomor }}</div>
  </div>
  <div class="body">{{ body|safe }}</div>
  {% if footer %}{{ footer|safe }}{% else %}
  <div class="ttd">
    <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
    <div>A/n. Kepala Desa {{ village_name }},</div>
    <div>Sekretaris Desa,</div>
    <div class="tanda-tangan-kosong" style="margin-top:56px;">( ......................................... )</div>
  </div>
  {% endif %}
</body>
</html>
"""

# Legal-basis header for NA's KUA-mandated sub-forms (N.1/N.4/N.5) -- these
# are prescribed by Kepdirjen Bimas Islam No. 473/2020, not the village's
# own letterhead, so they replace the usual Pemerintah/Kecamatan/Desa kop.
KUA_KOP = """
  <div style="text-align:center; font-size:10.5pt; font-weight:bold; margin-bottom:14px;">
    KEPUTUSAN DIREKTUR JENDERAL BIMBINGAN MASYARAKAT ISLAM NOMOR 473 TAHUN 2020<br/>
    TENTANG PETUNJUK TEKNIS PELAKSANAAN PENCATATAN PERNIKAHAN
  </div>
  <table style="width:100%; font-size:11pt; margin-bottom:10px;">
    <tr><td style="width:35%;">KANTOR DESA/KELURAHAN</td><td>: {{ village_name|upper }}</td></tr>
    <tr><td>KECAMATAN</td><td>: {{ kecamatan|upper }}</td></tr>
    <tr><td>KABUPATEN/KOTA</td><td>: {{ kabupaten|upper }}</td></tr>
    <tr><td>PROVINSI</td><td>: {{ provinsi|upper }}</td></tr>
  </table>
"""

# Signed by Kepala Desa directly (no "A/n. ... Sekretaris Desa" delegation)
# -- N.1 is the one NA sub-document the real template shows the Kepala Desa
# signing in person, not delegating to the Sekdes like every other letter.
KEPALA_DESA_DIRECT_FOOTER = """
  <div class="ttd">
    <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
    <div>Kepala Desa {{ village_name }},</div>
    <div class="tanda-tangan-kosong" style="margin-top:56px;">( ......................................... )</div>
  </div>
"""

# Two side-by-side blank-signature blocks (e.g. "Yang Membuat Pernyataan" +
# "Mengetahui, Ketua RT") for letters not signed by Kepala Desa/Sekretaris
# Desa -- see PindahRenderer, whose real template is a citizen's own
# declaration countersigned by the RT, not a village-issued certificate.
DUAL_SIGNATURE_FOOTER = """
  <div class="ttd" style="display:flex; justify-content:space-between; text-align:center; margin-top:40px;">
    <div style="width:45%;">
      <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
      <div class="tanda-tangan-kosong">( ......................................... )</div>
      <div class="ttd-label">{{ left_label }}</div>
    </div>
    <div style="width:45%;">
      <div class="tempat-tanggal">&nbsp;</div>
      <div class="tanda-tangan-kosong">( ......................................... )</div>
      <div class="ttd-label">{{ right_label }}</div>
    </div>
  </div>
"""

# ---------------------------------------------------------------------------
# Shared sample applicant data (used for preview rendering)
# ---------------------------------------------------------------------------

_SAMPLE_APPLICANT: dict[str, str] = {
    "nama": "Nama Pemohon (Contoh)",
    "nik": "3516000000000000",
    "alamat": "Dusun Contoh, RT 000/RW 000",
    "no_kk": "3516000000000000",
}


# ---------------------------------------------------------------------------
# BaseLetterRenderer
# ---------------------------------------------------------------------------

class BaseLetterRenderer:
    """Mixin that provides the low-level PDF rendering engine.

    All per-domain renderer classes inherit from this so the xhtml2pdf
    hardening lives in exactly one place.  Subclasses implement ``render()``
    and, optionally, ``render_sub_document()``.
    """

    def __init__(self, env: SandboxedEnvironment) -> None:
        self._env = env

    # ------------------------------------------------------------------
    # Low-level engine
    # ------------------------------------------------------------------

    def _render_document(
        self,
        *,
        profile: VillageProfile,
        data: dict,
        nomor: str,
        tanggal: str,
        letter_title: str,
        body_template: str,
        footer_template: str | None = None,
        kop_template: str | None = None,
        as_html: bool = False,
    ) -> bytes | str:
        """Interpolate the body template, wrap in the letterhead, and render to PDF.

        `footer_template` optionally replaces the default Kepala Desa/Sekdes
        signature block (e.g. DUAL_SIGNATURE_FOOTER), and `kop_template`
        optionally replaces the default Pemerintah/Kecamatan/Desa header
        (e.g. KUA_KOP) -- both rendered with the same `data` context, so
        they can reference answer fields like `{{ nama }}`.

        `as_html=True` returns the interpolated HTML string directly,
        skipping the xhtml2pdf conversion entirely -- used by Tahap 4's
        live pratinjau (ALUR_REVIEW_INPUT_MASTER.md), which needs the
        letter's real shape without paying the PDF-render cost. The
        xhtml2pdf-specific hardening below (link_callback, socket timeout)
        is irrelevant in this mode since pisa.CreatePDF is never reached.
        """
        # village_name/kecamatan/kabupaten are available to every body
        # template too (not just the letterhead) -- several real templates
        # (e.g. Domisili's "...Desa Kopo Kecamatan Cisarua, Kabupaten Bogor")
        # repeat these inside the body, not just the letterhead kop.
        body_tpl = self._env.from_string(body_template)
        body_html = body_tpl.render(
            village_name=profile.name, kecamatan=profile.kecamatan or "-",
            kabupaten=profile.kabupaten or "-", provinsi=profile.provinsi or "-",
            **data,
        )

        footer_html = None
        if footer_template:
            footer_html = self._env.from_string(footer_template).render(
                village_name=profile.name, tanggal=tanggal, **data,
            )
        kop_html = None
        if kop_template:
            kop_html = self._env.from_string(kop_template).render(
                village_name=profile.name, kecamatan=profile.kecamatan or "-",
                kabupaten=profile.kabupaten or "-", provinsi=profile.provinsi or "-",
            )

        letterhead_tpl = self._env.from_string(LETTERHEAD)
        full_html = letterhead_tpl.render(
            kabupaten=profile.kabupaten or "-",
            kecamatan=profile.kecamatan or "-",
            village_name=profile.name,
            letter_title=letter_title,
            nomor=nomor,
            body=body_html,
            tanggal=tanggal,
            footer=footer_html,
            kop=kop_html,
        )

        if as_html:
            return full_html

        buffer = io.BytesIO()
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_RENDER_SOCKET_TIMEOUT_SECONDS)
            result = pisa.CreatePDF(
                full_html, dest=buffer, link_callback=_block_external_resources
            )
        finally:
            socket.setdefaulttimeout(previous_timeout)

        if result.err:  # type: ignore[union-attr]  # xhtml2pdf stubs wrong; runtime returns pisaDocument
            raise AppException("Gagal merender PDF surat", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()

    # ------------------------------------------------------------------
    # Sample-data helpers (used by preview renderers)
    # ------------------------------------------------------------------

    @staticmethod
    def _sample_value(field: TemplateField) -> str:
        """Return a placeholder sample value for a template field, by type."""
        from datetime import date as _date
        if field.field_type == FieldType.SELECT and field.options:
            return field.options[0]
        if field.field_type == FieldType.NUMBER:
            return "1"
        if field.field_type == FieldType.DATE:
            return _date.today().isoformat()
        return f"{field.label} (Contoh)"

    def _sample_data(self, fields: list[TemplateField]) -> dict:
        """Build the full sample-data dict: applicant defaults + one entry per field."""
        data = dict(_SAMPLE_APPLICANT)
        for field in fields:
            data[field.field_key] = self._sample_value(field)
        return data

    @staticmethod
    def _preview_number(template: LetterTemplate) -> str:
        """Render the numbering pattern with seq=1 and the current year."""
        from datetime import date as _date
        return template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=1, year=_date.today().year
        )
