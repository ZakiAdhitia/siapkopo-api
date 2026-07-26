"""Redis-backed fixed-window rate limiter for public, unauthenticated endpoints."""
from collections.abc import Callable

from fastapi import Request

from app.core.exceptions import TooManyRequestsError
from app.core.redis import get_redis


def rate_limit(key_prefix: str, limit: int, window_seconds: int) -> Callable:
    """Dependency factory: at most `limit` requests per client IP per window.

    Scoped to a handful of public write/lookup endpoints that have no auth
    to key off of (guest submission, NIK autofill lookup, guest status
    tracking) -- not a general-purpose framework applied everywhere.
    """

    async def _dep(request: Request) -> None:
        client_ip = request.client.host if request.client else "unknown"
        redis = get_redis()
        key = f"ratelimit:{key_prefix}:{client_ip}"
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, window_seconds)
        if count > limit:
            raise TooManyRequestsError()

    return _dep
