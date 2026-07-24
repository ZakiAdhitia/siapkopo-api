import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.letter_number import LetterNumberService


@pytest.mark.asyncio
async def test_allocate_sequential(db_session):
    template_id = uuid.uuid4()
    svc = LetterNumberService(db_session)
    assert await svc.allocate(template_id, 2026) == 1
    assert await svc.allocate(template_id, 2026) == 2
    assert await svc.allocate(template_id, 2026) == 3
    # a different year restarts the sequence
    assert await svc.allocate(template_id, 2027) == 1


@pytest.mark.asyncio
async def test_allocate_concurrent_no_duplicates(_engine):
    """N concurrent allocations for the same (template_id, year) must return
    N distinct sequence numbers {1..N} with no duplicates and no gaps."""
    template_id = uuid.uuid4()
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    n = 10

    async def _allocate_one() -> int:
        async with maker() as session:
            return await LetterNumberService(session).allocate(template_id, 2026)

    results = await asyncio.gather(*[_allocate_one() for _ in range(n)])
    assert sorted(results) == list(range(1, n + 1))
