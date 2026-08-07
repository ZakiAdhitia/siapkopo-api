"""Authentication endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.schemas.auth import (
    ChangePasswordRequest, ForgotPasswordRequest, ForgotPasswordResponse, LoginRequest,
    LogoutRequest, MeData, RefreshRequest, ResetPasswordRequest, TokenData,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

# 2026-08-05 TAMBAHAN item 8: self-registration ("Daftar") is removed --
# accounts are now created exclusively by internal staff via POST /users
# (user:manage), never by the public. The old pending_approval
# approve/reject flow on POST /users/{id}/approve|reject is left in place
# so any rows created before this change (if the dev DB has them) can still
# be resolved by an admin; no new pending_approval rows can be created now.


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


@router.post("/change-password", response_model=Envelope[None])
async def change_password(
    body: ChangePasswordRequest, session: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Self-service password change from the Profile page (requires the
    current password, unlike /reset-password's OTP-style code)."""
    await AuthService(session).change_password(UUID(user.id), body.old_password, body.new_password)
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
async def me(
    user: CurrentUser = Depends(require_permission("auth:me")),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Return the current identity, permissions, and profile basics."""
    record = await AuthService(session).users.get_by_id(UUID(user.id))
    return success_response({
        "id": user.id, "role": user.role, "permissions": user.permissions,
        "username": record.username, "full_name": record.full_name, "email": record.email,
        "phone": record.phone,
        "position_name": record.position.display_name if record.position else None,
    })
