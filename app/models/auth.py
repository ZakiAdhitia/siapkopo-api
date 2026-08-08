"""Authentication & RBAC models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Role(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A named role. Effective permissions are resolved purely from
    ``app.permissions.registry.ROLE_PERMISSIONS`` by role name -- no
    permission data is stored in the database (see ``AuthService.permissions_for``)."""

    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Position(UUIDMixin, TimestampMixin, Base):
    """A jabatan (position): hierarchy level + optional extra permissions.

    Separate dimension from Role -- a user's effective permissions are the
    union of their Role's and their Position's permission codes, both
    resolved from ``app.permissions.registry`` by name/slug (see
    ``AuthService.permissions_for``). Fixed reference data, seeded; no CRUD
    API by design (see the rework spec).
    """

    __tablename__ = "positions"
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    level: Mapped[int] = mapped_column()


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An authenticated principal: staff (username/password) or citizen (NIK/OTP)."""

    __tablename__ = "users"
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    nik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("positions.id"), nullable=True
    )
    pending_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[Role] = relationship(lazy="selectin")
    position: Mapped[Position | None] = relationship(lazy="selectin")


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    """An issued refresh token, tracked so it can be revoked/rotated."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class TokenBlacklist(UUIDMixin, TimestampMixin, Base):
    """A revoked access-token jti, kept until its natural expiry.

    Populated on logout (``AuthService.logout``) so a stolen/leaked access
    token can't be reused before its own ``exp`` claim -- JWTs are otherwise
    stateless and can't be individually revoked. Replaces the old Redis
    ``bl:{jti}`` key with TTL; ``TokenBlacklistRepository.add`` opportunistically
    prunes already-expired rows on write since there is no background worker.
    """

    __tablename__ = "token_blacklist"
    jti: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PasswordResetCode(UUIDMixin, TimestampMixin, Base):
    """A single-use, short-lived password-reset code for one user.

    At most one active row per user -- ``PasswordResetService.request_reset``
    replaces any existing row for that user. Replaces the old Redis
    ``pwreset:{user_id}`` key with TTL.
    """

    __tablename__ = "password_reset_codes"
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id"), unique=True, index=True
    )
    code: Mapped[str] = mapped_column(String(10))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
