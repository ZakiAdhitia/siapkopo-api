"""Generic / fallback renderer for letter types without a dedicated module.

This renderer handles any letter type whose ``code`` is not
explicitly mapped to a domain-specific renderer (e.g. custom admin-created
templates).  It delegates entirely to the base engine using the template's own
``pdf_body_template`` field.
"""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, format_tanggal_indonesia


class GenericRenderer(BaseLetterRenderer):
    """Renders any letter template using its stored pdf_body_template."""

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
        as_html: bool = False,
    ) -> bytes | str:
        return self._render_document(
            profile=profile,
            data={**applicant, **answers},
            nomor=nomor,
            tanggal=tanggal,
            letter_title=template.name.upper(),
            body_template=template.pdf_body_template,
            as_html=as_html,
        )
