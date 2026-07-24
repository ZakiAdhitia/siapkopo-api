"""Smoke test: xhtml2pdf can render HTML to a valid PDF on this machine.

xhtml2pdf (pure Python, built on reportlab) replaces WeasyPrint here because
WeasyPrint requires native GTK3/Pango/cairo runtime libraries that are not
available on this Windows development machine. See the design spec's
deviation note for the full rationale.
"""
import io

from xhtml2pdf import pisa


def test_xhtml2pdf_renders_minimal_pdf():
    buffer = io.BytesIO()
    result = pisa.CreatePDF("<html><body><h1>Halo</h1></body></html>", dest=buffer)
    assert result.err == 0
    assert buffer.getvalue()[:5] == b"%PDF-"
