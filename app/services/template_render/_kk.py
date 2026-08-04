"""Renderer for the Kartu Keluarga (F-1.02 "Formulir Pendaftaran Peristiwa
Kependudukan") registration form.

Unlike Domisili/SKU/Ket. Kelahiran/Ket. Kematian (Kepala-Desa-issued
keterangan), F-1.02 is a registration form the citizen fills out and takes
to Dukcapil themselves -- the village only countersigns "mengetahui", it
doesn't certify anything (ALUR_PENGISIAN_KK.md bagian B).
"""
from __future__ import annotations

from datetime import date

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import DUAL_SIGNATURE_FOOTER, BaseLetterRenderer, format_tanggal_indonesia

_LETTER_TITLE = "FORMULIR PENDAFTARAN PERISTIWA KEPENDUDUKAN (F-1.02)"


class KKRenderer(BaseLetterRenderer):
    """Renders the KK (F-1.02) registration form to PDF."""

    def render_preview(
        self,
        template: LetterTemplate,
        fields: list[TemplateField],
        profile: VillageProfile,
    ) -> bytes:
        return self._render_document(
            profile=profile,
            data={
                **self._sample_data(fields),
                "left_label": "Pemohon",
                "right_label": f"Mengetahui, Kepala Desa {profile.name}",
            },
            nomor=self._preview_number(template),
            tanggal=format_tanggal_indonesia(date.today()),
            letter_title=_LETTER_TITLE,
            body_template=template.pdf_body_template,
            footer_template=DUAL_SIGNATURE_FOOTER,
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
            data={
                **applicant, **answers,
                "left_label": "Pemohon",
                "right_label": f"Mengetahui, Kepala Desa {profile.name}",
            },
            nomor=nomor,
            tanggal=tanggal,
            letter_title=_LETTER_TITLE,
            body_template=template.pdf_body_template,
            footer_template=DUAL_SIGNATURE_FOOTER,
        )
