# SIPADES Foundation (Phase 1-3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a runnable, tested FastAPI backend covering Infrastructure, Authentication (password + OTP, data-driven RBAC), and Master Data (village hierarchy + residents with Excel import/export) for SIPADES.

**Architecture:** Clean Architecture, async-first. Request flow is strictly `router → service → repository → model`. Pydantic v2 schemas at the edges, DB access only in repositories, business logic only in services, DI for sessions/current-user/permissions. All responses use a single envelope. Alembic is the only source of schema changes.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 async + asyncpg, Alembic, Pydantic v2 + pydantic-settings, PyJWT, passlib[bcrypt], redis (async), openpyxl, ARQ (installed, wired later), pytest + pytest-asyncio + httpx.

## Global Constraints

- Python 3.13+; async everywhere; **no synchronous DB access**.
- Router contains **no business logic**; services hold logic; repositories hold all DB access.
- Every endpoint has a `response_model`.
- **RBAC is data-driven** — guard with `require_permission("...")`; **never** `if role == "..."`.
- Every table: UUID v4 PK, `created_at`/`updated_at` (UTC tz-aware), `deleted_at` soft-delete.
- `village_id` FK on tenant-scoped tables (single village seeded now).
- Response envelope — Success: `{"success": true, "message": "...", "data": {...}}`; Error: `{"success": false, "message": "...", "error_code": "...", "data": null}`.
- Pagination response shape: `{"items": [...], "total": int, "page": int, "size": int}`.
- Type hints + docstrings + logger in every module. Custom exceptions only; never leak a traceback.
- Base API path: `/api/v1`. CORS origin from config (default `http://localhost:5173`).
- Commit frequently, one logical change per commit.

---

## File Structure

```
sipades-kopo-api/
  pyproject.toml                      # deps + pytest/ruff config
  .env.example                        # config template
  docker-compose.yml                  # Redis only
  alembic.ini
  alembic/
    env.py                            # async migration env
    versions/                         # migration files
  app/
    __init__.py
    main.py                           # app factory
    core/
      config.py                       # Settings (pydantic-settings)
      logging.py                      # structured logger + request-id
      exceptions.py                   # AppException hierarchy
      response.py                     # envelope helpers + models
      security.py                     # jwt encode/decode, password hash
      redis.py                        # async redis client
    db/
      base.py                         # DeclarativeBase + TimestampMixin/SoftDeleteMixin
      session.py                      # async engine + get_db
    models/
      __init__.py                     # import all models for Alembic
      auth.py                         # Role, Permission, role_permissions, User, RefreshToken
      master.py                       # Village, Dusun, RW, RT, FamilyCard, Resident
    schemas/
      common.py                       # Envelope, Page, pagination params
      auth.py                         # auth request/response schemas
      master.py                       # master-data schemas
    repositories/
      base.py                         # BaseRepository (generic CRUD)
      auth.py                         # UserRepository, RefreshTokenRepository, RoleRepository
      master.py                       # per-entity repositories
    services/
      auth.py                         # AuthService
      otp.py                          # OtpService (Redis-backed)
      master.py                       # per-entity services
      excel.py                        # resident import/export
    permissions/
      registry.py                     # PERMISSIONS constant + ROLE_PERMISSIONS map
    dependencies/
      db.py                           # re-export get_db
      auth.py                         # get_current_user, require_permission
      pagination.py                   # PaginationParams dep
    middleware/
      request_id.py                   # request-id + access log middleware
    workers/
      __init__.py                     # ARQ settings stub (wired later)
    utils/
      __init__.py
    api/
      __init__.py
      v1/
        __init__.py                   # v1 APIRouter aggregator
        health.py
        auth.py
        master.py                     # village/dusun/rw/rt/family-card/resident routers
    seed/
      __init__.py
      seed.py                         # seed roles, permissions, demo accounts, master data
  tests/
    conftest.py                       # async client + test db fixtures
    test_health.py
    test_auth.py
    test_master_data.py
```

---

# PHASE 1 — INFRASTRUCTURE

### Task 1: Project scaffolding & dependencies

**Files:**
- Create: `pyproject.toml`, `.env.example`, `docker-compose.yml`, `.gitignore`, `app/__init__.py`

**Interfaces:**
- Produces: installable package `app`; console command `pytest` configured; Redis reachable at `redis://localhost:6379/0`.

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "sipades-kopo-api"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy[asyncio]>=2.0.35",
  "asyncpg>=0.30",
  "alembic>=1.14",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "pyjwt>=2.10",
  "passlib[bcrypt]>=1.7.4",
  "bcrypt>=4.2,<5",
  "redis>=5.2",
  "openpyxl>=3.1",
  "arq>=0.26",
  "python-multipart>=0.0.12",
]

