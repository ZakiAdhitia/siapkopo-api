"""Repositories for auth models."""
import uuid
from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import RefreshToken, TokenBlacklist, User


class UserRepository:
    """Data access for User."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_username(self, username: str) -> User | None:
        """Return the active user with the given username, or None."""
        stmt = select(User).where(User.username == username, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def get_by_email(self, email: str) -> User | None:
        """Return the active user with the given email, or None."""
        stmt = select(User).where(User.email == email, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def get_by_phone(self, phone: str) -> User | None:
        """Return the active user with the given phone number, or None."""
        stmt = select(User).where(User.phone == phone, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return the active user with the given id, or None."""
        stmt = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        return await self.session.scalar(stmt)


class RefreshTokenRepository:
    """Data access for RefreshToken."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, user_id: uuid.UUID, token_hash: str, expires_at: datetime) -> RefreshToken:
        """Create and persist a new refresh token."""
        rt = RefreshToken(user_id=user_id, token_hash=token_hash, expires_at=expires_at)
        self.session.add(rt)
        await self.session.flush()
        return rt

    async def get_active_by_hash(self, token_hash: str) -> RefreshToken | None:
        """Return the non-revoked refresh token matching the given hash, or None."""
        stmt = select(RefreshToken).where(
            RefreshToken.token_hash == token_hash, RefreshToken.revoked_at.is_(None)
        )
        return await self.session.scalar(stmt)

    async def revoke(self, token: RefreshToken) -> None:
        """Mark a refresh token as revoked."""
        token.revoked_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token belonging to a user.

        Used after a password reset, so a stolen/old session can't outlive
        a credential change.
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        tokens = (await self.session.scalars(stmt)).all()
        now = datetime.now(timezone.utc)
        for token in tokens:
            token.revoked_at = now
        await self.session.flush()


class TokenBlacklistRepository:
    """Data access for TokenBlacklist (revoked access-token jtis)."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, jti: str, expires_at: datetime) -> None:
        """Blacklist a jti until it naturally expires.

        Opportunistically prunes already-expired rows first -- there is no
        background worker to do this on a schedule, and logout is the only
        write path, so piggybacking cleanup here is sufficient at this
        app's scale.
        """
        now = datetime.now(timezone.utc)
        await self.session.execute(delete(TokenBlacklist).where(TokenBlacklist.expires_at < now))
        self.session.add(TokenBlacklist(jti=jti, expires_at=expires_at))
        await self.session.flush()

    async def exists(self, jti: str) -> bool:
        """Return True if the given jti is currently blacklisted (not yet expired)."""
        stmt = select(TokenBlacklist).where(
            TokenBlacklist.jti == jti, TokenBlacklist.expires_at > datetime.now(timezone.utc)
        )
        return await self.session.scalar(stmt) is not None
