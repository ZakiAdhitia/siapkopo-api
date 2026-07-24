import pytest
from sqlalchemy import select

from app.models.auth import User
from app.models.master import Resident, Village
from app.models.submission import ApprovalStepConfig
from app.seed.data import VILLAGE
from app.seed.seed import (
    seed_approval_steps, seed_link_demo_resident, seed_master, seed_positions, seed_rbac,
)


@pytest.mark.asyncio
async def test_seed_link_demo_resident_links_matching_person(db_session):
    await seed_positions(db_session)
    await seed_rbac(db_session)
    await seed_master(db_session)
    await seed_link_demo_resident(db_session)

    user = await db_session.scalar(select(User).where(User.username == "warga"))
    assert user.resident_id is not None
    resident = await db_session.scalar(select(Resident).where(Resident.id == user.resident_id))
    assert resident.full_name == "Siti Rohmah"

    # idempotent
    await seed_link_demo_resident(db_session)
    user_again = await db_session.scalar(select(User).where(User.username == "warga"))
    assert user_again.resident_id == user.resident_id


@pytest.mark.asyncio
async def test_seed_approval_steps_default_two_step_chain(db_session):
    await seed_positions(db_session)
    await seed_rbac(db_session)
    await seed_master(db_session)
    await seed_approval_steps(db_session)

    village = await db_session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    steps = list((await db_session.scalars(
        select(ApprovalStepConfig)
        .where(ApprovalStepConfig.village_id == village.id)
        .order_by(ApprovalStepConfig.order_index)
    )).all())
    assert len(steps) == 2

    from app.models.auth import Role
    role_names = []
    for step in steps:
        role = await db_session.scalar(select(Role).where(Role.id == step.role_id))
        role_names.append(role.name)
    assert role_names == ["staff", "admin"]

    # idempotent
    await seed_approval_steps(db_session)
    steps_again = list((await db_session.scalars(
        select(ApprovalStepConfig).where(ApprovalStepConfig.village_id == village.id)
    )).all())
    assert len(steps_again) == 2
