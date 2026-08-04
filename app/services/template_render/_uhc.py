"""Renderer for Surat UHC / BPJS Kesehatan."""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer


class UHCRenderer(BaseLetterRenderer):
    """Renders Surat Keterangan UHC / BPJS Kesehatan to PDF."""

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
            tanggal=date.today().strftime("%d %B %Y"),
            letter_title=template.name.upper(),
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
            letter_title=template.name.upper(),
            body_template=template.pdf_body_template,
        )
