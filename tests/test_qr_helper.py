import base64
from app.services.qr import generate_qr_data_uri


def test_generate_qr_data_uri_returns_valid_png_data_uri():
    uri = generate_qr_data_uri("https://example.test/verify/ABC-2026-123456")
    assert uri.startswith("data:image/png;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
