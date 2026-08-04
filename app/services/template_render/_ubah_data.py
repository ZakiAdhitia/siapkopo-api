"""Renderer for Perubahan Elemen Data Kependudukan (F-1.06 "Ubah Data").

Like Pindah, the real template (F-1.06.docx, "SURAT PERNYATAAN PERUBAHAN
ELEMEN DATA KEPENDUDUKAN") is a citizen's own sworn declaration, not a
Kepala Desa/Sekdes-issued certificate -- but unlike Pindah's, it carries
only ONE signature ("Yang Membuat Pernyataan" + Materai), with no RT/RW
countersignature block in the real specimen.
"""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, format_tanggal_indonesia

_LETTER_TITLE = "SURAT PERNYATAAN PERUBAHAN ELEMEN DATA KEPENDUDUKAN"

# Signed by the applicant themselves only -- no desa/RT countersignature in
# the real F-1.06 specimen (contrast PindahRenderer's DUAL_SIGNATURE_FOOTER).
UBAH_DATA_FOOTER = """
  <div class="ttd" style="text-align:center; margin-top:40px;">
    <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
    <div>Yang Membuat Pernyataan,</div>
    <div style="margin-top:6px; font-size:10pt;">Materai Rp 10.000</div>
    <div class="tanda-tangan-kosong" style="margin-top:48px;">( ......................................... )</div>
  </div>
"""


class UbahDataRenderer(BaseLetterRenderer):
    """Renders the Ubah Data (F-1.06) SURAT PERNYATAAN to PDF."""

    def render_preview(
        self,
        template: LetterTemplate,
        fields: list[TemplateField],
        profile: VillageProfile,
    ) -> bytes:
        return self._render_document(
            profile=profile,
            data=self._sample_data(fields),
            nomor=self._preview_number(template),
            tanggal=format_tanggal_indonesia(date.today()),
            letter_title=_LETTER_TITLE,
            body_template=template.pdf_body_template,
            footer_template=UBAH_DATA_FOOTER,
        )

    def render_issued(
        self,
        *,
        template: LetterTemplate,
        profile: VillageProfile,
        answers: dict,
        applicant: dict,
        nomor: str,
        tanggal: str,
    ) -> bytes:
        return self._render_document(
            profile=profile,
            data={**applicant, **answers},
            nomor=nomor,
            tanggal=tanggal,
            letter_title=_LETTER_TITLE,
            body_template=template.pdf_body_template,
            footer_template=UBAH_DATA_FOOTER,
        )
