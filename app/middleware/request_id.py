"""Request-id + access log middleware."""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.logging import get_logger

logger = get_logger("access")


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a request id and log each request."""

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = rid
        start = time.perf_counter()
        response = await call_next(request)
        elapsed = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = rid
        logger.info("%s %s -> %s (%.1fms) rid=%s",
                    request.method, request.url.path, response.status_code, elapsed, rid)
        return response
