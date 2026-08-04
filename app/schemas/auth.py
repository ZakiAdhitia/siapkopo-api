"""Auth request/response schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _validate_email_format(value: str) -> str:
    """Lightweight email-shape check (no pydantic[email] dependency)."""
    if "@" not in value or "." not in value.split("@")[-1] or value.startswith("@") or value.endswith("@"):
        raise ValueError("Format email tidak valid")
    return value


class LoginRequest(BaseModel):
    """Login credentials: identifier matches username OR nik."""

    identifier: str = Field(min_length=1)
    password: str


class RegisterRequest(BaseModel):
    """Self-registration request."""

    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    email: str
    # "warga" (plain citizen) is intentionally not a registrable position --
    # citizens use the guest submission flow instead of an account (Bagian 6,
    # STRATEGI doc rev. 2026-07-26).
    position_choice: Literal["staff", "rt", "rw"]
    nik: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^\d{16}$")
    rt_id: UUID | None = None
    rw_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validate_email_format(v)


class RegisterResponse(BaseModel):
    """Outcome of a registration request."""

    status: Literal["active", "pending_approval"]
    message: str


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)


class ForgotPasswordResponse(BaseModel):
    """Always the same shape regardless of whether identifier matched an account."""

    message: str
    # dev only: code echoed back so the frontend/test can proceed without a real
    # email provider. None in production, and None if no account matched --
    # do not use presence/absence of this field to infer account existence.
    dev_code: str | None = None


class ResetPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)
    code: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class RefreshRequest(BaseModel):
    """Raw refresh token submitted for rotation."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional refresh token to revoke on logout."""

    refresh_token: str | None = None


class TokenData(BaseModel):
    """Issued access/refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RoleRead(BaseModel):
    """Read-only listing of the fixed Role catalog -- like Position, Role has
    no create/update/delete API by design; the approval-step config screen
    needs this to show/pick roles by name instead of raw ids."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    display_name: str


class MeData(BaseModel):
    """Current authenticated identity."""

    id: str
    role: str
    permissions: list[str]
    username: str | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    position_name: str | None = None
    # Which RT/RW this account is scoped to, for users whose Position is
    # "rt"/"rw" (set at account creation, see UserRole.jsx) -- they lack
    # rt:manage/rw:manage, so they can't call GET /rt themselves to
    # discover this on their own.
    rt_id: UUID | None = None
    rw_id: UUID | None = None
