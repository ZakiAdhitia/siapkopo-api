"""Renderer for Surat Keterangan Kematian."""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, format_tanggal_indonesia

# Real title (2025 KEMATIAN/KEMATIAN.docx) is "SURAT KEMATIAN", not "Ket.
# Kematian" (template.name, the shorter UI menu label).
_LETTER_TITLE = "SURAT KEMATIAN"

# Unlike every other letter type, the real Surat Kematian specimen has no
# Pemerintah/Kecamatan/Desa kop at all -- just this small note where the kop
# would normally sit. Reusing the existing kop_template override mechanism
# (see NA's KUA_KOP) rather than adding a new "suppress kop" flag.
_KEMATIAN_KOP = """
  <div style="text-align:right; font-size:9pt; font-style:italic; margin-bottom:6px;">
    *) Untuk Yang Bersangkutan
  </div>
"""


class MatiRenderer(BaseLetterRenderer):
    """Renders Surat Keterangan Kematian to PDF."""

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
            kop_template=_KEMATIAN_KOP,
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
        as_html: bool = False,
    ) -> bytes | str:
        return self._render_document(
            profile=profile,
            data={**applicant, **answers},
            nomor=nomor,
            tanggal=tanggal,
            letter_title=_LETTER_TITLE,
            body_template=template.pdf_body_template,
            kop_template=_KEMATIAN_KOP,
            as_html=as_html,
        )