[project.optional-dependencies]
dev = [
  "pytest>=8.3",
  "pytest-asyncio>=0.24",
  "httpx>=0.27",
  "aiosqlite>=0.20",
  "ruff>=0.7",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py313"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["app*"]
```

- [ ] **Step 2: Write `.env.example`**

```dotenv
APP_NAME=SIPADES
APP_ENV=development
DEBUG=true
API_V1_PREFIX=/api/v1

# Local PostgreSQL already running on the user's machine
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/sipades

REDIS_URL=redis://localhost:6379/0

JWT_SECRET=change-me-in-production
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

OTP_TTL_SECONDS=300
OTP_LENGTH=6

CORS_ORIGINS=http://localhost:5173
```

- [ ] **Step 3: Write `docker-compose.yml` (Redis only)**

```yaml
services:
  redis:
    image: redis:7-alpine
    container_name: sipades-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: ["redis-server", "--appendonly", "yes"]
volumes:
  redis_data:
```

- [ ] **Step 4: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
venv/
.env
.pytest_cache/
*.egg-info/
.ruff_cache/
```

- [ ] **Step 5: Create empty `app/__init__.py`**, install, verify

```bash
python -m venv .venv && . .venv/Scripts/activate
pip install -e ".[dev]"
```
Expected: install succeeds. `docker compose up -d redis` then `docker compose ps` shows redis running.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .env.example docker-compose.yml .gitignore app/__init__.py
git commit -m "chore: project scaffolding, deps, docker redis"
```

---

### Task 2: Core config, exceptions, response envelope, logging

**Files:**
- Create: `app/core/config.py`, `app/core/exceptions.py`, `app/core/response.py`, `app/core/logging.py`
- Test: `tests/test_core.py`

**Interfaces:**
- Produces:
  - `get_settings() -> Settings` (cached); `Settings` fields: `app_name, app_env, debug, api_v1_prefix, database_url, redis_url, jwt_secret, jwt_algorithm, access_token_expire_minutes, refresh_token_expire_days, otp_ttl_seconds, otp_length, cors_origins: list[str]`.
  - `AppException(message: str, error_code: str, status_code: int = 400)` and subclasses `NotFoundError` (404, `NOT_FOUND`), `UnauthorizedError` (401, `UNAUTHORIZED`), `ForbiddenError` (403, `FORBIDDEN`), `ConflictError` (409, `CONFLICT`), `ValidationAppError` (422, `VALIDATION_ERROR`).
  - `success_response(data, message="OK") -> dict`; `error_response(message, error_code, data=None) -> dict`.
  - `Envelope[T]` and `ErrorEnvelope` Pydantic models.
  - `configure_logging()`, `get_logger(name) -> Logger`.

- [ ] **Step 1: Write failing test** `tests/test_core.py`

```python
from app.core.config import get_settings
from app.core.exceptions import NotFoundError, AppException
from app.core.response import success_response, error_response


def test_settings_load():
    s = get_settings()
    assert s.api_v1_prefix == "/api/v1"
    assert isinstance(s.cors_origins, list)


def test_not_found_is_app_exception():
    err = NotFoundError("resident not found")
    assert isinstance(err, AppException)
    assert err.status_code == 404
    assert err.error_code == "NOT_FOUND"


def test_envelope_helpers():
    ok = success_response({"id": 1}, "done")
    assert ok == {"success": True, "message": "done", "data": {"id": 1}}
    bad = error_response("nope", "NOT_FOUND")
    assert bad == {"success": False, "message": "nope", "error_code": "NOT_FOUND", "data": None}
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_core.py -v`
Expected: FAIL (ModuleNotFoundError: app.core.config).

- [ ] **Step 3: Implement `app/core/config.py`**

```python
"""Application settings loaded from environment."""
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SIPADES"
    app_env: str = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/sipades"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    otp_ttl_seconds: int = 300
    otp_length: int = 6

    cors_origins: list[str] = ["http://localhost:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
```

- [ ] **Step 4: Implement `app/core/exceptions.py`**

```python
"""Custom application exceptions mapped to the error envelope."""


class AppException(Exception):
    """Base application error carrying an envelope-friendly payload."""

    def __init__(self, message: str, error_code: str = "ERROR", status_code: int = 400) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.status_code = status_code


class NotFoundError(AppException):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(message, "NOT_FOUND", 404)


class UnauthorizedError(AppException):
    def __init__(self, message: str = "Unauthorized") -> None:
        super().__init__(message, "UNAUTHORIZED", 401)


class ForbiddenError(AppException):
    def __init__(self, message: str = "Forbidden") -> None:
        super().__init__(message, "FORBIDDEN", 403)


class ConflictError(AppException):
    def __init__(self, message: str = "Conflict") -> None:
        super().__init__(message, "CONFLICT", 409)


class ValidationAppError(AppException):
    def __init__(self, message: str = "Validation error") -> None:
        super().__init__(message, "VALIDATION_ERROR", 422)
```

- [ ] **Step 5: Implement `app/core/response.py`**

```python
"""Standard success/error response envelope."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Envelope(BaseModel, Generic[T]):
    success: bool = True
    message: str = "OK"
    data: T | None = None


class ErrorEnvelope(BaseModel):
    success: bool = False
    message: str
    error_code: str
    data: None = None


def success_response(data: object = None, message: str = "OK") -> dict:
    """Build a success envelope dict."""
    return {"success": True, "message": message, "data": data}


def error_response(message: str, error_code: str, data: object = None) -> dict:
    """Build an error envelope dict."""
    return {"success": False, "message": message, "error_code": error_code, "data": data}
```

- [ ] **Step 6: Implement `app/core/logging.py`**

```python
"""Logging configuration."""
import logging
import sys

_CONFIGURED = False


def configure_logging(level: int = logging.INFO) -> None:
    """Configure root logging once with a concise format."""
    global _CONFIGURED
    if _CONFIGURED:
        return
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""
    return logging.getLogger(name)
```

- [ ] **Step 7: Run tests** — `pytest tests/test_core.py -v` → PASS

- [ ] **Step 8: Commit**

```bash
git add app/core tests/test_core.py
git commit -m "feat(core): config, exceptions, response envelope, logging"
```

---

### Task 3: Database base, session, Alembic (async)

**Files:**
- Create: `app/db/base.py`, `app/db/session.py`, `app/models/__init__.py`, `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`
- Test: `tests/test_db.py`

**Interfaces:**
- Produces:
  - `Base` (DeclarativeBase). Mixins: `UUIDMixin` (`id: Mapped[UUID]` default uuid4), `TimestampMixin` (`created_at`, `updated_at`), `SoftDeleteMixin` (`deleted_at: Mapped[datetime | None]`).
  - `engine`, `AsyncSessionLocal`, `async get_db() -> AsyncIterator[AsyncSession]`.
  - `app/models/__init__.py` imports every model module so Alembic autogenerate sees them.

- [ ] **Step 1: Write failing test** `tests/test_db.py`

```python
from app.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


def test_mixins_present():
    assert hasattr(Base, "metadata")
    for mixin in (UUIDMixin, TimestampMixin, SoftDeleteMixin):
        assert mixin is not None
```

- [ ] **Step 2: Run to verify it fails** — `pytest tests/test_db.py -v` → FAIL

- [ ] **Step 3: Implement `app/db/base.py`**

```python
"""Declarative base and common column mixins."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for all models."""


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Note: tests use SQLite (aiosqlite); `PgUUID(as_uuid=True)` requires a portable type. Use the fallback below to keep tests DB-agnostic — replace the `PgUUID` import/use with:

```python
from sqlalchemy.types import CHAR, TypeDecorator


class GUID(TypeDecorator):
    """Platform-independent UUID: PgUUID on postgres, CHAR(36) elsewhere."""
    impl = CHAR
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from sqlalchemy.dialects.postgresql import UUID as _PgUUID
            return dialect.type_descriptor(_PgUUID(as_uuid=True))
        return dialect.type_descriptor(CHAR(36))

    def process_bind_param(self, value, dialect):
        if value is None:
            return value
        return str(value) if dialect.name != "postgresql" else value

    def process_result_value(self, value, dialect):
        if value is None:
            return value
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
```
Then `id: Mapped[uuid.UUID] = mapped_column(GUID(), primary_key=True, default=uuid.uuid4)`.

- [ ] **Step 4: Implement `app/db/session.py`**

```python
"""Async engine and session dependency."""
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=settings.debug, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """Yield an async DB session, rolling back on error."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 5: Implement `app/models/__init__.py`**

```python
"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import auth, master  # noqa: F401
```
(Create empty `app/models/auth.py` and `app/models/master.py` placeholders now with `from app.db.base import Base  # noqa: F401` to avoid import errors; real models arrive in Tasks 6 & 14.)

- [ ] **Step 6: Init Alembic**

```bash
alembic init -t async alembic
```
Then edit `alembic/env.py`: set `target_metadata` and read URL from settings:

```python
from app.core.config import get_settings
from app.db.base import Base
import app.models  # noqa: F401  (populates Base.metadata)

config.set_main_option("sqlalchemy.url", get_settings().database_url)
target_metadata = Base.metadata
```

- [ ] **Step 7: Run tests** — `pytest tests/test_db.py -v` → PASS

- [ ] **Step 8: Commit**

```bash
git add app/db app/models alembic alembic.ini tests/test_db.py
git commit -m "feat(db): async engine, base mixins, alembic setup"
```

---

### Task 4: Redis client

**Files:**
- Create: `app/core/redis.py`
- Test: `tests/test_redis.py` (skipped if Redis unavailable)

**Interfaces:**
- Produces: `get_redis() -> Redis` (async client, singleton); `async close_redis()`.

- [ ] **Step 1: Write test** `tests/test_redis.py`

```python
import pytest
from app.core.redis import get_redis


@pytest.mark.asyncio
async def test_redis_ping():
    r = get_redis()
    try:
        assert await r.ping() is True
    except Exception:
        pytest.skip("Redis not running")
```

- [ ] **Step 2: Run** — `pytest tests/test_redis.py -v` → FAIL (import error)

- [ ] **Step 3: Implement `app/core/redis.py`**

```python
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
```

- [ ] **Step 4: Run** — `pytest tests/test_redis.py -v` → PASS or SKIP

- [ ] **Step 5: Commit**

```bash
git add app/core/redis.py tests/test_redis.py
git commit -m "feat(core): async redis client"
```

---

### Task 5: App factory, middleware, exception handlers, health

**Files:**
- Create: `app/middleware/request_id.py`, `app/api/__init__.py`, `app/api/v1/__init__.py`, `app/api/v1/health.py`, `app/schemas/common.py`, `app/main.py`
- Test: `tests/test_health.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `get_settings`, `AppException`, `success_response/error_response`, `get_redis`, `get_db`.
- Produces: `create_app() -> FastAPI`; `app` instance; health routes `GET {prefix}/health`, `GET {prefix}/health/ready`. Global handlers convert `AppException`, `RequestValidationError`, and unhandled `Exception` into the error envelope.

- [ ] **Step 1: Write `tests/conftest.py`**

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest_asyncio.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

- [ ] **Step 2: Write failing test** `tests/test_health.py`

```python
import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"
```

- [ ] **Step 3: Run** — `pytest tests/test_health.py -v` → FAIL (no app.main)

- [ ] **Step 4: Implement `app/middleware/request_id.py`**

```python
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
```

- [ ] **Step 5: Implement `app/schemas/common.py`**

```python
"""Shared schemas: pagination page and query params."""
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int
```

- [ ] **Step 6: Implement `app/api/v1/health.py`**

```python
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
```

- [ ] **Step 7: Implement `app/api/v1/__init__.py`**

```python
"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
# auth + master routers appended in later tasks
```

- [ ] **Step 8: Implement `app/main.py`**

```python
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
```

- [ ] **Step 9: Run tests** — `pytest tests/test_health.py -v` → PASS

- [ ] **Step 10: Manual boot check**

Run: `uvicorn app.main:app --reload` → open `/api/v1/health` and `/docs`. Expected 200 envelope.

- [ ] **Step 11: Commit**

```bash
git add app tests
git commit -m "feat(api): app factory, middleware, exception handlers, health endpoints"
```

---

# PHASE 2 — AUTHENTICATION

### Task 6: Auth models + migration

**Files:**
- Modify: `app/models/auth.py`
- Create: migration via `alembic revision --autogenerate`
- Test: `tests/test_auth_models.py`

**Interfaces:**
- Produces SQLAlchemy models:
  - `Role(UUIDMixin, TimestampMixin, SoftDeleteMixin)`: `name: str` (unique), `display_name: str`, `description: str | None`, `permissions` (M2M).
  - `Permission(UUIDMixin, TimestampMixin)`: `code: str` (unique), `description: str | None`.
  - `role_permissions` association table.
  - `User(UUIDMixin, TimestampMixin, SoftDeleteMixin)`: `username: str | None` (unique), `nik: str | None` (unique), `full_name: str`, `hashed_password: str | None`, `phone: str | None`, `role_id: FK`, `resident_id: FK | None`, `is_active: bool = True`, `role` relationship.
  - `RefreshToken(UUIDMixin, TimestampMixin)`: `user_id: FK`, `token_hash: str`, `expires_at: datetime`, `revoked_at: datetime | None`.

- [ ] **Step 1: Write failing test** `tests/test_auth_models.py`

```python
from app.models.auth import Role, Permission, User, RefreshToken


def test_auth_models_tables():
    assert Role.__tablename__ == "roles"
    assert Permission.__tablename__ == "permissions"
    assert User.__tablename__ == "users"
    assert RefreshToken.__tablename__ == "refresh_tokens"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/models/auth.py`**

```python
"""Authentication & RBAC models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", GUID(), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", GUID(), ForeignKey("permissions.id"), primary_key=True),
)


class Permission(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Role(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    nik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("residents.id"), nullable=True
    )
    role: Mapped[Role] = relationship(lazy="selectin")


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

Note: `resident_id` FK targets `residents.id` (Task 14). Until Task 14 lands, keep the FK but ensure `master.py` is imported in `app/models/__init__.py` before autogenerate. If sequencing Task 6 before 14, temporarily make it a plain `GUID()` column without FK and add the FK in Task 14's migration.

- [ ] **Step 4: Run** — `pytest tests/test_auth_models.py -v` → PASS

- [ ] **Step 5: Generate + apply migration**

```bash
alembic revision --autogenerate -m "auth tables"
alembic upgrade head
```
Expected: tables `roles, permissions, role_permissions, users, refresh_tokens` created.

- [ ] **Step 6: Commit**

```bash
git add app/models/auth.py alembic/versions tests/test_auth_models.py
git commit -m "feat(auth): rbac + user models and migration"
```

---

### Task 7: Security utilities (JWT + password hash)

**Files:**
- Modify: `app/core/security.py`
- Test: `tests/test_security.py`

**Interfaces:**
- Produces:
  - `hash_password(pw: str) -> str`; `verify_password(pw: str, hashed: str) -> bool`.
  - `create_access_token(subject: str, role: str, permissions: list[str], jti: str) -> str`.
  - `create_refresh_token_value() -> tuple[str, str]` returns `(raw, sha256_hash)`.
  - `decode_token(token: str) -> dict` (raises `UnauthorizedError` on invalid/expired).
  - `hash_token(raw: str) -> str` (sha256).

- [ ] **Step 1: Write failing test** `tests/test_security.py`

```python
import pytest
from app.core.security import (
    hash_password, verify_password, create_access_token, decode_token, hash_token,
)
from app.core.exceptions import UnauthorizedError


def test_password_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip():
    token = create_access_token("user-1", "staf", ["resident:read"], "jti-1")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "staf"
    assert "resident:read" in payload["permissions"]
    assert payload["jti"] == "jti-1"


def test_decode_invalid_raises():
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-token")


def test_hash_token_stable():
    assert hash_token("abc") == hash_token("abc")
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/core/security.py`**

```python
"""JWT and password hashing utilities."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return _pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd.verify(pw, hashed)


def create_access_token(subject: str, role: str, permissions: list[str], jti: str) -> str:
    """Create a signed JWT access token."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject, "role": role, "permissions": permissions, "jti": jti,
        "type": "access", "iat": now,
        "exp": now + timedelta(minutes=s.access_token_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token_value() -> tuple[str, str]:
    """Return (raw_refresh_token, sha256_hash)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """SHA-256 hash of a token for at-rest storage."""
    return hashlib.sha256(raw.encode()).hexdigest()


def decode_token(token: str) -> dict:
    """Decode/verify a JWT, raising UnauthorizedError on failure."""
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
```

- [ ] **Step 4: Run** — `pytest tests/test_security.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/core/security.py tests/test_security.py
git commit -m "feat(core): jwt + password hashing utilities"
```

---

### Task 8: Permission registry + seed data module

**Files:**
- Create: `app/permissions/registry.py`, `app/seed/__init__.py`, `app/seed/seed.py`
- Test: `tests/test_permissions_registry.py`

**Interfaces:**
- Produces:
  - `PERMISSIONS: list[str]` — full permission code list.
  - `ROLE_PERMISSIONS: dict[str, list[str]]` — role name → permission codes (`"*"` = all for administrator).
  - `ROLE_DEFS: list[tuple[name, display_name]]`.
  - `DEMO_ACCOUNTS: list[dict]` — `{username, password, full_name, role, nik}` from mockData.
  - `async seed_all(session)` — idempotent seed of roles, permissions, mappings, demo users (master-data seed added in Task 20).

- [ ] **Step 1: Write failing test** `tests/test_permissions_registry.py`

```python
from app.permissions.registry import PERMISSIONS, ROLE_PERMISSIONS, ROLE_DEFS, DEMO_ACCOUNTS


def test_registry_shapes():
    assert "resident:create" in PERMISSIONS
    assert set(ROLE_PERMISSIONS) == {"warga", "staf", "sekretaris", "kades", "administrator"}
    assert ROLE_PERMISSIONS["administrator"] == ["*"]
    assert {r[0] for r in ROLE_DEFS} == set(ROLE_PERMISSIONS)
    usernames = {a["username"] for a in DEMO_ACCOUNTS}
    assert {"warga", "staf", "sekdes", "kades", "operator"} == usernames
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/permissions/registry.py`**

```python
"""Data-driven RBAC registry: permissions, role mappings, demo accounts."""

# Resource:action permission codes. Extend as new features arrive.
PERMISSIONS: list[str] = [
    "auth:me",
    "resident:create", "resident:read", "resident:update", "resident:delete",
    "resident:import", "resident:export",
    "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
]

# Role name -> permission codes. "*" means all permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me"],
    "staf": ["auth:me", "resident:read", "resident:create", "resident:update",
             "resident:import", "resident:export"],
    "sekretaris": ["auth:me", "resident:read", "resident:update",
                   "village:manage", "dusun:manage", "rw:manage", "rt:manage",
                   "family_card:manage"],
    "kades": ["auth:me", "resident:read"],
    "administrator": ["*"],
}

ROLE_DEFS: list[tuple[str, str]] = [
    ("warga", "Warga"),
    ("staf", "Staf Loket"),
    ("sekretaris", "Sekretaris Desa"),
    ("kades", "Kepala Desa"),
    ("administrator", "Admin / Operator"),
]

# Demo accounts mirrored from the frontend mockData.js `accounts` map.
DEMO_ACCOUNTS: list[dict] = [
    {"username": "warga", "password": "warga123", "full_name": "Siti Rohmah",
     "role": "warga", "nik": "3516064588020003"},
    {"username": "staf", "password": "staf123", "full_name": "Nur Aini",
     "role": "staf", "nik": None},
    {"username": "sekdes", "password": "sekdes123", "full_name": "Dewi Lestari",
     "role": "sekretaris", "nik": None},
    {"username": "kades", "password": "kades123", "full_name": "Wiwin Wildan",
     "role": "kades", "nik": None},
    {"username": "operator", "password": "operator123", "full_name": "Operator IT",
     "role": "administrator", "nik": None},
]
```

- [ ] **Step 4: Implement `app/seed/seed.py`** (roles/permissions/users portion)

```python
"""Idempotent database seeding."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.auth import Permission, Role, User
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, ROLE_DEFS, ROLE_PERMISSIONS,
)


async def seed_rbac(session: AsyncSession) -> None:
    """Seed permissions, roles, role-permission mappings, and demo users."""
    # Permissions
    existing_perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for code in PERMISSIONS:
        if code not in existing_perms:
            p = Permission(code=code)
            session.add(p)
            existing_perms[code] = p
    await session.flush()

    # Roles + mappings
    existing_roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    for name, display in ROLE_DEFS:
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, display_name=display)
            session.add(role)
            existing_roles[name] = role
        codes = ROLE_PERMISSIONS[name]
        role.permissions = (
            list(existing_perms.values()) if codes == ["*"]
            else [existing_perms[c] for c in codes]
        )
    await session.flush()

    # Demo users
    existing_users = {u.username: u for u in (await session.scalars(select(User))).all()}
    for acc in DEMO_ACCOUNTS:
        if acc["username"] in existing_users:
            continue
        session.add(User(
            username=acc["username"], nik=acc["nik"], full_name=acc["full_name"],
            hashed_password=hash_password(acc["password"]),
            role_id=existing_roles[acc["role"]].id, is_active=True,
        ))
    await session.commit()


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders (master-data seeding appended in Task 20)."""
    await seed_rbac(session)
```

Also create `app/seed/__init__.py` (empty).

- [ ] **Step 5: Run** — `pytest tests/test_permissions_registry.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/permissions app/seed tests/test_permissions_registry.py
git commit -m "feat(auth): permission registry + rbac seeding"
```

---

### Task 9: Auth repositories

**Files:**
- Create: `app/repositories/auth.py`
- Test: covered via service tests (Task 13); add `tests/test_auth_repo.py` smoke

**Interfaces:**
- Produces `UserRepository(session)`:
  - `async get_by_username(username) -> User | None`
  - `async get_by_nik(nik) -> User | None`
  - `async get_by_id(user_id) -> User | None`
- `RefreshTokenRepository(session)`:
  - `async create(user_id, token_hash, expires_at) -> RefreshToken`
  - `async get_active_by_hash(token_hash) -> RefreshToken | None`
  - `async revoke(token: RefreshToken) -> None`

- [ ] **Step 1: Write smoke test** `tests/test_auth_repo.py`

```python
import pytest
from app.repositories.auth import UserRepository, RefreshTokenRepository


@pytest.mark.asyncio
async def test_get_by_username_none(db_session):
    repo = UserRepository(db_session)
    assert await repo.get_by_username("nobody") is None
```
(Uses `db_session` fixture added in Task 13's conftest update.)

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/repositories/auth.py`**

```python
"""Repositories for auth models."""
import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import RefreshToken, User


class UserRepository:
    """Data access for User."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> User | None:
        stmt = select(User).where(User.username == username, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def get_by_nik(self, nik: str) -> User | None:
        stmt = select(User).where(User.nik == nik, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)


class RefreshTokenRepository:
    """Data access for RefreshToken."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None)
        )
        return await self.session.scalar(stmt)

    async def revoke(self, token: RefreshToken) -> None:
        from datetime import timezone
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()
```

- [ ] **Step 4: Run** — PASS (after Task 13 fixtures) or defer test; **Step 5: Commit**

```bash
git add app/repositories/auth.py tests/test_auth_repo.py
git commit -m "feat(auth): user & refresh-token repositories"
```

---

### Task 10: OTP service + Auth service

**Files:**
- Create: `app/services/otp.py`, `app/services/auth.py`
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Consumes: `UserRepository`, `RefreshTokenRepository`, `security.*`, `get_redis`, registry.
- Produces `OtpService`:
  - `async request_otp(nik: str) -> str` (stores code in Redis `otp:{nik}` with TTL; returns code for dev).
  - `async verify_otp(nik: str, code: str) -> bool`.
- `AuthService(session)`:
  - `async login_password(username, password) -> TokenPair`
  - `async login_otp(nik, code) -> TokenPair`
  - `async refresh(raw_refresh) -> TokenPair`
  - `async logout(access_payload: dict, raw_refresh: str | None) -> None` (blacklist jti in Redis until exp; revoke refresh)
  - `async is_blacklisted(jti) -> bool`
  - `permissions_for(user) -> list[str]`
  - `TokenPair = {access_token, refresh_token, token_type, expires_in}`

- [ ] **Step 1: Write failing test** `tests/test_auth_service.py`

```python
import pytest
from app.services.auth import AuthService
from app.core.exceptions import UnauthorizedError


@pytest.mark.asyncio
async def test_login_password_success(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login_password("staf", "staf123")
    assert pair["access_token"]
    assert pair["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_password_wrong(seeded_session):
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login_password("staf", "wrong")
```
(`seeded_session` fixture from Task 13 conftest runs `seed_rbac`.)

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/otp.py`**

```python
"""OTP generation/verification backed by Redis."""
import secrets

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("otp")


class OtpService:
    """Generate and verify one-time passwords stored in Redis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = get_redis()

    def _key(self, nik: str) -> str:
        return f"otp:{nik}"

    async def request_otp(self, nik: str) -> str:
        """Generate an OTP, store with TTL, return it (dev delivery)."""
        code = "".join(secrets.choice("0123456789") for _ in range(self.settings.otp_length))
        await self.redis.set(self._key(nik), code, ex=self.settings.otp_ttl_seconds)
        logger.info("OTP for %s: %s (dev)", nik, code)
        return code

    async def verify_otp(self, nik: str, code: str) -> bool:
        """Verify and consume the OTP."""
        stored = await self.redis.get(self._key(nik))
        if stored and stored == code:
            await self.redis.delete(self._key(nik))
            return True
        return False
```

- [ ] **Step 4: Implement `app/services/auth.py`**

```python
"""Authentication service: login, refresh, logout, RBAC resolution."""
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token, create_refresh_token_value, hash_token, verify_password,
)
from app.models.auth import User
from app.permissions.registry import ROLE_PERMISSIONS
from app.repositories.auth import RefreshTokenRepository, UserRepository
from app.services.otp import OtpService
import uuid


class AuthService:
    """Business logic for authentication and token lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.otp = OtpService()
        self.redis = get_redis()
        self.settings = get_settings()

    def permissions_for(self, user: User) -> list[str]:
        """Resolve effective permission codes for a user from its role."""
        return [p.code for p in user.role.permissions]

    async def _issue(self, user: User) -> dict:
        jti = str(uuid.uuid4())
        access = create_access_token(
            str(user.id), user.role.name, self.permissions_for(user), jti
        )
        raw_refresh, token_hash = create_refresh_token_value()
        expires = datetime.now(timezone.utc) + timedelta(days=self.settings.refresh_token_expire_days)
        await self.refresh_tokens.create(user.id, token_hash, expires)
        await self.session.commit()
        return {
            "access_token": access, "refresh_token": raw_refresh,
            "token_type": "bearer",
            "expires_in": self.settings.access_token_expire_minutes * 60,
        }

    async def login_password(self, username: str, password: str) -> dict:
        """Authenticate a staff user by username + password."""
        user = await self.users.get_by_username(username.strip().lower())
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Username atau kata sandi salah")
        if not user.is_active:
            raise UnauthorizedError("Akun tidak aktif")
        return await self._issue(user)

    async def login_otp(self, nik: str, code: str) -> dict:
        """Authenticate a warga by NIK + OTP."""
        if not await self.otp.verify_otp(nik, code):
            raise UnauthorizedError("Kode OTP salah atau kedaluwarsa")
        user = await self.users.get_by_nik(nik)
        if not user or not user.is_active:
            raise UnauthorizedError("Warga tidak terdaftar")
        return await self._issue(user)

    async def refresh(self, raw_refresh: str) -> dict:
        """Rotate a refresh token and issue a new pair."""
        token = await self.refresh_tokens.get_active_by_hash(hash_token(raw_refresh))
        if not token or token.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token tidak valid")
        await self.refresh_tokens.revoke(token)
        user = await self.users.get_by_id(token.user_id)
        if not user:
            raise UnauthorizedError("User tidak ditemukan")
        return await self._issue(user)

    async def logout(self, access_payload: dict, raw_refresh: str | None) -> None:
        """Blacklist the access jti and revoke the refresh token."""
        jti = access_payload.get("jti")
        exp = access_payload.get("exp")
        if jti and exp:
            ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
            await self.redis.set(f"bl:{jti}", "1", ex=ttl)
        if raw_refresh:
            token = await self.refresh_tokens.get_active_by_hash(hash_token(raw_refresh))
            if token:
                await self.refresh_tokens.revoke(token)
                await self.session.commit()

    async def is_blacklisted(self, jti: str) -> bool:
        """Return True if an access jti has been blacklisted."""
        return bool(await self.redis.get(f"bl:{jti}"))
```

- [ ] **Step 5: Run** — `pytest tests/test_auth_service.py -v` → PASS (requires Redis running for OTP; password tests do not touch Redis except logout)

- [ ] **Step 6: Commit**

```bash
git add app/services/otp.py app/services/auth.py tests/test_auth_service.py
git commit -m "feat(auth): otp + auth service (login/refresh/logout/rbac)"
```

---

### Task 11: Auth dependencies (current user + require_permission)

**Files:**
- Create: `app/dependencies/db.py`, `app/dependencies/auth.py`
- Test: exercised via Task 13 endpoint tests

**Interfaces:**
- Produces:
  - `CurrentUser` dataclass: `id: str, role: str, permissions: list[str], jti: str`.
  - `async get_current_user(request, token=Depends(oauth2_scheme), session=Depends(get_db)) -> CurrentUser` — decodes token, checks blacklist, 401 on failure.
  - `require_permission(code: str) -> Callable` dependency factory — 403 if `code` not in user permissions and `"*"` not present.

- [ ] **Step 1: Implement `app/dependencies/db.py`**

```python
"""DI re-export for DB session."""
from app.db.session import get_db  # noqa: F401
```

- [ ] **Step 2: Implement `app/dependencies/auth.py`**

```python
"""Auth dependencies: current user resolution + permission guard."""
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.services.auth import AuthService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login", auto_error=False
)


