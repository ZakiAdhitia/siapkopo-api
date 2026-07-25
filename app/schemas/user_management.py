"""Schemas for admin-driven user & position management (Bagian 8)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import _validate_email_format


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    email: str
    position_id: UUID
    nik: str | None = Field(default=None, min_length=8, max_length=20)
    phone: str | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    resident_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validate_email_format(v)


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
