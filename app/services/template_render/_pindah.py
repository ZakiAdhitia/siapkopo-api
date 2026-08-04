"""Renderer for the outbound move (pindah) letter.

The real template (SURAT PINDAH 2024.docx) is a "SURAT PERNYATAAN" the
citizen signs themselves, countersigned by the Ketua RT -- unlike every
other letter type, it is NOT issued/signed by Kepala Desa/Sekdes. The
village still prints it on its own letterhead (filled in at the desa
office), so the kop stays standard; only the title and signature footer
differ.
"""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, format_tanggal_indonesia

_LETTER_TITLE = "SURAT PERNYATAAN"

# Signed by the applicant themselves + countersigned by the Ketua RT --
# roles only (no name printed a second time; it's already in the body's
# "Nama Lengkap" field, and this is a blank form for wet signature anyway).
PINDAH_FOOTER = """
  <div class="ttd" style="display:flex; justify-content:space-between; text-align:center; margin-top:40px;">
    <div style="width:45%;">
      <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
      <div class="tanda-tangan-kosong">( ......................................... )</div>
      <div class="ttd-label">Yang Membuat Pernyataan</div>
    </div>
    <div style="width:45%;">
      <div class="tempat-tanggal">&nbsp;</div>
      <div class="tanda-tangan-kosong">( ......................................... )</div>
      <div class="ttd-label">Mengetahui, Ketua RT</div>
    </div>
  </div>
"""


class PindahRenderer(BaseLetterRenderer):
    """Renders the pindah SURAT PERNYATAAN to PDF."""

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
            footer_template=PINDAH_FOOTER,
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
            footer_template=PINDAH_FOOTER,
        )
