"""Render letter templates to PDF using sandboxed Jinja2 + xhtml2pdf."""
import io
import logging
import socket
from datetime import date

from jinja2.sandbox import SandboxedEnvironment
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village

logger = logging.getLogger(__name__)

# 1x1 transparent GIF, used as an inert stand-in for any resource xhtml2pdf
# is refused permission to resolve. It is a `data:` URI, so resolving it never
# touches the filesystem or the network.
_BLOCKED_RESOURCE_PLACEHOLDER = (
    "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="
)

# Defense-in-depth backstop: nothing in a single-page government letter render
# should legitimately need more than a few seconds. This bounds any blocking
# I/O xhtml2pdf might still attempt despite the link_callback below.
_RENDER_SOCKET_TIMEOUT_SECONDS = 5


def _block_external_resources(uri: str, _relative: str | None) -> str:
    """xhtml2pdf `link_callback`: refuse to resolve any external resource.

    The letter engine's HTML (letterhead + admin-authored ``pdf_body_template``)
    is fully self-contained inline HTML/CSS and never legitimately needs to load
    an external image, stylesheet, or font, nor read an arbitrary local file.
    Without this callback, xhtml2pdf performs a REAL outbound fetch (or local
    file read) for any ``<img src>``, ``<link>``, or CSS ``url()`` it finds --
    an SSRF/DoS vector that needs no ``{{ }}`` Jinja expression, so it entirely
    bypasses the sandboxed Jinja2 environment used to render the template.

    Important: returning a falsy value (``None``/``""``) here does NOT block
    resolution. xhtml2pdf's ``pisaFileObject.__init__`` only overrides the URI
    when the callback's return value is truthy (see
    ``xhtml2pdf/files.py``: ``if callback and (new := callback(uri, basepath))``);
    a falsy return falls through to xhtml2pdf's own default resolution, i.e. it
    still performs the fetch. So every external reference is instead redirected
    to an inert local ``data:`` URI, which xhtml2pdf resolves instantly, with no
    I/O -- the render still succeeds, just without that resource (a blank image
    in its place), rather than raising and aborting the whole PDF.

    Raising an exception from this callback is NOT an option either: it
    propagates straight out of ``pisa.CreatePDF`` and aborts the entire render,
    which is a much heavier failure mode than silently dropping one resource.
    """
    if isinstance(uri, str) and uri.startswith("data:"):
        # Already an inline resource; no I/O involved either way.
        return uri
    logger.warning("Blocked external resource resolution in letter template render: %r", uri)
    return _BLOCKED_RESOURCE_PLACEHOLDER

_LETTERHEAD = """<!DOCTYPE html>
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
  .ttd .nama { font-weight: bold; text-decoration: underline; }
</style>
</head>
<body>
  <div class="kop">
    <div class="instansi">PEMERINTAH KABUPATEN {{ kabupaten }}<br/>KECAMATAN {{ kecamatan }}</div>
    <div class="desa">DESA {{ village_name }}</div>
  </div>
  <div class="judul">
    <div class="title">{{ letter_title }}</div>
    <div class="nomor">Nomor: {{ nomor }}</div>
  </div>
  <div class="body">{{ body|safe }}</div>
  <div class="ttd">
    <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
    <div>Kepala Desa {{ village_name }}</div>
    <div class="nama">{{ signer_name }}</div>
  </div>
</body>
</html>
"""

_SAMPLE_APPLICANT = {
    "nama": "Nama Pemohon (Contoh)",
    "nik": "3516000000000000",
    "alamat": "Dusun Contoh, RT 000/RW 000",
    "no_kk": "3516000000000000",
}


class TemplateRenderService:
    """Renders a LetterTemplate's body into a full letter PDF document."""

    def __init__(self) -> None:
        self._env = SandboxedEnvironment(autoescape=True)

    def _sample_value(self, field: TemplateField) -> str:
        """Return a placeholder sample value for a template field, by type."""
        if field.field_type == FieldType.SELECT and field.options:
            return field.options[0]
        if field.field_type == FieldType.NUMBER:
            return "1"
        if field.field_type == FieldType.DATE:
            return date.today().isoformat()
        return f"{field.label} (Contoh)"

    def _sample_data(self, fields: list[TemplateField]) -> dict:
        """Build the full sample-data dict: applicant defaults + one entry per field."""
        data = dict(_SAMPLE_APPLICANT)
        for field in fields:
            data[field.field_key] = self._sample_value(field)
        return data

    def _preview_number(self, template: LetterTemplate) -> str:
        """Render the numbering pattern with seq=1 and the current year."""
        return template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=1, year=date.today().year
        )

    def render_preview(
        self, template: LetterTemplate, fields: list[TemplateField], village: Village
    ) -> bytes:
        """Render a PDF preview of a template using auto-generated sample data."""
        data = self._sample_data(fields)
        body_tpl = self._env.from_string(template.pdf_body_template)
        body_html = body_tpl.render(**data)

        letterhead_tpl = self._env.from_string(_LETTERHEAD)
        full_html = letterhead_tpl.render(
            kabupaten=village.kabupaten or "-",
            kecamatan=village.kecamatan or "-",
            village_name=village.name,
            letter_title=template.name.upper(),
            nomor=self._preview_number(template),
            body=body_html,
            tanggal=date.today().strftime("%d %B %Y"),
            signer_name="(Contoh Tanda Tangan)",
        )
        buffer = io.BytesIO()
        previous_timeout = socket.getdefaulttimeout()
        try:
            # Defense-in-depth: bound any blocking socket call xhtml2pdf might
            # still make, on top of the link_callback refusing external
            # resources outright. Restored in `finally` so this never leaks
            # into unrelated code elsewhere in the process.
            socket.setdefaulttimeout(_RENDER_SOCKET_TIMEOUT_SECONDS)
            result = pisa.CreatePDF(
                full_html, dest=buffer, link_callback=_block_external_resources
            )
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if result.err:
            raise AppException("Gagal merender PDF template", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()
