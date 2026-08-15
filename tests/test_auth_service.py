import pytest
from sqlalchemy import select

from app.core.exceptions import UnauthorizedError
from app.models.auth import Position, Role, User
from app.permissions import registry
from app.seed.seed import seed_rbac
from app.services.auth import AuthService


@pytest.mark.asyncio
async def test_login_by_username_success(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login("staf", "staf123")
    assert pair["access_token"]
    assert pair["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_wrong_password(seeded_session):
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login("staf", "wrong")


@pytest.mark.asyncio
async def test_login_pending_approval_rejected(seeded_session):
    """A pending_approval=True account cannot log in even with the right password."""
    from app.core.security import hash_password
    from app.models.auth import User
    user = await AuthService(seeded_session).users.get_by_username("staf")
    pending = User(
        username="pendingstaff", full_name="Pending Staff",
        hashed_password=hash_password("pending123"), role_id=user.role_id,
        is_active=False, pending_approval=True,
    )
    seeded_session.add(pending)
    await seeded_session.commit()
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login("pendingstaff", "pending123")


@pytest.mark.asyncio
async def test_refresh_with_sqlite_naive_expiry_does_not_raise(seeded_session):
    """Regression test for the naive/aware datetime TypeError on refresh.

    SQLite (used here) round-trips ``DateTime(timezone=True)`` as naive, so
    this exercises the exact comparison path that used to crash.
    """
    svc = AuthService(seeded_session)
    pair = await svc.login("staf", "staf123")
    new_pair = await svc.refresh(pair["refresh_token"])
    assert new_pair["access_token"]
    assert new_pair["refresh_token"] != pair["refresh_token"]


@pytest.mark.asyncio
async def test_refresh_rejects_reused_rotated_token(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login("staf", "staf123")
    await svc.refresh(pair["refresh_token"])
    with pytest.raises(UnauthorizedError):
        await svc.refresh(pair["refresh_token"])


@pytest.mark.asyncio
async def test_permissions_for_administrator_is_wildcard(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("operator")
    assert svc.permissions_for(user) == ["*"]


@pytest.mark.asyncio
async def test_permissions_for_staf_is_concrete_codes(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("staf")
    perms = svc.permissions_for(user)
    assert "*" not in perms
    assert "master_data:read" in perms


@pytest.mark.asyncio
async def test_permissions_for_unions_role_and_position(seeded_session, monkeypatch):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("rt001")
    # Position "rt" grants nothing yet in this part of the rework, but the
    # union must still include the user's Role permissions (warga's set).
    perms = svc.permissions_for(user)
    assert "submission:create" in perms

    # Patch the code registry's Position "rt" grant and confirm the union
    # picks it up without going through the Role at all.
    monkeypatch.setitem(
        registry.POSITION_PERMISSIONS, "rt", ["test:placeholder_position_permission"]
    )
    perms_after = svc.permissions_for(user)
    assert "test:placeholder_position_permission" in perms_after
    assert "submission:create" in perms_after  # role grant still present


@pytest.mark.asyncio
async def test_seed_rbac_is_idempotent(seeded_session):
    """Re-running seed_rbac must not duplicate role rows."""
    roles_before = (await seeded_session.scalars(select(Role))).all()

    await seed_rbac(seeded_session)

    roles_after = (await seeded_session.scalars(select(Role))).all()
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


@pytest.mark.asyncio
async def test_forgot_password_known_identifier_returns_dev_code(seeded_session):
    svc = AuthService(seeded_session)
    code = await svc.forgot_password("staf")
    assert code is not None
    assert len(code) == svc.password_reset.settings.password_reset_code_length


@pytest.mark.asyncio
async def test_forgot_password_unknown_identifier_returns_none_silently(seeded_session):
    svc = AuthService(seeded_session)
    code = await svc.forgot_password("nosuchuser")
    assert code is None  # no exception raised -- must not leak existence


@pytest.mark.asyncio
async def test_reset_password_success_changes_password_and_revokes_tokens(seeded_session):
    svc = AuthService(seeded_session)
    old_pair = await svc.login("staf", "staf123")
    code = await svc.forgot_password("staf")
    await svc.reset_password("staf", code, "newpassword456")

    # Old refresh token must now be revoked.
    with pytest.raises(UnauthorizedError):
        await svc.refresh(old_pair["refresh_token"])

    # New password works.
    new_pair = await svc.login("staf", "newpassword456")
    assert new_pair["access_token"]
    # Old password no longer works.
    with pytest.raises(UnauthorizedError):
        await svc.login("staf", "staf123")


@pytest.mark.asyncio
async def test_reset_password_wrong_code_rejected(seeded_session):
    svc = AuthService(seeded_session)
    await svc.forgot_password("staf")
    with pytest.raises(UnauthorizedError):
        await svc.reset_password("staf", "000000", "newpassword456")
