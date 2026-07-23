"""FastAPI application factory."""
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.exceptions import AppException
from app.core.logging import configure_logging, get_logger
from app.core.response import error_response
from app.middleware.request_id import RequestIdMiddleware

logger = get_logger("app")


def create_app() -> FastAPI:
    """Build and configure the FastAPI app."""
    configure_logging()
    settings = get_settings()
    app = FastAPI(title=settings.app_name, debug=settings.debug)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestIdMiddleware)

    @app.exception_handler(AppException)
    async def _app_exc(_: Request, exc: AppException) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code,
                            content=error_response(exc.message, exc.error_code))

    @app.exception_handler(RequestValidationError)
    async def _val_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(status_code=422,
                            content=error_response(str(exc.errors()), "VALIDATION_ERROR"))

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error: %s", exc)
        return JSONResponse(status_code=500,
                            content=error_response("Internal server error", "INTERNAL_ERROR"))

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    return app


app = create_app()
