"""Tests for the generic BaseRepository CRUD/pagination behavior."""
import pytest

from app.models.master import Village
from app.repositories.base import BaseRepository


@pytest.mark.asyncio
async def test_create_and_get(db_session):
    """create() persists a row and get() retrieves it by id."""
    repo = BaseRepository(db_session, Village)
    v = await repo.create(name="Desa Kopo")
    await db_session.commit()
    got = await repo.get(v.id)
    assert got.name == "Desa Kopo"


@pytest.mark.asyncio
async def test_soft_delete_hides(db_session):
    """soft_delete() sets deleted_at, and get() no longer returns the row."""
    repo = BaseRepository(db_session, Village)
    v = await repo.create(name="X")
    await db_session.commit()
    await repo.soft_delete(v)
    await db_session.commit()
    assert await repo.get(v.id) is None