@dataclass
class CurrentUser:
    id: str
    role: str
    permissions: list[str]
    jti: str


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Decode the bearer token, reject blacklisted/invalid tokens."""
    if not token:
        raise UnauthorizedError("Tidak ada token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("Token tidak valid")
    svc = AuthService(session)
    if await svc.is_blacklisted(payload.get("jti", "")):
        raise UnauthorizedError("Token sudah logout")
    return CurrentUser(
        id=payload["sub"], role=payload["role"],
        permissions=payload.get("permissions", []), jti=payload["jti"],
    )


def require_permission(code: str) -> Callable:
    """Dependency factory enforcing a single permission code."""

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions or code in user.permissions:
            return user
        raise ForbiddenError(f"Tidak memiliki izin: {code}")

    return _dep
```

- [ ] **Step 3: Commit**

```bash
git add app/dependencies
git commit -m "feat(auth): current-user + require_permission dependencies"
```

---

### Task 12: Auth schemas + router

**Files:**
- Create: `app/schemas/auth.py`, `app/api/v1/auth.py`
- Modify: `app/api/v1/__init__.py` (include auth router)

**Interfaces:**
- Consumes: `AuthService`, `get_current_user`, `require_permission("auth:me")`.
- Produces routes under `/api/v1/auth`: `POST /login`, `POST /request-otp`, `POST /verify-otp`, `POST /refresh`, `POST /logout`, `GET /me`. All return the envelope.

- [ ] **Step 1: Implement `app/schemas/auth.py`**

```python
"""Auth request/response schemas."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str
    password: str


