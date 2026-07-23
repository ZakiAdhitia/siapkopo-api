import pytest
from app.core.redis import get_redis


@pytest.mark.asyncio
async def test_redis_ping():
    r = get_redis()
    try:
        assert await r.ping() is True
    except Exception:
        pytest.skip("Redis not running")
