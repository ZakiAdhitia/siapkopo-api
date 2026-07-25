"""Authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.schemas.auth import (
    ForgotPasswordRequest, ForgotPasswordResponse, LoginRequest, LogoutRequest,
    MeData, RefreshRequest, RegisterRequest, RegisterResponse, ResetPasswordRequest,
    TokenData,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Envelope[RegisterResponse])
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Self-register a new account."""
    _user, is_active = await AuthService(session).register(body.model_dump())
    if is_active:
        data = RegisterResponse(status="active", message="Registrasi berhasil, silakan masuk")
    else:
        data = RegisterResponse(
            status="pending_approval",
            message="Registrasi berhasil, menunggu persetujuan admin sebelum dapat masuk",
        )
    return success_response(data.model_dump(), data.message)


@router.post("/login", response_model=Envelope[TokenData])
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Login with username or NIK + password."""
    pair = await AuthService(session).login(body.identifier, body.password)
    return success_response(pair, "Login berhasil")


@router.post("/forgot-password", response_model=Envelope[ForgotPasswordResponse])
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Request a password-reset code. Response shape never reveals account existence."""
    code = await AuthService(session).forgot_password(body.identifier)
    data = ForgotPasswordResponse(
        message="Jika akun ditemukan, kode reset telah dikirim ke email terdaftar",
        dev_code=code,
    )
    return success_response(data.model_dump())


@router.post("/reset-password", response_model=Envelope[None])
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Reset a password using a code from /forgot-password."""
    await AuthService(session).reset_password(body.identifier, body.code, body.new_password)
    return success_response(None, "Kata sandi berhasil diubah")


@router.post("/refresh", response_model=Envelope[TokenData])
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Rotate the refresh token."""
    pair = await AuthService(session).refresh(body.refresh_token)
    return success_response(pair, "Token diperbarui")


@router.post("/logout", response_model=Envelope[None])
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


@router.get("/me", response_model=Envelope[MeData])
async def me(user: CurrentUser = Depends(require_permission("auth:me"))) -> dict:
    """Return the current identity and permissions."""
    return success_response(
        {"id": user.id, "role": user.role, "permissions": user.permissions}
    )
