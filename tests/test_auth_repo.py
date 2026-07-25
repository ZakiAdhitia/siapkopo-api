from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.auth import RefreshToken, Role, User
from app.repositories.auth import RefreshTokenRepository, UserRepository


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
