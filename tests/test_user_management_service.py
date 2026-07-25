"""Tests for UserManagementService: position-hierarchy enforcement + CRUD.

House style mirrors tests/test_auth_service.py: fetch seeded demo users by
username, build `actor_permissions` via AuthService(session).permissions_for,
call the service directly (no HTTP layer -- that's Task 2's job).
"""
import uuid

import pytest
from sqlalchemy import select

from app.core.exceptions import (
    ConflictError, ForbiddenError, NotFoundError, ValidationAppError,
)
from app.core.security import hash_password
from app.models.auth import Position, User
from app.services.auth import AuthService
from app.services.user_management import UserManagementService


async def _actor(session, username: str) -> tuple[User, list[str]]:
    """Fetch a seeded demo user by username and resolve its effective permissions."""
    user = await session.scalar(select(User).where(User.username == username))
    perms = AuthService(session).permissions_for(user)
    return user, perms


async def _position(session, slug: str) -> Position:
    return await session.scalar(select(Position).where(Position.slug == slug))


async def _plain_user(session, username: str) -> User:
    """Fetch a seeded demo user without also resolving permissions."""
    return await session.scalar(select(User).where(User.username == username))


@pytest.mark.asyncio
async def test_create_kades_can_create_bendahara(seeded_session):
    """1. kades (level 1) creates a user at bendahara_desa (level 3) -> succeeds."""
    actor, perms = await _actor(seeded_session, "kades")
    bendahara_position = await _position(seeded_session, "bendahara_desa")
    svc = UserManagementService(seeded_session)
    user = await svc.create(actor, perms, {
        "full_name": "Bendahara Baru", "username": "bendaharabaru",
        "password": "password123", "email": "bendaharabaru@example.test",
        "position_id": bendahara_position.id,
    })
    assert user.role.name == "staff"
    assert user.is_active is True
    assert user.pending_approval is False


@pytest.mark.asyncio
async def test_create_sekdes_cannot_create_kepala_desa(seeded_session):
    """2. sekdes (level 2) attempts to create a user at kepala_desa (level 1,
    numerically higher authority) -> ForbiddenError."""
    actor, perms = await _actor(seeded_session, "sekdes")
    kades_position = await _position(seeded_session, "kepala_desa")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ForbiddenError):
        await svc.create(actor, perms, {
            "full_name": "Kades Baru", "username": "kadesbaru",
            "password": "password123", "email": "kadesbaru@example.test",
            "position_id": kades_position.id,
        })


@pytest.mark.asyncio
async def test_create_username_conflict(seeded_session):
    """3a. Duplicate username -> ConflictError."""
    actor, perms = await _actor(seeded_session, "kades")
    bendahara_position = await _position(seeded_session, "bendahara_desa")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ConflictError):
        await svc.create(actor, perms, {
            "full_name": "Duplikat Username", "username": "sekdes",  # already a demo account
            "password": "password123", "email": "unik@example.test",
            "position_id": bendahara_position.id,
        })


@pytest.mark.asyncio
async def test_create_email_conflict(seeded_session):
    """3b. Duplicate email -> ConflictError."""
    actor, perms = await _actor(seeded_session, "kades")
    bendahara_position = await _position(seeded_session, "bendahara_desa")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ConflictError):
        await svc.create(actor, perms, {
            "full_name": "Duplikat Email", "username": "uniqueusername",
            "password": "password123", "email": "dewi.lestari@example.test",  # sekdes's email
            "position_id": bendahara_position.id,
        })


@pytest.mark.asyncio
async def test_create_rt_position_missing_rt_id(seeded_session):
    """4a. position_id = rt's position but no rt_id in data -> ValidationAppError."""
    actor, perms = await _actor(seeded_session, "kades")
    rt_position = await _position(seeded_session, "rt")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(actor, perms, {
            "full_name": "RT Baru", "username": "rtbaru",
            "password": "password123", "email": "rtbaru@example.test",
            "position_id": rt_position.id,
        })


@pytest.mark.asyncio
async def test_create_rt_position_nonexistent_rt_id(seeded_session):
    """4b. position_id = rt's position with a non-existent rt_id -> ValidationAppError."""
    actor, perms = await _actor(seeded_session, "kades")
    rt_position = await _position(seeded_session, "rt")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(actor, perms, {
            "full_name": "RT Baru", "username": "rtbaru2",
            "password": "password123", "email": "rtbaru2@example.test",
            "position_id": rt_position.id, "rt_id": uuid.uuid4(),
        })


@pytest.mark.asyncio
async def test_update_kades_can_update_sekdes(seeded_session):
    """5. kades (level 1) updates sekdes (level 2) -> succeeds."""
    actor, perms = await _actor(seeded_session, "kades")
    target, _ = await _actor(seeded_session, "sekdes")
    svc = UserManagementService(seeded_session)
    updated = await svc.update(actor, perms, target.id, {"full_name": "Dewi Lestari Baru"})
    assert updated.full_name == "Dewi Lestari Baru"


