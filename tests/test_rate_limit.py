"""Tests for the in-process rate limiter (replaces the old Redis-backed one)."""
from types import SimpleNamespace

import pytest

import app.dependencies.rate_limit as rate_limit_module
from app.core.exceptions import TooManyRequestsError
from app.dependencies.rate_limit import rate_limit


def _request(ip: str = "1.2.3.4"):
    return SimpleNamespace(client=SimpleNamespace(host=ip))


@pytest.mark.asyncio
async def test_allows_up_to_the_limit():
    dep = rate_limit("test_allow", limit=3, window_seconds=60)
    for _ in range(3):
        await dep(_request())  # must not raise


@pytest.mark.asyncio
async def test_rejects_once_over_the_limit():
    dep = rate_limit("test_reject", limit=3, window_seconds=60)
    for _ in range(3):
        await dep(_request())
    with pytest.raises(TooManyRequestsError):
        await dep(_request())


@pytest.mark.asyncio
async def test_counts_are_scoped_per_ip():
    dep = rate_limit("test_per_ip", limit=1, window_seconds=60)
    await dep(_request("1.1.1.1"))
    await dep(_request("2.2.2.2"))  # different IP, must not raise


@pytest.mark.asyncio
async def test_window_resets_after_expiry(monkeypatch):
    dep = rate_limit("test_window", limit=1, window_seconds=60)
    fake_now = [1000.0]
    monkeypatch.setattr(rate_limit_module.time, "monotonic", lambda: fake_now[0])

    await dep(_request())
    with pytest.raises(TooManyRequestsError):
        await dep(_request())

    fake_now[0] += 61  # past the window
    await dep(_request())  # must not raise
