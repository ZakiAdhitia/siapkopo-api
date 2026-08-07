"""Tests for master-data (RW/RT hierarchy) seeding."""
import pytest
from sqlalchemy import func, select

from app.models.master import RT, RW
from app.seed.seed import seed_master


@pytest.mark.asyncio
async def test_seed_master_creates_rw_and_rt(db_session):
    """First run creates all RW and RT (4 RW x 4 RT each -- 2026-08-06: no
    more Resident population registry, see app/models/master.py's module
    docstring; RW/RT are seeded directly from RW_RT_PAIRS now)."""
    await seed_master(db_session)

    rw_count = await db_session.scalar(select(func.count()).select_from(RW))
    rt_count = await db_session.scalar(select(func.count()).select_from(RT))

    assert rw_count == 4
    assert rt_count == 16


@pytest.mark.asyncio
async def test_seed_master_idempotent(db_session):
    """Re-running seed_master must not duplicate RW/RT."""
    await seed_master(db_session)
    await seed_master(db_session)

    rw_count = await db_session.scalar(select(func.count()).select_from(RW))
    rt_count = await db_session.scalar(select(func.count()).select_from(RT))

    assert rw_count == 4
    assert rt_count == 16
