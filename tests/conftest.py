import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.session import get_db
from app.dependencies.rate_limit import _reset_counters
from app.main import create_app
from app.seed.seed import seed_positions, seed_rbac

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    """Rate limiting is in-process, module-level state (no Redis) -- clear
    it between tests so one test's requests don't count against another's
    limit (the test client has no real client IP, so every test would
    otherwise share the same counter key)."""
    _reset_counters()
    yield


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
