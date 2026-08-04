"""Docx-based letter rendering: fills the real Word specimen files
(`template_file/*_TEMPLATE.docx`) with Jinja2 placeholders via `docxtpl`,
then converts the result to PDF with a headless LibreOffice subprocess.

This is the "really use the file directly" rendering path (per the
2026-08-01 instruction), as opposed to the hand-authored HTML/Jinja
renderers in `_domisili.py`/`_sku.py`/etc., which only *visually mirror*
the real documents. Only letter types with a prepared `*_TEMPLATE.docx`
are covered here (`_TEMPLATES`/`_SUB_TEMPLATES` below) -- `pindah`/`kk`
still use the HTML pipeline, and `TemplateRenderService` falls back to it
for any code not listed here.
"""
from __future__ import annotations

import datetime as _dt
import io
import subprocess
import tempfile
from pathlib import Path

from docxtpl import DocxTemplate
from jinja2 import Environment, Undefined
from pypdf import PdfReader, PdfWriter

from app.core.exceptions import AppException

from ._base import _ddmmyyyy, _hari_indonesia, format_tanggal_indonesia

# template_file/ lives at the project root (sipades-kopo-api/template_file),
# not next to this module -- moved there 2026-08-03 so every letter type's
# specimen/template docx files sit in one place outside the app package.
# parents[3] from this file (_docx_engine.py -> template_render -> services
# -> app -> sipades-kopo-api) is that project root.
_TEMPLATE_DIR = Path(__file__).resolve().parents[3] / "template_file"

# template_code -> docx path (relative to _TEMPLATE_DIR), for the "main"
# pdf_storage_path (the whole combined document -- for na/uhc this is every
# sub-document's pages concatenated, same as the real specimen file).
# Paths are grouped into one subfolder per letter type (2026-08-03 template
# reorg -- template_file/<Type>-Pengajuan/*.docx) so the growing set of
# specimen/template/output files per letter type stays browsable instead of
# one flat directory of 20+ similarly-named files.
_TEMPLATES: dict[str, str] = {
    "domisili": "Domisili-Pengajuan/DOMISILI_TEMPLATE.docx",
    "lahir": "Kelahiran-Pengajuan/KELAHIRAN_TEMPLATE.docx",
    "mati": "Kematian-Pengajuan/KEMATIAN_TEMPLATE.docx",
    "usaha": "SKU-Pengajuan/SKU_TEMPLATE.docx",
    "na": "NA-Pengajuan/NA_TEMPLATE.docx",
    "uhc": "UHC-Pengajuan/SKTM_TEMPLATE.docx",
}

# Multi-document letter types: the source .doc has every sub-document as
# consecutive pages of ONE file (e.g. NA's N.1/N.4/N.5/menumpang/belum-nikah
# specimen is one 5-page Word doc; SKTM's "Keluarga Miskin" + "Tanggung
# Jawab Mutlak" specimen is one 2-page doc) -- rendered once as a whole
# with every field merged into one Jinja context, then sliced into
# per-sub-document PDFs by page range via pypdf rather than split at the
# docx/XML level. NA's 6th sub-document (na_n6, "Ket. Kematian Suami/Istri
# Terdahulu") is deliberately NOT listed here -- its specimen (N-6 N-A.docx)
# is a separate standalone file, not an extra page merged into
# NA_TEMPLATE.docx, so it renders via the HTML/Jinja fallback (_na.py)
# instead; see `supports_sub_document` below.
_SUB_TEMPLATES: dict[str, str] = {
    "na": "NA-Pengajuan/NA_TEMPLATE.docx",
    "uhc": "UHC-Pengajuan/SKTM_TEMPLATE.docx",
}
# sub_doc_code -> 0-indexed inclusive page range, confirmed empirically
# against a real LibreOffice conversion (font substitution can shift
# pagination vs. the original Word layout -- verified 2026-08-02, each
# NA/SKTM sub-document renders to exactly one page).
_SUB_DOC_PAGES: dict[str, dict[str, tuple[int, int]]] = {
    "na": {
        "na_n1": (0, 0),
        "na_n4": (1, 1),
        "na_n5": (2, 2),
        "na_menumpang": (3, 3),
        "na_belum_nikah": (4, 4),
    },
    "uhc": {
        "sktm_utama": (0, 0),
        "sktm_tjm": (1, 1),
    },
}


def _tanggal_indonesia(value) -> str:
    """Jinja filter: ISO date string -> "15 Juli 2026" (Indonesian month
    name) -- the docx templates' free-text date lines (e.g. "Tanggal :
    ...", "Kopo, ...") use this full format, unlike the numeric
    `ddmmyyyy` filter used for compact "DD-MM-YYYY" fields."""
    if not value or not isinstance(value, str):
        return "-"
    try:
        d = _dt.date.fromisoformat(value[:10])
    except ValueError:
        return "-"
    return format_tanggal_indonesia(d)


