"""Health endpoints."""
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from app.core.response import success_response
from app.db.session import AsyncSessionLocal

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness check."""
    return success_response({"status": "ok"})


@router.get("/health/ready")
async def readiness(response: Response) -> dict:
    """Readiness check: verify Postgres connectivity."""
    try:
        async with AsyncSessionLocal() as s:
            await s.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    if not db_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return success_response({"database": db_ok}, "ready" if db_ok else "degraded")
