"""Health endpoints."""
from fastapi import APIRouter
from sqlalchemy import text

from app.core.redis import get_redis
from app.core.response import success_response
from app.db.session import AsyncSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness check."""
    return success_response({"status": "ok"})


@router.get("/health/ready")
async def readiness() -> dict:
    """Readiness check: verify Postgres and Redis connectivity."""
    db_ok = redis_ok = False
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    try:
        redis_ok = await get_redis().ping()
    except Exception:
        redis_ok = False
    return success_response({"database": db_ok, "redis": bool(redis_ok)},
                            "ready" if db_ok and redis_ok else "degraded")
