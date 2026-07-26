"""Authentication service: login, refresh, logout, RBAC resolution."""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ConflictError, UnauthorizedError, ValidationAppError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.core.security import (
    create_access_token, create_refresh_token_value, hash_password, hash_token,
    verify_password,
)
from app.models.auth import Position, Role, User
from app.models.master import RT, RW, Resident
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

    _POSITION_CHOICE_MAP: dict[str, tuple[str, str]] = {
        "rt": ("warga", "rt"),
        "rw": ("warga", "rw"),
        "staff": ("staff", "staff_desa"),
    }

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)
        self.refresh_tokens = RefreshTokenRepository(session)
        self.redis = get_redis()
        self.settings = get_settings()
        self.password_reset = PasswordResetService()

    def permissions_for(self, user: User) -> list[str]:
        """Resolve effective permission codes for a user: Role ∪ Position.

        Purely data-driven from the database: whatever permission rows are
        assigned to the user's role (including a literal ``"*"`` row for
        wildcard roles) and, if set, the user's position, are unioned and
        returned. Order is not significant; duplicates are removed.
        """
        codes = {p.code for p in user.role.permissions}
        if user.position is not None:
            codes.update(p.code for p in user.position.permissions)
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
        """Authenticate by username OR NIK, both matched against `password`."""
        clean = identifier.strip()
        user = await self.users.get_by_username(clean.lower())
        if user is None:
            user = await self.users.get_by_nik(clean)
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

    async def register(self, data: dict) -> tuple[User, bool]:
        """Self-register a new account. Returns (user, is_immediately_active).

        rt/rw require a nik matching an existing Resident (identity check
        against master data); staff's nik is optional and unchecked. Every
        remaining position_choice (staff/rt/rw) is created pending approval
        (is_active=False) -- plain "warga" registration doesn't exist
        anymore (Bagian 6, STRATEGI doc rev. 2026-07-26), so there is no
        immediately-active self-registration path left.
        """
        position_choice = data["position_choice"]
        role_name, position_slug = self._POSITION_CHOICE_MAP[position_choice]

        if await self.users.get_by_username(data["username"].strip().lower()):
            raise ConflictError("Username sudah digunakan")
        existing_email = await self.session.scalar(
            select(User).where(User.email == data["email"], User.deleted_at.is_(None))
        )
        if existing_email:
            raise ConflictError("Email sudah digunakan")

        resident_id = None
        nik = data.get("nik")
        if position_choice in ("rt", "rw"):
            if not nik:
                raise ValidationAppError("NIK wajib diisi untuk pendaftaran ini")
            resident = await self.session.scalar(
                select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
            )
            if resident is None:
                raise ValidationAppError(
                    "NIK tidak ditemukan pada data kependudukan, silakan hubungi kantor desa"
                )
            already_linked = await self.session.scalar(
                select(User).where(User.resident_id == resident.id, User.deleted_at.is_(None))
            )
            if already_linked:
                raise ConflictError("NIK ini sudah terdaftar")
            resident_id = resident.id
            full_name = resident.full_name
        else:
            full_name = data["full_name"]

        rt_id, rw_id = None, None
        if position_choice == "rt":
            if not data.get("rt_id"):
                raise ValidationAppError("rt_id wajib diisi untuk pendaftaran posisi RT")
            rt = await self.session.get(RT, data["rt_id"])
            if rt is None:
                raise ValidationAppError("RT tidak ditemukan")
            rt_id = rt.id
        elif position_choice == "rw":
            if not data.get("rw_id"):
                raise ValidationAppError("rw_id wajib diisi untuk pendaftaran posisi RW")
            rw = await self.session.get(RW, data["rw_id"])
            if rw is None:
                raise ValidationAppError("RW tidak ditemukan")
            rw_id = rw.id

        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        position = await self.session.scalar(select(Position).where(Position.slug == position_slug))

        is_active = False
        user = User(
            username=data["username"].strip().lower(), nik=nik, full_name=full_name,
            hashed_password=hash_password(data["password"]), email=data["email"],
            role_id=role.id, position_id=position.id, resident_id=resident_id,
            rt_id=rt_id, rw_id=rw_id, is_active=is_active, pending_approval=not is_active,
        )
        # Populate the relationship attributes directly from the objects we
        # already fetched above (not just their FK ids). A freshly
        # constructed instance -- unlike one returned by a `select()` -- has
        # no relationships eagerly loaded, so leaving this to `user.role`'s
        # `lazy="selectin"` strategy would force an implicit lazy load the
        # first time a caller touches `.role`/`.position` outside of an
        # awaited call, which needs SQLAlchemy's async/greenlet IO bridge
        # and is not guaranteed to be available at that point (e.g. a
        # synchronous attribute access in calling code). Assigning here
        # costs nothing extra (both were already queried) and guarantees
        # `.role`/`.position` are immediately usable on the returned user.
        user.role = role
        user.position = position
        self.session.add(user)
        await self.session.commit()
        logger.info(
            "User registered id=%s username=%s position=%s active=%s",
            user.id, user.username, position_slug, is_active,
        )
        return user, is_active

    async def _resolve_by_identifier(self, identifier: str) -> User | None:
        clean = identifier.strip()
        user = await self.users.get_by_username(clean.lower())
        if user is None:
            user = await self.users.get_by_nik(clean)
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
