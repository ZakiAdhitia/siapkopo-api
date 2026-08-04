"""Tests for master-data seeding from mockData."""
import pytest
from sqlalchemy import func, select

from app.models.master import RW, Resident
from app.seed.seed import seed_master


@pytest.mark.asyncio
async def test_seed_master_creates_rw_and_residents(db_session):
    """First run creates all RW and 36 residents."""
    await seed_master(db_session)

    rw_count = await db_session.scalar(select(func.count()).select_from(RW))
    resident_count = await db_session.scalar(select(func.count()).select_from(Resident))

    assert rw_count == 4
    assert resident_count == 36


@pytest.mark.asyncio
async def test_seed_master_idempotent(db_session):
    """Re-running seed_master must not duplicate RW/residents."""
    await seed_master(db_session)
    await seed_master(db_session)

    rw_count = await db_session.scalar(select(func.count()).select_from(RW))
    resident_count = await db_session.scalar(select(func.count()).select_from(Resident))

    assert rw_count == 4
    assert resident_count == 36
