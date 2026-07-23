"""Authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.response import success_response
from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.schemas.auth import (
    LoginRequest, LogoutRequest, RefreshRequest, RequestOtpRequest, VerifyOtpRequest,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Staff login with username + password."""
    pair = await AuthService(session).login_password(body.username, body.password)
    return success_response(pair, "Login berhasil")


@router.post("/request-otp")
async def request_otp(body: RequestOtpRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Warga requests an OTP for their NIK."""
    code = await AuthService(session).otp.request_otp(body.nik)
    data = {"nik": body.nik}
    if get_settings().app_env != "production":
        data["dev_code"] = code
    return success_response(data, "OTP dikirim")


@router.post("/verify-otp")
async def verify_otp(body: VerifyOtpRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Warga verifies NIK + OTP and receives tokens."""
    pair = await AuthService(session).login_otp(body.nik, body.code)
    return success_response(pair, "Login berhasil")


@router.post("/refresh")
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Rotate the refresh token."""
    pair = await AuthService(session).refresh(body.refresh_token)
    return success_response(pair, "Token diperbarui")


@router.post("/logout")
async def logout(
    body: LogoutRequest, request: Request, session: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Blacklist the current access token and revoke refresh."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    await AuthService(session).logout(payload, body.refresh_token)
    return success_response(None, "Logout berhasil")


@router.get("/me")
async def me(user: CurrentUser = Depends(require_permission("auth:me"))) -> dict:
    """Return the current identity and permissions."""
    return success_response(
        {"id": user.id, "role": user.role, "permissions": user.permissions}
    )
