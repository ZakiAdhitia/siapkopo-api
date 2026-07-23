"""Auth request/response schemas."""
from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """Staff login credentials."""

    username: str
    password: str


class RequestOtpRequest(BaseModel):
    """NIK for which an OTP should be issued."""

    nik: str = Field(min_length=8, max_length=20)


class VerifyOtpRequest(BaseModel):
    """NIK + OTP code submitted for verification."""

    nik: str
    code: str


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


class OtpRequestedData(BaseModel):
    """Response payload after requesting an OTP."""

    nik: str
    # dev only: code echoed back so the frontend/test can proceed without WhatsApp
    dev_code: str | None = None
