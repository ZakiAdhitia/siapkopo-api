"""Authentication & RBAC models."""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String, Table
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin

role_permissions = Table(
    "role_permissions",
    Base.metadata,
    Column("role_id", GUID(), ForeignKey("roles.id"), primary_key=True),
    Column("permission_id", GUID(), ForeignKey("permissions.id"), primary_key=True),
)


class Permission(UUIDMixin, TimestampMixin, Base):
    """A single grantable permission code (e.g. ``resident:read``)."""

    __tablename__ = "permissions"
    code: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)


class Role(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A named role granting a set of permissions to users."""

    __tablename__ = "roles"
    name: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    permissions: Mapped[list[Permission]] = relationship(
        secondary=role_permissions, lazy="selectin"
    )


class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An authenticated principal: staff (username/password) or citizen (NIK/OTP)."""

    __tablename__ = "users"
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    nik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("residents.id"), nullable=True
    )
    role: Mapped[Role] = relationship(lazy="selectin")


class RefreshToken(UUIDMixin, TimestampMixin, Base):
    """An issued refresh token, tracked so it can be revoked/rotated."""

    __tablename__ = "refresh_tokens"
    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(255), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
