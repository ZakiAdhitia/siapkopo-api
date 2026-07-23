"""Tests for master-data seeding from mockData."""
import pytest
from sqlalchemy import func, select

from app.models.master import Dusun, Resident, Village
from app.seed.seed import seed_master


@pytest.mark.asyncio
async def test_seed_master_creates_village_and_residents(db_session):
    """First run creates the village, all dusun, and 36 residents."""
    await seed_master(db_session)

    village_count = await db_session.scalar(select(func.count()).select_from(Village))
    dusun_count = await db_session.scalar(select(func.count()).select_from(Dusun))
    resident_count = await db_session.scalar(select(func.count()).select_from(Resident))

    assert village_count == 1
    assert dusun_count == 4
    assert resident_count == 36


@pytest.mark.asyncio
async def test_seed_master_idempotent(db_session):
    """Re-running seed_master must not duplicate villages/dusun/residents."""
    await seed_master(db_session)
    await seed_master(db_session)

    village_count = await db_session.scalar(select(func.count()).select_from(Village))
    dusun_count = await db_session.scalar(select(func.count()).select_from(Dusun))
    resident_count = await db_session.scalar(select(func.count()).select_from(Resident))

    assert village_count == 1
    assert dusun_count == 4
    assert resident_count == 36
