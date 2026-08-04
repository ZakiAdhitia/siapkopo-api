"""Schemas for admin-driven user & position management (Bagian 8)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.auth import _validate_email_format


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    # 2026-08-05 (HASIL_UJICOBA_PERROLE.md kades item 4): swapped from the
    # original email-required/phone-optional -- a village staff account is
    # far more likely to have a phone number on file than a personal email.
    email: str | None = None
    phone: str = Field(min_length=8, max_length=20)
    position_id: UUID
    nik: str | None = Field(default=None, min_length=8, max_length=20)
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    resident_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        return v if v is None else _validate_email_format(v)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = None
    phone: str | None = None
    password: str | None = Field(default=None, min_length=6)
    position_id: UUID | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        return v if v is None else _validate_email_format(v)


class PositionRead(BaseModel):
    """Read-only listing of the fixed Position catalog -- Position itself has
    no create/update/delete API by design, but admin user-management forms
    need this to populate a position picker with real ids."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    slug: str
    display_name: str
    level: int


class UserRead(BaseModel):
    id: UUID
    username: str | None = None
    nik: str | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool
    pending_approval: bool
    role_id: UUID
    role_name: str
    position_id: UUID | None = None
    position_name: str | None = None
    position_level: int | None = None
    resident_id: UUID | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    created_at: datetime