class RequestOtpRequest(BaseModel):
    nik: str = Field(min_length=8, max_length=20)


class VerifyOtpRequest(BaseModel):
    nik: str
    code: str


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenData(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeData(BaseModel):
    id: str
    role: str
    permissions: list[str]


class OtpRequestedData(BaseModel):
    nik: str
    # dev only: code echoed back so the frontend/test can proceed without WhatsApp
    dev_code: str | None = None
```

- [ ] **Step 2: Implement `app/api/v1/auth.py`**

```python
"""Authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.response import success_response
from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.schemas.auth import (
    LoginRequest, LogoutRequest, RefreshRequest, RequestOtpRequest, VerifyOtpRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Staff login with username + password."""
    pair = await AuthService(session).login_password(body.username, body.password)
    return success_response(pair, "Login berhasil")


@router.post("/request-otp")
async def request_otp(body: RequestOtpRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Warga requests an OTP for their NIK."""
    code = await AuthService(session).otp.request_otp(body.nik)
    data = {"nik": body.nik}
    if get_settings().app_env != "production":
        data["dev_code"] = code
    return success_response(data, "OTP dikirim")


@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Warga verifies NIK + OTP and receives tokens."""
    pair = await AuthService(session).login_otp(body.nik, body.code)
    return success_response(pair, "Login berhasil")


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Rotate the refresh token."""
    pair = await AuthService(session).refresh(body.refresh_token)
    return success_response(pair, "Token diperbarui")


@router.post("/logout")
async def logout(
    body: LogoutRequest, request: Request, session: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Blacklist the current access token and revoke refresh."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    await AuthService(session).logout(payload, body.refresh_token)
    return success_response(None, "Logout berhasil")


@router.get("/me")
async def me(user: CurrentUser = Depends(require_permission("auth:me"))) -> dict:
    """Return the current identity and permissions."""
    return success_response(
        {"id": user.id, "role": user.role, "permissions": user.permissions}
    )
```

- [ ] **Step 3: Register router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import auth, health
api_router.include_router(health.router)
api_router.include_router(auth.router)
```

- [ ] **Step 4: Commit**

```bash
git add app/schemas/auth.py app/api/v1/auth.py app/api/v1/__init__.py
git commit -m "feat(auth): auth schemas + endpoints"
```

---

### Task 13: Auth integration tests + test fixtures

**Files:**
- Modify: `tests/conftest.py` (add DB + seeded fixtures)
- Create: `tests/test_auth.py`

**Interfaces:**
- Produces fixtures: `db_session` (SQLite in-memory, tables created), `seeded_session` (db_session + `seed_rbac`), `client` (already exists), `auth_client` factory for logged-in requests.

- [ ] **Step 1: Extend `tests/conftest.py`**

```python
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.seed.seed import seed_rbac

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture
async def _engine():
    engine = create_async_engine(TEST_DB_URL, future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    async with maker() as session:
        yield session


@pytest_asyncio.fixture
async def seeded_session(db_session):
    await seed_rbac(db_session)
    return db_session


@pytest_asyncio.fixture
async def client(_engine):
    app = create_app()
    maker = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    # seed once for endpoint tests
    async with maker() as s:
        await seed_rbac(s)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
```

Note: OTP/logout tests need Redis; mark them with `@pytest.mark.skipif` when `get_redis().ping()` fails, or use `fakeredis` (add `fakeredis>=2.26` to dev deps and monkeypatch `app.core.redis._client`). Recommended: add `fakeredis` and a `autouse` fixture setting `app.core.redis._client = fakeredis.aioredis.FakeRedis(decode_responses=True)`.

- [ ] **Step 2: Write `tests/test_auth.py`**

```python
import pytest


@pytest.mark.asyncio
async def test_login_all_demo_accounts(client):
    for username, password in [
        ("staf", "staf123"), ("sekdes", "sekdes123"),
        ("kades", "kades123"), ("operator", "operator123"),
    ]:
        resp = await client.post("/api/v1/auth/login",
                                 json={"username": username, "password": password})
        assert resp.status_code == 200, username
        assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_login_bad_password(client):
    resp = await client.post("/api/v1/auth/login",
                             json={"username": "staf", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client):
    login = await client.post("/api/v1/auth/login",
                              json={"username": "operator", "password": "operator123"})
    token = login.json()["data"]["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "*" in resp.json()["data"]["permissions"]


@pytest.mark.asyncio
async def test_otp_flow(client):
    req = await client.post("/api/v1/auth/request-otp", json={"nik": "3516064588020003"})
    assert req.status_code == 200
    code = req.json()["data"]["dev_code"]
    verify = await client.post("/api/v1/auth/verify-otp",
                               json={"nik": "3516064588020003", "code": code})
    assert verify.status_code == 200
    assert verify.json()["data"]["access_token"]
```

- [ ] **Step 3: Run full auth suite** — `pytest tests/test_auth.py -v` → PASS

- [ ] **Step 4: Commit**

```bash
git add tests/conftest.py tests/test_auth.py pyproject.toml
git commit -m "test(auth): integration tests + fakeredis/db fixtures"
```

---

# PHASE 3 — MASTER DATA

### Task 14: Master-data models + migration

**Files:**
- Modify: `app/models/master.py`
- Create: migration
- Test: `tests/test_master_models.py`

**Interfaces:**
- Produces models (all `UUIDMixin, TimestampMixin, SoftDeleteMixin, Base`):
  - `Village`: `name, slogan, kecamatan, kabupaten, provinsi`.
  - `Dusun`: `village_id FK, name`.
  - `RW`: `dusun_id FK, number`.
  - `RT`: `rw_id FK, number`.
  - `FamilyCard`: `village_id FK, kk_number (unique), address, head_resident_id (nullable)`.
  - `Resident`: `village_id FK, nik (unique), full_name, family_card_id FK|None, rt_id FK|None, gender, birth_place, birth_date, occupation, phone, address`.

- [ ] **Step 1: Write failing test** `tests/test_master_models.py`

```python
from app.models.master import Village, Dusun, RW, RT, FamilyCard, Resident


def test_master_tables():
    assert Village.__tablename__ == "villages"
    assert Dusun.__tablename__ == "dusun"
    assert RW.__tablename__ == "rw"
    assert RT.__tablename__ == "rt"
    assert FamilyCard.__tablename__ == "family_cards"
    assert Resident.__tablename__ == "residents"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/models/master.py`**

```python
"""Master data models: village hierarchy, family cards, residents."""
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Village(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "villages"
    name: Mapped[str] = mapped_column(String(150), index=True)
    slogan: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kecamatan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Dusun(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "dusun"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)


class RW(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rw"
    dusun_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("dusun.id"), index=True)
    number: Mapped[str] = mapped_column(String(10))


class RT(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "rt"
    rw_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("rw.id"), index=True)
    number: Mapped[str] = mapped_column(String(10))


class FamilyCard(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "family_cards"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    kk_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    head_resident_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class Resident(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "residents"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    nik: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    family_card_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("family_cards.id"), nullable=True, index=True
    )
    rt_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rt.id"), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # L/P
    birth_place: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
```

- [ ] **Step 4: Run** — `pytest tests/test_master_models.py -v` → PASS

- [ ] **Step 5: Generate + apply migration**

```bash
alembic revision --autogenerate -m "master data tables"
alembic upgrade head
```
(If Task 6's `users.resident_id` FK was deferred, this migration also adds it.)

- [ ] **Step 6: Commit**

```bash
git add app/models/master.py alembic/versions tests/test_master_models.py
git commit -m "feat(master): village hierarchy + resident models and migration"
```

---

### Task 15: Base repository (generic CRUD + pagination)

**Files:**
- Create: `app/repositories/base.py`, `app/dependencies/pagination.py`
- Test: `tests/test_base_repo.py`

**Interfaces:**
- Produces `BaseRepository[ModelT]`:
  - `__init__(session, model)`
  - `async get(id) -> ModelT | None` (excludes soft-deleted)
  - `async list(page, size, filters: dict | None, search: tuple[list[Column], str] | None) -> tuple[list[ModelT], int]`
  - `async create(**data) -> ModelT`
  - `async update(obj, **data) -> ModelT`
  - `async soft_delete(obj) -> None`
- `PaginationParams` dep: `page: int = 1, size: int = 20` (size capped at 100).

- [ ] **Step 1: Write failing test** `tests/test_base_repo.py`

```python
import pytest
from app.repositories.base import BaseRepository
from app.models.master import Village


@pytest.mark.asyncio
async def test_create_and_get(db_session):
    repo = BaseRepository(db_session, Village)
    v = await repo.create(name="Desa Kopo")
    await db_session.commit()
    got = await repo.get(v.id)
    assert got.name == "Desa Kopo"


@pytest.mark.asyncio
async def test_soft_delete_hides(db_session):
    repo = BaseRepository(db_session, Village)
    v = await repo.create(name="X")
    await db_session.commit()
    await repo.soft_delete(v)
    await db_session.commit()
    assert await repo.get(v.id) is None
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/repositories/base.py`**

```python
"""Generic repository with soft-delete-aware CRUD and pagination."""
from datetime import datetime, timezone
from typing import Generic, TypeVar

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Reusable async CRUD scoped to non-soft-deleted rows."""

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def _base_stmt(self):
        return select(self.model).where(self.model.deleted_at.is_(None))

    async def get(self, id_):
        stmt = self._base_stmt().where(self.model.id == id_)
        return await self.session.scalar(stmt)

    async def list(self, page=1, size=20, filters=None, search=None):
        stmt = self._base_stmt()
        if filters:
            for field, value in filters.items():
                if value is not None:
                    stmt = stmt.where(getattr(self.model, field) == value)
        if search:
            columns, term = search
            if term:
                stmt = stmt.where(or_(*[c.ilike(f"%{term}%") for c in columns]))
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        stmt = stmt.order_by(self.model.created_at.desc()).offset((page - 1) * size).limit(size)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def create(self, **data):
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj, **data):
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        await self.session.flush()
        return obj

    async def soft_delete(self, obj) -> None:
        obj.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
```

- [ ] **Step 4: Implement `app/dependencies/pagination.py`**

```python
"""Pagination query params dependency."""
from dataclasses import dataclass

from fastapi import Query


@dataclass
class PaginationParams:
    page: int
    size: int


def pagination_params(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
) -> PaginationParams:
    """Parse and clamp pagination query params."""
    return PaginationParams(page=page, size=size)
```

- [ ] **Step 5: Run** — `pytest tests/test_base_repo.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/repositories/base.py app/dependencies/pagination.py tests/test_base_repo.py
git commit -m "feat(master): generic base repository + pagination dependency"
```

---

### Task 16: Master-data schemas + services

**Files:**
- Create: `app/schemas/master.py`, `app/services/master.py`
- Test: `tests/test_master_service.py`

**Interfaces:**
- Produces Pydantic schemas per entity: `<Entity>Create`, `<Entity>Update`, `<Entity>Read` (all `from_attributes=True`).
- Produces service classes wrapping `BaseRepository`: `VillageService, DusunService, RWService, RTService, FamilyCardService, ResidentService`, each with `create/get_or_404/list/update/delete`. `ResidentService.list` supports `search` over `nik, full_name` and `filters` `{rt_id, family_card_id, village_id}`.

- [ ] **Step 1: Write failing test** `tests/test_master_service.py`

```python
import pytest
from app.services.master import ResidentService, VillageService
from app.core.exceptions import NotFoundError


@pytest.mark.asyncio
async def test_resident_crud(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    svc = ResidentService(db_session)
    r = await svc.create({"nik": "1", "full_name": "Budi", "village_id": village.id})
    assert r.full_name == "Budi"
    got = await svc.get_or_404(r.id)
    assert got.nik == "1"
    await svc.update(r.id, {"occupation": "Petani"})
    items, total = await svc.list(page=1, size=10, search="Budi")
    assert total == 1
    await svc.delete(r.id)
    with pytest.raises(NotFoundError):
        await svc.get_or_404(r.id)
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/schemas/master.py`**

```python
"""Master data schemas."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class VillageCreate(BaseModel):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class VillageUpdate(BaseModel):
    name: str | None = None
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class VillageRead(_Read):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class DusunCreate(BaseModel):
    village_id: UUID
    name: str


class DusunUpdate(BaseModel):
    name: str | None = None


class DusunRead(_Read):
    village_id: UUID
    name: str


class RWCreate(BaseModel):
    dusun_id: UUID
    number: str


class RWUpdate(BaseModel):
    number: str | None = None


class RWRead(_Read):
    dusun_id: UUID
    number: str


class RTCreate(BaseModel):
    rw_id: UUID
    number: str


class RTUpdate(BaseModel):
    number: str | None = None


class RTRead(_Read):
    rw_id: UUID
    number: str


class FamilyCardCreate(BaseModel):
    village_id: UUID
    kk_number: str
    address: str | None = None


class FamilyCardUpdate(BaseModel):
    kk_number: str | None = None
    address: str | None = None


class FamilyCardRead(_Read):
    village_id: UUID
    kk_number: str
    address: str | None = None


class ResidentCreate(BaseModel):
    village_id: UUID
    nik: str
    full_name: str
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None


class ResidentUpdate(BaseModel):
    full_name: str | None = None
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None


class ResidentRead(_Read):
    village_id: UUID
    nik: str
    full_name: str
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None
```

- [ ] **Step 4: Implement `app/services/master.py`**

```python
"""Master data services wrapping BaseRepository."""
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.models.master import RT, RW, Dusun, FamilyCard, Resident, Village
from app.repositories.base import BaseRepository


class _CrudService:
    """Common CRUD orchestration for a single model."""
    model = None
    name = "Resource"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, self.model)

    async def create(self, data: dict):
        obj = await self.repo.create(**data)
        await self.session.commit()
        return obj

    async def get_or_404(self, id_):
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError(f"{self.name} tidak ditemukan")
        return obj

    async def list(self, page=1, size=20, filters=None, search=None):
        search_arg = None
        if search and getattr(self, "search_columns", None):
            search_arg = (self.search_columns, search)
        return await self.repo.list(page=page, size=size, filters=filters, search=search_arg)

    async def update(self, id_, data: dict):
        obj = await self.get_or_404(id_)
        obj = await self.repo.update(obj, **data)
        await self.session.commit()
        return obj

    async def delete(self, id_) -> None:
        obj = await self.get_or_404(id_)
        await self.repo.soft_delete(obj)
        await self.session.commit()


class VillageService(_CrudService):
    model = Village
    name = "Village"


class DusunService(_CrudService):
    model = Dusun
    name = "Dusun"


class RWService(_CrudService):
    model = RW
    name = "RW"


class RTService(_CrudService):
    model = RT
    name = "RT"


class FamilyCardService(_CrudService):
    model = FamilyCard
    name = "Kartu Keluarga"


class ResidentService(_CrudService):
    model = Resident
    name = "Penduduk"

    @property
    def search_columns(self):
        return [Resident.nik, Resident.full_name]
```

- [ ] **Step 5: Run** — `pytest tests/test_master_service.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/schemas/master.py app/services/master.py tests/test_master_service.py
git commit -m "feat(master): schemas + crud services"
```

---

### Task 17: Master-data routers (village/dusun/rw/rt/family-card/resident)

**Files:**
- Create: `app/api/v1/master.py`
- Modify: `app/api/v1/__init__.py`
- Test: `tests/test_master_data.py`

**Interfaces:**
- Consumes: master services, `require_permission`, `pagination_params`, `Page`, `success_response`.
- Produces routes: `/villages`, `/dusun`, `/rw`, `/rt`, `/family-cards`, `/residents` — each with `POST /`, `GET /`, `GET /{id}`, `PUT /{id}`, `DELETE /{id}`; residents list also accepts `?search=&rt_id=&family_card_id=`.

- [ ] **Step 1: Write failing test** `tests/test_master_data.py`

```python
import pytest


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_village_crud_flow(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    created = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    assert created.status_code == 200
    vid = created.json()["data"]["id"]
    listed = await client.get("/api/v1/villages", headers=h)
    assert listed.json()["data"]["total"] >= 1
    got = await client.get(f"/api/v1/villages/{vid}", headers=h)
    assert got.json()["data"]["name"] == "Desa Kopo"


@pytest.mark.asyncio
async def test_resident_requires_permission(client):
    # kades has only resident:read — creating must 403
    tok = await _token(client, "kades", "kades123")
    h = {"Authorization": f"Bearer {tok}"}
    v = await client.post("/api/v1/villages", json={"name": "V"},
                          headers={"Authorization": f"Bearer {await _token(client)}"})
    vid = v.json()["data"]["id"]
    resp = await client.post("/api/v1/residents",
                             json={"nik": "9", "full_name": "Z", "village_id": vid}, headers=h)
    assert resp.status_code == 403
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/api/v1/master.py`**

```python
"""Master data CRUD endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.master import (
    DusunCreate, DusunRead, DusunUpdate, FamilyCardCreate, FamilyCardRead, FamilyCardUpdate,
    RTCreate, RTRead, RTUpdate, RWCreate, RWRead, RWUpdate, ResidentCreate, ResidentRead,
    ResidentUpdate, VillageCreate, VillageRead, VillageUpdate,
)
from app.services.master import (
    DusunService, FamilyCardService, RTService, RWService, ResidentService, VillageService,
)

router = APIRouter(tags=["master-data"])


def _page(items, total, p: PaginationParams, schema) -> dict:
    return {"items": [schema.model_validate(i).model_dump(mode="json") for i in items],
            "total": total, "page": p.page, "size": p.size}


# ---- Villages ----
@router.post("/villages")
async def create_village(body: VillageCreate, session: AsyncSession = Depends(get_db),
                         _=Depends(require_permission("village:manage"))) -> dict:
    obj = await VillageService(session).create(body.model_dump(exclude_unset=True))
    return success_response(VillageRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/villages")
async def list_villages(session: AsyncSession = Depends(get_db),
                        p: PaginationParams = Depends(pagination_params),
                        _=Depends(require_permission("village:manage"))) -> dict:
    items, total = await VillageService(session).list(p.page, p.size)
    return success_response(_page(items, total, p, VillageRead))


@router.get("/villages/{item_id}")
async def get_village(item_id: UUID, session: AsyncSession = Depends(get_db),
                      _=Depends(require_permission("village:manage"))) -> dict:
    obj = await VillageService(session).get_or_404(item_id)
    return success_response(VillageRead.model_validate(obj).model_dump(mode="json"))


@router.put("/villages/{item_id}")
async def update_village(item_id: UUID, body: VillageUpdate, session: AsyncSession = Depends(get_db),
                         _=Depends(require_permission("village:manage"))) -> dict:
    obj = await VillageService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(VillageRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/villages/{item_id}")
async def delete_village(item_id: UUID, session: AsyncSession = Depends(get_db),
                         _=Depends(require_permission("village:manage"))) -> dict:
    await VillageService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- Dusun / RW / RT / FamilyCard follow the same pattern with their own
# permission codes (dusun:manage, rw:manage, rt:manage, family_card:manage)
# and schema trio. Implement each block identically to Villages. ----
# (Full blocks omitted here for brevity in the plan preview; the implementer
#  MUST write each of the four exactly like the Village block above, swapping
#  Service, schema, path, and permission code.)


# ---- Residents (with search + filters) ----
@router.post("/residents")
async def create_resident(body: ResidentCreate, session: AsyncSession = Depends(get_db),
                          _=Depends(require_permission("resident:create"))) -> dict:
    obj = await ResidentService(session).create(body.model_dump(exclude_unset=True))
    return success_response(ResidentRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/residents")
async def list_residents(session: AsyncSession = Depends(get_db),
                         p: PaginationParams = Depends(pagination_params),
                         search: str | None = Query(None),
                         rt_id: UUID | None = Query(None),
                         family_card_id: UUID | None = Query(None),
                         _=Depends(require_permission("resident:read"))) -> dict:
    filters = {"rt_id": rt_id, "family_card_id": family_card_id}
    items, total = await ResidentService(session).list(p.page, p.size, filters=filters, search=search)
    return success_response(_page(items, total, p, ResidentRead))


@router.get("/residents/{item_id}")
async def get_resident(item_id: UUID, session: AsyncSession = Depends(get_db),
                       _=Depends(require_permission("resident:read"))) -> dict:
    obj = await ResidentService(session).get_or_404(item_id)
    return success_response(ResidentRead.model_validate(obj).model_dump(mode="json"))


@router.put("/residents/{item_id}")
async def update_resident(item_id: UUID, body: ResidentUpdate, session: AsyncSession = Depends(get_db),
                          _=Depends(require_permission("resident:update"))) -> dict:
    obj = await ResidentService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(ResidentRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/residents/{item_id}")
async def delete_resident(item_id: UUID, session: AsyncSession = Depends(get_db),
                          _=Depends(require_permission("resident:delete"))) -> dict:
    await ResidentService(session).delete(item_id)
    return success_response(None, "Dihapus")
```

Note to implementer: the four omitted blocks (Dusun, RW, RT, FamilyCard) are **required** — write each one as a full copy of the Village block, substituting: service (`DusunService`…), schemas (`DusunCreate/Read/Update`…), path (`/dusun`, `/rw`, `/rt`, `/family-cards`), and permission code (`dusun:manage`, `rw:manage`, `rt:manage`, `family_card:manage`). Do not use shared factory magic that obscures the routes in `/docs`.

- [ ] **Step 4: Register router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import auth, health, master
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
```

- [ ] **Step 5: Run** — `pytest tests/test_master_data.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/v1/master.py app/api/v1/__init__.py tests/test_master_data.py
git commit -m "feat(master): crud endpoints for village hierarchy + residents"
```

---

### Task 18: Resident Excel import/export

**Files:**
- Create: `app/services/excel.py`
- Modify: `app/api/v1/master.py` (add `/residents/import`, `/residents/export`)
- Test: `tests/test_excel.py`

**Interfaces:**
- Consumes: `ResidentService`, `openpyxl`.
- Produces `ResidentExcelService(session)`:
  - `async import_bytes(file_bytes, village_id) -> dict` → `{"imported": int, "errors": [{"row": int, "message": str}]}`. Columns: `nik, full_name, gender, birth_place, birth_date, occupation, phone, address`.
  - `async export_bytes(filters) -> bytes` (xlsx).
- Routes: `POST /residents/import` (multipart file + `village_id` query), `GET /residents/export`.

- [ ] **Step 1: Write failing test** `tests/test_excel.py`

```python
import io
import openpyxl
import pytest
from app.services.excel import ResidentExcelService
from app.services.master import VillageService


def _wb(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["nik", "full_name", "gender", "birth_place", "birth_date",
               "occupation", "phone", "address"])
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_residents(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    data = _wb([["3201", "Budi", "L", "Bogor", "1990-01-01", "Petani", "0812", "Jl A"],
                ["", "Invalid", "L", "", "", "", "", ""]])
    result = await ResidentExcelService(db_session).import_bytes(data, village.id)
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3


@pytest.mark.asyncio
async def test_export_residents(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    out = await ResidentExcelService(db_session).export_bytes({"village_id": village.id})
    assert out[:2] == b"PK"  # xlsx is a zip
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/excel.py`**

```python
"""Resident Excel import/export."""
import io
from datetime import date, datetime

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.master import ResidentService

COLUMNS = ["nik", "full_name", "gender", "birth_place", "birth_date",
           "occupation", "phone", "address"]


class ResidentExcelService:
    """Import residents from and export residents to xlsx."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.residents = ResidentService(session)

    @staticmethod
    def _parse_date(value) -> date | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        return datetime.strptime(str(value), "%Y-%m-%d").date()

    async def import_bytes(self, file_bytes: bytes, village_id) -> dict:
        """Import residents; return counts + per-row errors."""
        wb = openpyxl.load_workbook(io.BytesIO(file_bytes))
        ws = wb.active
        header = [str(c.value).strip().lower() if c.value else "" for c in ws[1]]
        imported, errors = 0, []
        for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
            record = dict(zip(header, row))
            try:
                nik = str(record.get("nik") or "").strip()
                name = str(record.get("full_name") or "").strip()
                if not nik or not name:
                    raise ValueError("nik dan full_name wajib diisi")
                await self.residents.repo.create(
                    village_id=village_id, nik=nik, full_name=name,
                    gender=(record.get("gender") or None),
                    birth_place=(record.get("birth_place") or None),
                    birth_date=self._parse_date(record.get("birth_date")),
                    occupation=(record.get("occupation") or None),
                    phone=(str(record["phone"]) if record.get("phone") else None),
                    address=(record.get("address") or None),
                )
                imported += 1
            except Exception as exc:  # row-level failure isolated
                errors.append({"row": idx, "message": str(exc)})
        await self.session.commit()
        return {"imported": imported, "errors": errors}

    async def export_bytes(self, filters: dict | None = None) -> bytes:
        """Export residents matching filters to xlsx bytes."""
        items, _ = await self.residents.list(page=1, size=100000, filters=filters or {})
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Residents"
        ws.append(COLUMNS)
        for r in items:
            ws.append([r.nik, r.full_name, r.gender, r.birth_place,
                       r.birth_date.isoformat() if r.birth_date else "",
                       r.occupation, r.phone, r.address])
        buf = io.BytesIO()
        wb.save(buf)
        return buf.getvalue()
```

- [ ] **Step 4: Add routes to `app/api/v1/master.py`**

```python
import io
from fastapi import File, UploadFile
from fastapi.responses import StreamingResponse
from app.services.excel import ResidentExcelService


@router.post("/residents/import")
async def import_residents(village_id: UUID, file: UploadFile = File(...),
                           session: AsyncSession = Depends(get_db),
                           _=Depends(require_permission("resident:import"))) -> dict:
    content = await file.read()
    result = await ResidentExcelService(session).import_bytes(content, village_id)
    return success_response(result, "Import selesai")


@router.get("/residents/export")
async def export_residents(village_id: UUID | None = Query(None),
                           session: AsyncSession = Depends(get_db),
                           _=Depends(require_permission("resident:export"))):
    data = await ResidentExcelService(session).export_bytes({"village_id": village_id})
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=residents.xlsx"},
    )
```
Note: register `/residents/import` and `/residents/export` **before** `/residents/{item_id}` is fine since they are distinct paths, but ensure the static routes are declared before the `{item_id}` route in the file to avoid path-param capture.

- [ ] **Step 5: Run** — `pytest tests/test_excel.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/excel.py app/api/v1/master.py tests/test_excel.py
git commit -m "feat(master): resident excel import/export"
```

---

### Task 19: Master-data seeding from mockData

**Files:**
- Modify: `app/seed/seed.py` (add `seed_master`, extend `seed_all`)
- Create: `app/seed/data.py` (dusun list + residents extracted from mockData)
- Test: `tests/test_seed_master.py`

**Interfaces:**
- Produces: `async seed_master(session)` — creates Desa Kopo village, dusun (Krajan, Sumber, Ngemplak, Kopo Wetan), and residents from `mockData.js` `masterData`. Idempotent. `seed_all` now runs `seed_rbac` then `seed_master`.

- [ ] **Step 1: Implement `app/seed/data.py`**

```python
"""Static seed data mirrored from the frontend mockData.js."""

VILLAGE = {
    "name": "Desa Kopo", "slogan": "Kopo Kita", "kecamatan": "Cisarua",
    "kabupaten": "Kabupaten Bogor", "provinsi": "Jawa Barat",
}

DUSUN = ["Krajan", "Sumber", "Ngemplak", "Kopo Wetan"]

# (nik_suffix, name, kk_suffix, dusun, rt, rw) — from mockData.js masterData
RESIDENTS = [
    ("0003", "Siti Rohmah", "7890", "Krajan", "002", "001"),
    ("0011", "Ahmad Fauzi", "1204", "Krajan", "001", "001"),
    ("0027", "Andi Wijaya", "5567", "Sumber", "003", "002"),
    ("0042", "Dewi Lestari", "8890", "Sumber", "004", "002"),
    ("0058", "Bambang Sujarwo", "3321", "Ngemplak", "002", "003"),
    ("0064", "Rina Handayani", "4410", "Krajan", "003", "001"),
    ("0071", "Sugeng Riyadi", "2290", "Kopo Wetan", "001", "004"),
    ("0085", "Yanto Prasetyo", "6631", "Sumber", "002", "002"),
    ("0092", "Wahyuni", "7742", "Ngemplak", "004", "003"),
    ("0106", "Slamet Riadi", "8853", "Krajan", "001", "001"),
    ("0114", "Kartika Sari", "9964", "Kopo Wetan", "002", "004"),
    ("0129", "Joko Purnomo", "1075", "Sumber", "003", "002"),
    ("0137", "Fitriani", "2186", "Ngemplak", "001", "003"),
    ("0145", "Agus Setiawan", "3297", "Krajan", "004", "001"),
    ("0153", "Maya Puspita", "4308", "Kopo Wetan", "003", "004"),
    ("0168", "Hendra Gunawan", "5419", "Sumber", "001", "002"),
    ("0176", "Lilis Suryani", "6520", "Ngemplak", "002", "003"),
    ("0184", "Rudi Hartono", "7631", "Krajan", "003", "001"),
    ("0192", "Nia Ramadhani", "8742", "Kopo Wetan", "004", "004"),
    ("0207", "Eko Prasetyo", "9853", "Sumber", "002", "002"),
    ("0215", "Wati Suminar", "1064", "Ngemplak", "003", "003"),
    ("0223", "Dedi Kurniawan", "2175", "Krajan", "001", "001"),
    ("0231", "Sri Wahyuni", "3286", "Kopo Wetan", "002", "004"),
    ("0248", "Tono Sudrajat", "4397", "Sumber", "004", "002"),
    ("0256", "Yeni Marlina", "5408", "Ngemplak", "001", "003"),
    ("0264", "Asep Saepudin", "6519", "Krajan", "002", "001"),
    ("0272", "Nining Kusrini", "7620", "Kopo Wetan", "003", "004"),
    ("0289", "Budi Santoso", "8731", "Sumber", "001", "002"),
    ("0297", "Nur Aini", "9842", "Krajan", "004", "001"),
    ("0305", "Dewi Anggraeni", "1053", "Ngemplak", "002", "003"),
    ("0313", "Sutrisno", "2164", "Kopo Wetan", "001", "004"),
    ("0321", "Ratna Kusuma", "3275", "Sumber", "003", "002"),
    ("0338", "Wawan Kurniadi", "4386", "Krajan", "001", "001"),
    ("0346", "Indah Permatasari", "5497", "Ngemplak", "004", "003"),
    ("0354", "Hari Mulyono", "6508", "Kopo Wetan", "002", "004"),
    ("0362", "Ani Setiawati", "7619", "Sumber", "003", "002"),
]
```

- [ ] **Step 2: Add `seed_master` to `app/seed/seed.py`**

```python
from app.models.master import RT, RW, Dusun, Resident, Village
from app.seed.data import DUSUN, RESIDENTS, VILLAGE
from sqlalchemy import select


async def seed_master(session: AsyncSession) -> None:
    """Seed the village, dusun, RW/RT, and residents from mockData."""
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        village = Village(**VILLAGE)
        session.add(village)
        await session.flush()

    dusun_map = {d.name: d for d in (await session.scalars(select(Dusun))).all()}
    for name in DUSUN:
        if name not in dusun_map:
            d = Dusun(village_id=village.id, name=name)
            session.add(d)
            dusun_map[name] = d
    await session.flush()

    # Build RW/RT lazily keyed by (dusun, rw) and (rw_obj, rt)
    rw_cache: dict[tuple[str, str], RW] = {}
    rt_cache: dict[tuple, RT] = {}
    existing_niks = {
        r.nik for r in (await session.scalars(select(Resident))).all()
    }
    for nik_suffix, name, _kk, dusun_name, rt_no, rw_no in RESIDENTS:
        nik = f"3516{nik_suffix.zfill(12)[:12]}"  # deterministic synthetic NIK
        if nik in existing_niks:
            continue
        dusun = dusun_map[dusun_name]
        rw = rw_cache.get((dusun_name, rw_no))
        if rw is None:
            rw = RW(dusun_id=dusun.id, number=rw_no)
            session.add(rw)
            await session.flush()
            rw_cache[(dusun_name, rw_no)] = rw
        rt = rt_cache.get((rw.id, rt_no))
        if rt is None:
            rt = RT(rw_id=rw.id, number=rt_no)
            session.add(rt)
            await session.flush()
            rt_cache[(rw.id, rt_no)] = rt
        session.add(Resident(village_id=village.id, nik=nik, full_name=name, rt_id=rt.id))
    await session.commit()


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders."""
    await seed_rbac(session)
    await seed_master(session)
```

- [ ] **Step 3: Write test** `tests/test_seed_master.py`

```python
import pytest
from sqlalchemy import func, select
from app.models.master import Resident
from app.seed.seed import seed_master


@pytest.mark.asyncio
async def test_seed_master_idempotent(db_session):
    await seed_master(db_session)
    await seed_master(db_session)
    count = await db_session.scalar(select(func.count()).select_from(Resident))
    assert count == 36
```

- [ ] **Step 4: Run** — `pytest tests/test_seed_master.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/seed/data.py app/seed/seed.py tests/test_seed_master.py
git commit -m "feat(master): seed village/dusun/rt/residents from mockData"
```

---

### Task 20: Seed CLI + startup wiring

**Files:**
- Create: `app/seed/__main__.py` (CLI: `python -m app.seed`)
- Modify: `app/main.py` (optional startup log; do NOT auto-seed in prod)
- Test: manual

**Interfaces:**
- Produces: `python -m app.seed` runs `seed_all` against the configured database.

- [ ] **Step 1: Implement `app/seed/__main__.py`**

```python
"""CLI entry: python -m app.seed — seed the configured database."""
import asyncio

from app.db.session import AsyncSessionLocal
from app.seed.seed import seed_all


async def _run() -> None:
    async with AsyncSessionLocal() as session:
        await seed_all(session)
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(_run())
```

- [ ] **Step 2: Manual verification**

```bash
docker compose up -d redis
alembic upgrade head
python -m app.seed
```
Expected: "Seeding complete." and querying the DB shows 5 users + 36 residents.

- [ ] **Step 3: Commit**

```bash
git add app/seed/__main__.py
git commit -m "feat(seed): CLI entrypoint for database seeding"
```

---

### Task 21: Full-suite verification + README run guide

**Files:**
- Modify: `README.md`
- Test: full `pytest`

**Interfaces:** none (documentation + gate).

- [ ] **Step 1: Run the whole test suite**

Run: `pytest -v`
Expected: all tests PASS (OTP/logout tests use fakeredis; no external Redis required for tests).

- [ ] **Step 2: Manual end-to-end smoke against real Postgres**

```bash
docker compose up -d redis
# ensure DATABASE_URL points at local postgres and DB `sipades` exists
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload
```
Verify in `/docs`: login as `operator/operator123`, call `GET /residents` (200, 36 items), `GET /health/ready` (database+redis true).

- [ ] **Step 3: Write `README.md` run guide** (setup, env, migrate, seed, run, test sections — concrete commands from above).

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: backend run guide + foundation verification"
```

---

## Self-Review

**1. Spec coverage:**
- Phase 1 (infra, health, config, logger, exception handler, CORS, versioning, DI, Redis, folder structure) → Tasks 1-5. ✓
- Phase 2 (User/Role/RefreshToken/OTP models, all 6 auth endpoints, JWT, refresh, RBAC, blacklist, session) → Tasks 6-13. ✓ (OTP stored in Redis per spec; blacklist via Redis jti.)
- Phase 3 (Village/Dusun/RW/RT/Resident/FamilyCard CRUD, pagination, filter, search, Excel import/export, seeding) → Tasks 14-20. ✓
- Cross-cutting (envelope, exception handler, logging, Alembic-only, tests) → Tasks 2, 5, 13, 21. ✓
- DoD (boot, connect Postgres, migrate, 5 accounts auth, CRUD+import/export, tests green) → Task 21. ✓

**2. Placeholder scan:** The four master CRUD blocks (Dusun/RW/RT/FamilyCard) in Task 17 are described-not-shown for brevity but the Village block is fully shown and the note makes the substitution mechanical and explicit (service/schema/path/permission). This is the one intentional compression; every other step has complete code. Acceptable because the pattern is shown verbatim once and the substitution table is exact.

**3. Type consistency:** `create_access_token(subject, role, permissions, jti)` — consistent across security, auth service, tests. `TokenPair` dict keys (`access_token, refresh_token, token_type, expires_in`) consistent across service, schemas, tests. `require_permission(code)` codes match `PERMISSIONS` registry (`resident:*`, `village:manage`, etc.). `BaseRepository.list` signature consistent with service `list`. Synthetic NIK in seed (`3516` + padded suffix) is internal-only and does not collide with the demo warga NIK `3516064588020003` used in auth tests (different value, and seed users vs residents are separate tables).

**Note on one cross-table dependency:** `User.resident_id` FK → `residents.id` requires the residents table. Task 6 note instructs deferring the FK constraint if auth is built before master models; Task 14 adds it. Implementer must honor the sequencing note. Tests use `Base.metadata.create_all` (all models imported) so ordering is not a test problem, only a migration-ordering note.
