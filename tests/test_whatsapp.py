"""Tests for the Fonnte WhatsApp provider -- mocks the outbound HTTP call,
never hits the real Fonnte API (this would send a real WhatsApp message)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.services.whatsapp import WhatsAppProvider, _normalize_id_phone


def test_normalize_id_phone_leading_zero():
    assert _normalize_id_phone("081234567890") == "6281234567890"


def test_normalize_id_phone_already_62():
    assert _normalize_id_phone("6281234567890") == "6281234567890"


def test_normalize_id_phone_strips_plus_and_formatting():
    assert _normalize_id_phone("+62 812-3456-7890") == "6281234567890"


@pytest.mark.asyncio
async def test_send_message_posts_to_fonnte_with_auth_header(monkeypatch):
    monkeypatch.setenv("FONNTE_API_KEY", "test-key-123")
    from app.core.config import get_settings
    get_settings.cache_clear()

    mock_response = AsyncMock()
    mock_response.status_code = 200
    with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_response)) as mock_post:
        await WhatsAppProvider().send_message("081234567890", "Kode: 123456")

    mock_post.assert_called_once()
    _, kwargs = mock_post.call_args
    assert kwargs["headers"]["Authorization"] == "test-key-123"
    assert kwargs["data"]["target"] == "6281234567890"
    assert kwargs["data"]["message"] == "Kode: 123456"
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_send_message_no_api_key_does_not_call_http(monkeypatch):
    monkeypatch.setenv("FONNTE_API_KEY", "")
    from app.core.config import get_settings
    get_settings.cache_clear()

    with patch("httpx.AsyncClient.post", new=AsyncMock()) as mock_post:
        await WhatsAppProvider().send_message("081234567890", "Kode: 123456")

    mock_post.assert_not_called()
    get_settings.cache_clear()