@pytest.mark.asyncio
async def test_update_sekdes_cannot_update_kades(seeded_session):
    """6. sekdes (level 2) attempts to update kades (level 1) -> ForbiddenError.

    Key spec assertion: hierarchy is purely position-level, independent of
    Role -- both kades and sekdes share the "admin" Role, but the hierarchy
    is NOT symmetric.
    """
    actor, perms = await _actor(seeded_session, "sekdes")
    target, _ = await _actor(seeded_session, "kades")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ForbiddenError):
        await svc.update(actor, perms, target.id, {"full_name": "Wiwin Wildan Baru"})


@pytest.mark.asyncio
async def test_update_kades_cannot_promote_target_to_kades_level_or_higher(seeded_session):
    """7. kades attempts to change a target's position_id to level <= kades's
    own level (e.g. promote to kepala_desa or sekretaris_desa) -> ForbiddenError."""
    actor, perms = await _actor(seeded_session, "kades")
    target, _ = await _actor(seeded_session, "bendahara")
    kades_position = await _position(seeded_session, "kepala_desa")
    svc = UserManagementService(seeded_session)
    with pytest.raises(ForbiddenError):
        await svc.update(actor, perms, target.id, {"position_id": kades_position.id})


@pytest.mark.asyncio
async def test_delete_soft_deletes(seeded_session):
    """8. delete() soft-deletes: deleted_at set, get_or_404 then raises NotFoundError."""
    actor, perms = await _actor(seeded_session, "kades")
    target, _ = await _actor(seeded_session, "bendahara")
    svc = UserManagementService(seeded_session)
    await svc.delete(actor, perms, target.id)
    assert target.deleted_at is not None
    with pytest.raises(NotFoundError):
        await svc.get_or_404(target.id)


@pytest.mark.asyncio
async def test_list_excludes_warga_by_default_includes_when_flagged(seeded_session):
    """9. list(include_warga=False) excludes warga_desa-position users;
    include_warga=True includes them."""
    svc = UserManagementService(seeded_session)
    rows_excluded, _ = await svc.list(1, 50, None, None, False)
    assert not any(u.position and u.position.slug == "warga_desa" for u in rows_excluded)

    rows_included, _ = await svc.list(1, 50, None, None, True)
    assert any(u.position and u.position.slug == "warga_desa" for u in rows_included)


@pytest.mark.asyncio
async def test_list_search_matches_kades(seeded_session):
    """10. list(search="kades") returns the kades demo user, case-insensitive."""
    svc = UserManagementService(seeded_session)
    rows, total = await svc.list(1, 50, None, "kades", True)
    assert total >= 1
    assert any(u.username == "kades" for u in rows)


@pytest.mark.asyncio
async def test_approve_activates_pending_user(seeded_session):
    """11. approve() on a pending_approval=True user -> is_active=True, pending_approval=False."""
    actor, perms = await _actor(seeded_session, "kades")
    staf = await _plain_user(seeded_session, "staf")
    pending = User(
        username="pendingapproveme", full_name="Pending Approve Me",
        hashed_password=hash_password("password123"), email="pendingapprove@example.test",
        role_id=staf.role_id, position_id=staf.position_id,
        is_active=False, pending_approval=True,
    )
    seeded_session.add(pending)
    await seeded_session.commit()

    svc = UserManagementService(seeded_session)
    approved = await svc.approve(actor, perms, pending.id)
    assert approved.is_active is True
    assert approved.pending_approval is False


@pytest.mark.asyncio
async def test_approve_reject_non_pending_user_raises_validation_error(seeded_session):
    """12. approve()/reject() on a user whose pending_approval is already False ->
    ValidationAppError."""
    actor, perms = await _actor(seeded_session, "kades")
    target, _ = await _actor(seeded_session, "bendahara")  # not pending
    svc = UserManagementService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.approve(actor, perms, target.id)
    with pytest.raises(ValidationAppError):
        await svc.reject(actor, perms, target.id)


@pytest.mark.asyncio
async def test_administrator_it_bypasses_hierarchy_for_all_operations(seeded_session):
    """13. administrator-it (operator, position=None, permission "*") can
    create/update/delete/approve a user at ANY position level, including
    kepala_desa -- the unrestricted-actor bypass works even though
    operator.position is None."""
    actor, perms = await _actor(seeded_session, "operator")
    assert actor.position is None
    assert perms == ["*"]
    kades_position = await _position(seeded_session, "kepala_desa")
    svc = UserManagementService(seeded_session)

    # create at the highest-authority position
    created = await svc.create(actor, perms, {
        "full_name": "Kades Kedua", "username": "kadeskedua",
        "password": "password123", "email": "kadeskedua@example.test",
        "position_id": kades_position.id,
    })
    assert created.role.name == "admin"
    assert created.position.slug == "kepala_desa"

    # update it
    updated = await svc.update(actor, perms, created.id, {"full_name": "Kades Kedua Baru"})
    assert updated.full_name == "Kades Kedua Baru"

    # approve a pending user at kepala_desa level
    pending = User(
        username="pendingkades", full_name="Pending Kades",
        hashed_password=hash_password("password123"), email="pendingkades@example.test",
        role_id=created.role_id, position_id=kades_position.id,
        is_active=False, pending_approval=True,
    )
    seeded_session.add(pending)
    await seeded_session.commit()
    approved = await svc.approve(actor, perms, pending.id)
    assert approved.is_active is True
    assert approved.pending_approval is False

    # delete it
    await svc.delete(actor, perms, created.id)
    assert created.deleted_at is not None
