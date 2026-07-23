"""Proves the JSON error envelope covers unhandled exceptions and HTTP errors."""
import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.asyncio
async def test_unhandled_exception_returns_envelope_without_traceback():
    """An unhandled exception in a route must yield 500 + the JSON envelope, no traceback text."""
    app = create_app()

    @app.get("/api/v1/_boom")
    async def _boom():
        raise RuntimeError("kaboom - sensitive internal detail")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/_boom")

    assert resp.status_code == 500
    body = resp.json()
    assert body == {
        "success": False,
        "message": "Internal server error",
        "error_code": "INTERNAL_ERROR",
        "data": None,
    }
    # No traceback / plaintext leakage anywhere in the raw response body.
    assert "Traceback" not in resp.text
    assert "RuntimeError" not in resp.text
    assert "kaboom" not in resp.text
    assert resp.headers["content-type"].startswith("application/json")


@pytest.mark.asyncio
async def test_unknown_path_returns_404_envelope(client):
    resp = await client.get("/api/v1/this-route-does-not-exist")
    assert resp.status_code == 404
    body = resp.json()
    assert body["success"] is False
    assert body["error_code"] == "NOT_FOUND"
    assert "data" in body and body["data"] is None


@pytest.mark.asyncio
async def test_wrong_method_returns_405_envelope(client):
    resp = await client.post("/api/v1/health")
    assert resp.status_code == 405
    body = resp.json()
    assert body["success"] is False
    assert body["error_code"] == "METHOD_NOT_ALLOWED"
