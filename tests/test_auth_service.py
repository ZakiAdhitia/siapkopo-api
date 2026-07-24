import pytest
from sqlalchemy import select

from app.core.exceptions import UnauthorizedError
from app.models.auth import Permission, Position, Role, User
from app.seed.seed import seed_rbac
from app.services.auth import AuthService


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


@pytest.mark.asyncio
async def test_refresh_with_sqlite_naive_expiry_does_not_raise(seeded_session):
    """Regression test for the naive/aware datetime TypeError on refresh.

    SQLite (used here) round-trips ``DateTime(timezone=True)`` as naive, so
    this exercises the exact comparison path that used to crash.
    """
    svc = AuthService(seeded_session)
    pair = await svc.login_password("staf", "staf123")
    new_pair = await svc.refresh(pair["refresh_token"])
    assert new_pair["access_token"]
    assert new_pair["refresh_token"] != pair["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rejects_reused_rotated_token(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login_password("staf", "staf123")
    await svc.refresh(pair["refresh_token"])
    with pytest.raises(UnauthorizedError):
        await svc.refresh(pair["refresh_token"])


@pytest.mark.asyncio
async def test_permissions_for_administrator_is_wildcard_from_db(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("operator")
    codes = [p.code for p in user.role.permissions]
    assert codes == ["*"]
    assert svc.permissions_for(user) == ["*"]


@pytest.mark.asyncio
async def test_permissions_for_staf_is_concrete_codes(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("staf")
    perms = svc.permissions_for(user)
    assert "*" not in perms
    assert "resident:read" in perms


@pytest.mark.asyncio
async def test_permissions_for_unions_role_and_position(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("rt001")
    # Position "rt" grants nothing yet in this part of the rework, but the
    # union must still include the user's Role permissions (warga's set).
    perms = svc.permissions_for(user)
    assert "submission:create" in perms

    # Directly attach an extra permission to Position "rt" and confirm the
    # union picks it up without going through the Role at all.
    position = await seeded_session.scalar(
        select(Position).where(Position.slug == "rt")
    )
    extra = Permission(code="lapduk:manage_own")
    seeded_session.add(extra)
    await seeded_session.flush()
    position.permissions.append(extra)
    await seeded_session.commit()
    await seeded_session.refresh(user)
    perms_after = svc.permissions_for(user)
    assert "lapduk:manage_own" in perms_after
    assert "submission:create" in perms_after  # role grant still present


@pytest.mark.asyncio
async def test_seed_rbac_is_idempotent(seeded_session):
    """Re-running seed_rbac must not duplicate permission or role rows."""
    perms_before = (await seeded_session.scalars(select(Permission))).all()
    roles_before = (await seeded_session.scalars(select(Role))).all()

    await seed_rbac(seeded_session)

    perms_after = (await seeded_session.scalars(select(Permission))).all()
    roles_after = (await seeded_session.scalars(select(Role))).all()
    assert len(perms_after) == len(perms_before)
    assert len(roles_after) == len(roles_before)


@pytest.mark.asyncio
async def test_seed_rbac_corrects_stale_role_on_reseed(seeded_session):
    """Regression test for the update-on-reseed fix in seed_rbac.

    Simulates a demo username that pre-existed this Role+Position rework
    and was therefore left with a stale role_id/position_id (the old
    seed_rbac skipped updating any username already present). Re-running
    seed_rbac must now correct the user's role_id/position_id back to
    whatever DEMO_ACCOUNTS specifies, not leave the stale values in place.
    """
    user = await seeded_session.scalar(select(User).where(User.username == "staf"))
    correct_role_id = user.role_id
    correct_position_id = user.position_id

    # Force the user onto a different role/position than DEMO_ACCOUNTS
    # specifies for "staf", to simulate the pre-rework stale state.
    stale_role = await seeded_session.scalar(select(Role).where(Role.name == "admin"))
    stale_position = await seeded_session.scalar(
        select(Position).where(Position.slug == "kepala_desa")
    )
    assert stale_role.id != correct_role_id
    assert stale_position.id != correct_position_id
    user.role_id = stale_role.id
    user.position_id = stale_position.id
    await seeded_session.commit()

    await seed_rbac(seeded_session)

    await seeded_session.refresh(user)
    assert user.role_id == correct_role_id
    assert user.position_id == correct_position_id
