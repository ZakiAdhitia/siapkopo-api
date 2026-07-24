"""Smoke test: qrcode can render a QR PNG on this machine."""
import io

import qrcode


def test_qrcode_renders_png():
    img = qrcode.make("https://example.test/verify/ABC-2026-123456")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
