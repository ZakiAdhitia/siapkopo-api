"""Auth request/response schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


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
    position_choice: Literal["staff", "rt", "rw", "warga"]
    nik: str | None = Field(default=None, min_length=8, max_length=20)
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


class MeData(BaseModel):
    """Current authenticated identity."""

    id: str
    role: str
    permissions: list[str]
