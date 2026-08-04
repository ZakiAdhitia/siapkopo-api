"""TemplateRenderService: orchestrates per-domain PDF renderers.

Each letter type has its own dedicated renderer module.  This service acts as
the single entry-point for the rest of the application, dispatching calls to
the correct domain renderer based on the template's ``code``.

Domain renderer mapping
-----------------------
  domisili  → DomisiliRenderer  (_domisili.py)
  usaha     → SKURenderer       (_sku.py)
  lahir     → LahirRenderer     (_lahir.py)
  mati      → MatiRenderer      (_mati.py)
  na        → NARenderer        (_na.py)   ← also handles sub-documents
  uhc       → UHCRenderer       (_uhc.py)
  pindah    → PindahRenderer    (_pindah.py)
  ubah_data → UbahDataRenderer  (_ubah_data.py)
  *         → GenericRenderer   (_generic.py)  (fallback)
"""
from __future__ import annotations

from jinja2.sandbox import SandboxedEnvironment

from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import BaseLetterRenderer, _ddmmyyyy, _hari_indonesia
from ._docx_engine import DocxLetterRenderer
from ._domisili import DomisiliRenderer
from ._generic import GenericRenderer
from ._lahir import LahirRenderer
from ._mati import MatiRenderer
from ._na import NARenderer
from ._pindah import PindahRenderer
from ._sku import SKURenderer
from ._ubah_data import UbahDataRenderer
from ._uhc import UHCRenderer


def _finalize_none(value):
    """Jinja `finalize`: applied to every `{{ expression }}`'s value right
    before it's written to the output. Without this, a None value (e.g. an
    applicant snapshot field like `rt`/`rw` that's genuinely unset on the
    Resident record -- common for a freshly-created guest/walk-in resident)
    renders as the literal text "None" in a government letter. Existing
    `{{ field or '-' }}` guards already produce '-' before this ever sees
    None, so this is a safety net for the ones that don't, not a
    replacement for them."""
    return "-" if value is None else value


class TemplateRenderService:
    """Renders a LetterTemplate's body into a full letter PDF document.

    Dispatches to the appropriate per-domain renderer based on the template's
    ``code``.  The NA renderer additionally exposes
    ``render_sub_document()`` for individual sub-document downloads.
    """

    def __init__(self) -> None:
        self._docx_renderer = DocxLetterRenderer()
        self._env = SandboxedEnvironment(autoescape=True, finalize=_finalize_none)
        # Real letter templates print dates "DD-MM-YYYY" (e.g. "24-07-1976");
        # our applicant snapshot / answers carry ISO "YYYY-MM-DD" strings, so
        # every date field in a pdf_body_template needs this filter applied.
        self._env.filters["ddmmyyyy"] = _ddmmyyyy
        self._env.filters["hari_indonesia"] = _hari_indonesia
        self._renderers: dict[str, BaseLetterRenderer] = {
            "domisili": DomisiliRenderer(self._env),
            "usaha":    SKURenderer(self._env),
            "lahir":    LahirRenderer(self._env),
            "mati":     MatiRenderer(self._env),
            "na":       NARenderer(self._env),
            "uhc":      UHCRenderer(self._env),
            "pindah":   PindahRenderer(self._env),
            "ubah_data": UbahDataRenderer(self._env),
        }
        self._fallback: GenericRenderer = GenericRenderer(self._env)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def render_preview(
        self,
        template: LetterTemplate,
        fields: list[TemplateField],
        profile: VillageProfile,
    ) -> bytes:
        """Render a PDF preview using auto-generated sample data."""
        return self._renderer(template).render_preview(template, fields, profile)

    def render_issued(
        self,
        *,
        template: LetterTemplate,
        fields: list[TemplateField],
        profile: VillageProfile,
        answers: dict,
        applicant: dict,
        nomor: str,
        tanggal: str,
    ) -> bytes:
        """Render the real issued letter using actual submission answers.

        Prefers the real-Word-file pipeline (`DocxLetterRenderer`,
        2026-08-01 -- "benar-benar dipakai langsung") when a prepared
        template exists for this letter type; falls back to the
        hand-authored HTML/Jinja renderer otherwise (`pindah`/`kk`, which
        have no docx template yet).
        """
        if self._docx_renderer.supports(template.code):
            context = self._docx_context(profile, answers, applicant, nomor, tanggal)
            return self._docx_renderer.render(template.code, context)
        return self._renderer(template).render_issued(
            template=template,
            profile=profile,
            answers=answers,
            applicant=applicant,
            nomor=nomor,
            tanggal=tanggal,
        )

    def render_issued_sub_document(
        self,
        *,
        template: LetterTemplate,
        profile: VillageProfile,
        answers: dict,
        applicant: dict,
        nomor: str,
        tanggal: str,
        sub_doc_code: str,
    ) -> bytes:
        """Render a specific sub-document PDF (NA, SKTM)."""
        if self._docx_renderer.supports_sub_document(template.code, sub_doc_code):
            context = self._docx_context(profile, answers, applicant, nomor, tanggal)
            return self._docx_renderer.render_sub_document(template.code, context, sub_doc_code)
        renderer = self._renderer(template)
        if isinstance(renderer, NARenderer):
            return renderer.render_sub_document(
                template=template,
                profile=profile,
                answers=answers,
                applicant=applicant,
                nomor=nomor,
                tanggal=tanggal,
                sub_doc_code=sub_doc_code,
            )
        # Fallback: treat the whole letter as the sub-document
        return renderer.render_issued(
            template=template,
            profile=profile,
            answers=answers,
            applicant=applicant,
            nomor=nomor,
            tanggal=tanggal,
        )

    @staticmethod
    def _docx_context(
        profile: VillageProfile, answers: dict, applicant: dict, nomor: str, tanggal: str,
    ) -> dict:
        """Same shape as the HTML pipeline's Jinja context (see
        `_base.py::_render_document`) so docx templates can reference the
        same field names."""
        return {
            "village_name": profile.name, "kecamatan": profile.kecamatan or "-",
            "kabupaten": profile.kabupaten or "-", "provinsi": profile.provinsi or "-",
            "nomor": nomor, "tanggal": tanggal,
            **applicant, **answers,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _renderer(self, template: LetterTemplate) -> BaseLetterRenderer:
        """Return the domain renderer for a given template."""
        return self._renderers.get(template.code, self._fallback)
