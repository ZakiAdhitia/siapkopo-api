import fakeredis
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import app.core.redis as redis_module
from app.db.base import Base
from app.db.session import get_db
from app.main import create_app
from app.seed.seed import seed_positions, seed_rbac

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest_asyncio.fixture(autouse=True)
async def _fake_redis():
    """Replace the module-singleton Redis client with an in-memory fake.

    Redis is not running in this environment; forgot-password/reset-password
    codes and the logout blacklist go through ``app.core.redis.get_redis()``,
    so swapping the singleton here makes those flows exercisable without a
    real server.
    """
    redis_module._client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    yield
    redis_module._client = None


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
    await seed_positions(db_session)
    await seed_rbac(db_session)
    return db_session


@pytest_asyncio.fixture
async def client(_engine):
    """An async HTTP client wired to the in-memory test DB, pre-seeded with RBAC."""
    app = create_app()
    maker = async_sessionmaker(_engine, expire_on_commit=False)

    async def _override_get_db():
        async with maker() as s:
            yield s

    app.dependency_overrides[get_db] = _override_get_db
    # seed once for endpoint tests
    async with maker() as s:
        await seed_positions(s)
        await seed_rbac(s)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
