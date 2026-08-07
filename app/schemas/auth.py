"""Auth request/response schemas."""
from pydantic import BaseModel, Field


def _validate_email_format(value: str) -> str:
    """Lightweight email-shape check (no pydantic[email] dependency)."""
    if "@" not in value or "." not in value.split("@")[-1] or value.startswith("@") or value.endswith("@"):
        raise ValueError("Format email tidak valid")
    return value


class LoginRequest(BaseModel):
    """Login credentials: identifier matches username OR nik."""

    identifier: str = Field(min_length=1)
    password: str


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
