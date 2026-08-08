"""In-process fixed-window rate limiter for public, unauthenticated endpoints."""
import time
from collections.abc import Callable

from fastapi import Request

from app.core.exceptions import TooManyRequestsError

# {key: (window_start, count)} -- single-process, in-memory state (no Redis
# or other shared store). Sufficient for this app's single-server
# deployment (see CLAUDE.md: one village, one server); a stale entry for an
# IP that never comes back just sits at a few bytes, not worth pruning at
# this app's traffic scale.
_counters: dict[str, tuple[float, int]] = {}


def rate_limit(key_prefix: str, limit: int, window_seconds: int) -> Callable:
    """Dependency factory: at most `limit` requests per client IP per window.

    Scoped to a handful of public write/lookup endpoints that have no auth
    to key off of (guest submission, guest status tracking) -- not a
    general-purpose framework applied everywhere.
    """

    async def _dep(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        key = f"{key_prefix}:{client_ip}"
        now = time.monotonic()
        window_start, count = _counters.get(key, (now, 0))
        if now - window_start >= window_seconds:
            window_start, count = now, 0
        count += 1
        _counters[key] = (window_start, count)
        if count > limit:
            raise TooManyRequestsError()

    return _dep


def _reset_counters() -> None:
    """Test-only hook: clear all rate-limit state between test cases."""
    _counters.clear()
