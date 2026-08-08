from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.core.security import hash_password
from app.models.auth import RefreshToken, Role, TokenBlacklist, User
from app.repositories.auth import RefreshTokenRepository, TokenBlacklistRepository, UserRepository


@pytest.mark.asyncio
async def test_get_by_username_none(db_session):
    repo = UserRepository(db_session)
    assert await repo.get_by_username("nobody") is None


@pytest.mark.asyncio
async def test_revoke_all_for_user_revokes_every_active_token(seeded_session):
    """A password reset revokes every active session, not just one token."""
    role = await seeded_session.scalar(select(Role).where(Role.name == "warga"))
    user = User(
        username="tokenowner", full_name="Token Owner",
        hashed_password=hash_password("password123"), is_active=True, role_id=role.id,
    )
    seeded_session.add(user)
    await seeded_session.flush()

    repo = RefreshTokenRepository(seeded_session)
    expires_at = datetime.now(timezone.utc) + timedelta(days=1)
    token_a = await repo.create(user.id, "hash-a", expires_at)
    token_b = await repo.create(user.id, "hash-b", expires_at)
    await seeded_session.commit()
    assert token_a.revoked_at is None
    assert token_b.revoked_at is None

    await repo.revoke_all_for_user(user.id)
    await seeded_session.commit()

    assert await repo.get_active_by_hash("hash-a") is None
    assert await repo.get_active_by_hash("hash-b") is None

    # The rows still exist -- revoked, not deleted.
    revoked = (await seeded_session.scalars(
        select(RefreshToken).where(RefreshToken.user_id == user.id)
    )).all()
    assert len(revoked) == 2
    assert all(t.revoked_at is not None for t in revoked)


@pytest.mark.asyncio
async def test_blacklist_exists_false_for_unknown_jti(db_session):
    repo = TokenBlacklistRepository(db_session)
    assert await repo.exists("no-such-jti") is False


@pytest.mark.asyncio
async def test_blacklist_add_then_exists(db_session):
    repo = TokenBlacklistRepository(db_session)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=30)
    await repo.add("jti-1", expires_at)
    assert await repo.exists("jti-1") is True


@pytest.mark.asyncio
async def test_blacklist_exists_false_once_naturally_expired(db_session):
    """A jti past its own expires_at is treated as not-blacklisted --
    matches the old Redis key's TTL auto-expiry."""
    repo = TokenBlacklistRepository(db_session)
    already_expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    await repo.add("jti-expired", already_expired)
    assert await repo.exists("jti-expired") is False


@pytest.mark.asyncio
async def test_blacklist_add_prunes_expired_rows(db_session):
    """No background worker prunes this table -- add() opportunistically
    deletes already-expired rows itself."""
    repo = TokenBlacklistRepository(db_session)
    already_expired = datetime.now(timezone.utc) - timedelta(seconds=1)
    await repo.add("jti-old", already_expired)
    await db_session.commit()

    still_valid = datetime.now(timezone.utc) + timedelta(minutes=30)
    await repo.add("jti-new", still_valid)

    count = await db_session.scalar(select(func.count()).select_from(TokenBlacklist))
    assert count == 1
