"""Render letter templates to PDF using sandboxed Jinja2 + xhtml2pdf."""
import io
from datetime import date

from jinja2.sandbox import SandboxedEnvironment
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village

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
        result = pisa.CreatePDF(full_html, dest=buffer)
        if result.err:
            raise AppException("Gagal merender PDF template", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()
