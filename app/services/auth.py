"""Authentication service: login, refresh, logout, RBAC resolution."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError
from app.core.redis import get_redis
from app.core.security import (
    create_access_token, create_refresh_token_value, hash_token, verify_password,
)
from app.models.auth import User
from app.permissions.registry import ROLE_PERMISSIONS
from app.repositories.auth import RefreshTokenRepository, UserRepository
from app.services.otp import OtpService


class AuthService:
    """Business logic for authentication and token lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.otp = OtpService()
        self.redis = get_redis()
        self.settings = get_settings()

    def permissions_for(self, user: User) -> list[str]:
        """Resolve effective permission codes for a user from its role.

        Roles registered in the RBAC registry with the wildcard sentinel
        (``["*"]``) collapse to a single ``"*"`` entry so the JWT/permission
        check can grant everything without enumerating every code; all other
        roles report the concrete codes actually granted in the database.
        """
        if ROLE_PERMISSIONS.get(user.role.name) == ["*"]:
            return ["*"]
        return [p.code for p in user.role.permissions]

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

    async def login_password(self, username: str, password: str) -> dict:
        """Authenticate a staff user by username + password."""
        user = await self.users.get_by_username(username.strip().lower())
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            raise UnauthorizedError("Username atau kata sandi salah")
        if not user.is_active:
            raise UnauthorizedError("Akun tidak aktif")
        return await self._issue(user)

    async def login_otp(self, nik: str, code: str) -> dict:
        """Authenticate a warga by NIK + OTP."""
        if not await self.otp.verify_otp(nik, code):
            raise UnauthorizedError("Kode OTP salah atau kedaluwarsa")
        user = await self.users.get_by_nik(nik)
        if not user or not user.is_active:
            raise UnauthorizedError("Warga tidak terdaftar")
        return await self._issue(user)

    async def refresh(self, raw_refresh: str) -> dict:
        """Rotate a refresh token and issue a new pair."""
        token = await self.refresh_tokens.get_active_by_hash(hash_token(raw_refresh))
        if not token or token.expires_at < datetime.now(timezone.utc):
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

    async def is_blacklisted(self, jti: str) -> bool:
        """Return True if an access jti has been blacklisted."""
        return bool(await self.redis.get(f"bl:{jti}"))
