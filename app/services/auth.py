"""Authentication service: login, refresh, logout, RBAC resolution."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError, ValidationAppError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import (
    create_access_token, create_refresh_token_value, hash_password, hash_token,
    verify_password,
)
from app.models.auth import User
from app.permissions.registry import POSITION_PERMISSIONS, ROLE_PERMISSIONS
from app.repositories.auth import RefreshTokenRepository, UserRepository
from app.services.password_reset import PasswordResetService

logger = get_logger("auth")


def _as_aware_utc(value: datetime) -> datetime:
    """Normalize a possibly-naive datetime to timezone-aware UTC.

    SQLite (used in tests) returns naive datetimes for ``DateTime(timezone=True)``
    columns; PostgreSQL returns aware ones. Comparing naive vs aware raises
    ``TypeError``, so every expiry comparison must go through this first.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AuthService:
    """Business logic for authentication and token lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.redis = get_redis()
        self.settings = get_settings()
        self.password_reset = PasswordResetService()

    def permissions_for(self, user: User) -> list[str]:
        """Resolve effective permission codes for a user: Role ∪ Position.

        Purely code-driven from ``app.permissions.registry`` (no permission
        data stored in the database): the user's role name and, if set,
        their position slug are looked up in ``ROLE_PERMISSIONS``/
        ``POSITION_PERMISSIONS`` and unioned. Order is not significant;
        duplicates are removed.
        """
        codes = set(ROLE_PERMISSIONS.get(user.role.name, []))
        if user.position is not None:
            codes.update(POSITION_PERMISSIONS.get(user.position.slug, []))
        return list(codes)

    async def _issue(self, user: User) -> dict:
        """Issue a fresh access/refresh token pair for an authenticated user."""
        jti = str(uuid.uuid4())
        access = create_access_token(
            str(user.id), user.role.name, self.permissions_for(user), jti
        )
        raw_refresh, token_hash = create_refresh_token_value()
        expires = datetime.now(timezone.utc) + timedelta(days=self.settings.refresh_token_expire_days)
        await self.refresh_tokens.create(user.id, token_hash, expires)
        await self.session.commit()
        return {
            "access_token": access, "refresh_token": raw_refresh,
            "token_type": "bearer",
            "expires_in": self.settings.access_token_expire_minutes * 60,
        }

    async def login(self, identifier: str, password: str) -> dict:
        """Authenticate by username, NIK, email, or phone, all matched against `password`."""
        clean = identifier.strip()
        user = await self._resolve_by_identifier(clean)
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            logger.warning("Login gagal untuk identifier=%s", clean)
            raise UnauthorizedError("Identitas atau kata sandi salah")
        if not user.is_active:
            if user.pending_approval:
                logger.warning("Login ditolak (menunggu approval) untuk identifier=%s", clean)
                raise UnauthorizedError("Akun Anda masih menunggu persetujuan")
            logger.warning("Login ditolak (akun tidak aktif) untuk identifier=%s", clean)
            raise UnauthorizedError("Akun tidak aktif")
        result = await self._issue(user)
        logger.info("Login sukses user_id=%s role=%s", user.id, user.role.name)
        return result

    async def refresh(self, raw_refresh: str) -> dict:
        """Rotate a refresh token and issue a new pair."""
        token = await self.refresh_tokens.get_active_by_hash(hash_token(raw_refresh))
        if not token or _as_aware_utc(token.expires_at) < datetime.now(timezone.utc):
            raise UnauthorizedError("Refresh token tidak valid")
        await self.refresh_tokens.revoke(token)
        user = await self.users.get_by_id(token.user_id)
        if not user:
            raise UnauthorizedError("User tidak ditemukan")
        return await self._issue(user)

    async def logout(self, access_payload: dict, raw_refresh: str | None) -> None:
        """Blacklist the access jti and revoke the refresh token."""
        jti = access_payload.get("jti")
        exp = access_payload.get("exp")
        if jti and exp:
            ttl = max(int(exp - datetime.now(timezone.utc).timestamp()), 1)
            await self.redis.set(f"bl:{jti}", "1", ex=ttl)
        if raw_refresh:
            token = await self.refresh_tokens.get_active_by_hash(hash_token(raw_refresh))
            if token:
                await self.refresh_tokens.revoke(token)
                await self.session.commit()
        logger.info("Logout jti=%s", jti)

    async def is_blacklisted(self, jti: str) -> bool:
        """Return True if an access jti has been blacklisted."""
        return bool(await self.redis.get(f"bl:{jti}"))

    async def _resolve_by_identifier(self, identifier: str) -> User | None:
        """Match a login/forgot-password identifier against username, NIK,
        email, or phone -- in that order, first match wins (2026-08-04:
        widened from username/NIK-only)."""
        clean = identifier.strip()
        user = await self.users.get_by_username(clean.lower())
        if user is None:
            user = await self.users.get_by_nik(clean)
        if user is None and "@" in clean:
            user = await self.users.get_by_email(clean.lower())
        if user is None:
            user = await self.users.get_by_phone(clean)
        return user

    async def forgot_password(self, identifier: str) -> str | None:
        """Generate a reset code for the matching account, if any.

        Returns the raw code only for dev-mode convenience (None in
        production or if no account matched) -- the caller must not use a
        non-None/None distinction to reveal whether an account exists;
        both cases return the same API response shape.
        """
        user = await self._resolve_by_identifier(identifier)
        if user is None:
            return None
        code = await self.password_reset.request_reset(user)
        return code if self.settings.app_env != "production" else None

    async def reset_password(self, identifier: str, code: str, new_password: str) -> None:
        """Verify a reset code and set a new password, revoking all sessions."""
        user = await self._resolve_by_identifier(identifier)
        if user is None or not await self.password_reset.verify_and_consume(user.id, code):
            raise UnauthorizedError("Kode reset tidak valid atau kedaluwarsa")
        user.hashed_password = hash_password(new_password)
        await self.refresh_tokens.revoke_all_for_user(user.id)
        await self.session.commit()
        logger.info("Password reset sukses user_id=%s", user.id)

    async def change_password(self, user_id: uuid.UUID, old_password: str, new_password: str) -> None:
        """Self-service password change from the Profile page
        (HASIL_UJICOBA_DILUAR_ROLE.md poin 3) -- unlike `reset_password`
        (unauthenticated, code-based), this is for an already-logged-in
        user who knows their current password. Every other session is
        revoked afterward, same as a reset, since the old password may
        have been compromised."""
        user = await self.users.get_by_id(user_id)
        if user is None or not user.hashed_password or not verify_password(old_password, user.hashed_password):
            raise UnauthorizedError("Kata sandi lama salah")
        user.hashed_password = hash_password(new_password)
        await self.refresh_tokens.revoke_all_for_user(user.id)
        await self.session.commit()
        logger.info("Password diubah sendiri oleh user_id=%s", user.id)
