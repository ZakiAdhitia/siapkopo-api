"""Renderer for Surat Keterangan Domisili."""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, format_tanggal_indonesia

# Real title is "KETERANGAN TINGGAL SEMENTARA" (2025 DOMISILI/DOMISILI.doc),
# not "SURAT DOMISILI" (template.name, used for the UI menu label instead).
_LETTER_TITLE = "KETERANGAN TINGGAL SEMENTARA"


class DomisiliRenderer(BaseLetterRenderer):
    """Renders Surat Keterangan Domisili to PDF."""

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
        )