def _is_blank(value) -> bool:
    """True for both explicit None and a missing/undefined context key
    (Jinja's `Undefined` sentinel) -- optional repeated-slot fields like
    SKTM's nik_2..nik_10/nama_2..nama_10 may be entirely absent from the
    submission's `answers` dict rather than present with a None value, and
    both cases must render identically ("-"), not one dashed and one
    blank."""
    return value is None or isinstance(value, Undefined)


def _upper_or_dash(value) -> str:
    """Blank-safe replacement for Jinja's built-in `upper` filter. Plain
    `|upper` on None/Undefined stringifies first (Jinja's default filter
    behavior), producing the literal word "NONE" -- very visible in
    optional repeated-slot fields like SKTM's nama_2..nama_10 (most
    submissions don't fill all 9)."""
    return "-" if _is_blank(value) else str(value).upper()


def _docx_jinja_env() -> Environment:
    """Plain (non-sandboxed) Jinja env -- docxtpl needs its own XML-aware
    rendering pipeline that `SandboxedEnvironment` doesn't support; the
    input here is server-authored template files, not user-supplied HTML,
    so the sandboxing rationale in the HTML pipeline doesn't apply."""
    env = Environment(finalize=lambda v: "-" if _is_blank(v) else v)
    env.filters["ddmmyyyy"] = _ddmmyyyy
    env.filters["hari_indonesia"] = _hari_indonesia
    env.filters["upper"] = _upper_or_dash
    env.filters["tanggal_indonesia"] = _tanggal_indonesia
    return env


def _find_soffice() -> str:
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "soffice",
    ):
        if candidate == "soffice" or Path(candidate).exists():
            return candidate
    raise AppException(
        "LibreOffice tidak ditemukan di server", "LIBREOFFICE_NOT_FOUND", 500
    )


class DocxLetterRenderer:
    """Fills a real Word template with submission data and returns PDF bytes."""

    def supports(self, template_code: str) -> bool:
        return template_code in _TEMPLATES or template_code in _SUB_TEMPLATES

    def supports_sub_document(self, template_code: str, sub_doc_code: str) -> bool:
        """Whether this specific sub-document has a page-range mapped to a
        real docx specimen. Unlike `supports()` (per template code), this is
        per sub-document: NA's na_n6 has no page mapped (its specimen is a
        separate standalone file, not a page merged into NA_TEMPLATE.docx),
        so callers must fall back to the HTML/Jinja renderer for that one
        sub-document even though NA otherwise uses the docx pipeline."""
        return sub_doc_code in _SUB_DOC_PAGES.get(template_code, {})

    def render(self, template_code: str, context: dict) -> bytes:
        """Render a single-document letter type's full PDF."""
        docx_filename = _TEMPLATES[template_code]
        pdf_bytes, _ = self._render_docx_to_pdf(docx_filename, context)
        return pdf_bytes

    def render_sub_document(self, template_code: str, context: dict, sub_doc_code: str) -> bytes:
        """Render one page-range of a multi-document letter type's PDF."""
        docx_filename = _SUB_TEMPLATES[template_code]
        pdf_bytes, _ = self._render_docx_to_pdf(docx_filename, context)
        pages = _SUB_DOC_PAGES.get(template_code, {}).get(sub_doc_code)
        if pages is None:
            return pdf_bytes
        return self._extract_pages(pdf_bytes, pages)

    # ------------------------------------------------------------------

    def _render_docx_to_pdf(self, docx_filename: str, context: dict) -> tuple[bytes, int]:
        template_path = _TEMPLATE_DIR / docx_filename
        doc = DocxTemplate(str(template_path))
        doc.render(context, jinja_env=_docx_jinja_env())
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            docx_path = tmp_path / "out.docx"
            doc.save(str(docx_path))
            pdf_bytes = self._convert_to_pdf(docx_path, tmp_path)
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return pdf_bytes, len(reader.pages)

    def _convert_to_pdf(self, docx_path: Path, out_dir: Path) -> bytes:
        soffice = _find_soffice()
        result = subprocess.run(
            [
                soffice, "--headless", "--norestore",
                "--convert-to", "pdf", "--outdir", str(out_dir), str(docx_path),
            ],
            capture_output=True, timeout=60,
        )
        pdf_path = out_dir / (docx_path.stem + ".pdf")
        if result.returncode != 0 or not pdf_path.exists():
            raise AppException(
                "Gagal mengonversi dokumen Word ke PDF: "
                + result.stderr.decode(errors="replace")[:300],
                "DOCX_PDF_CONVERT_ERROR", 500,
            )
        return pdf_path.read_bytes()

    @staticmethod
    def _extract_pages(pdf_bytes: bytes, page_range: tuple[int, int]) -> bytes:
        reader = PdfReader(io.BytesIO(pdf_bytes))
        writer = PdfWriter()
        start, end = page_range
        for i in range(start, end + 1):
            writer.add_page(reader.pages[i])
        out = io.BytesIO()
        writer.write(out)
        return out.getvalue()
