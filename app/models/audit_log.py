"""Append-only audit trail (CLAUDE.md "Logging": login/logout/approval/
reject/generate-pdf/delete/export must be recorded).

Deliberately minimal (no soft delete -- an audit log must never appear to
lose entries) and denormalized (`actor_name`/`actor_role` snapshot the
actor at the time of the action, not a live join), so the log stays
readable even after a user account is later renamed or deactivated.
"""
from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, TimestampMixin, UUIDMixin


class AuditAction(str):
    """Action codes -- plain str constants (not enum.Enum) so a future
    action never needs a migration to add (see AttendanceStatus's
    native_enum=False precedent for the same reasoning, applied here via
    a bare VARCHAR column instead of even a SAEnum)."""

    LOGIN = "login"
    LOGOUT = "logout"
    APPROVE = "approve"
    REJECT = "reject"
    GENERATE_PDF = "generate_pdf"
    DELETE = "delete"
    EXPORT = "export"


class AuditLog(UUIDMixin, TimestampMixin, Base):
    __tablename__ = "audit_logs"

    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True, index=True,
    )
    actor_name: Mapped[str] = mapped_column(String(150))
    action: Mapped[str] = mapped_column(String(30), index=True)
    entity_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    description: Mapped[str] = mapped_column(String(500))
