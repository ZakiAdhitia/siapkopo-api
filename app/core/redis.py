"""Async Redis client singleton."""
from redis.asyncio import Redis, from_url

from app.core.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    """Return a shared async Redis client."""
    global _client
    if _client is None:
        _client = from_url(get_settings().redis_url, decode_responses=True)
    return _client


async def close_redis() -> None:
    """Close the shared Redis client."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
