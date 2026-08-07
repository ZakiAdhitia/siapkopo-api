"""Auth dependencies: current user resolution + permission guard."""
from collections.abc import Callable
from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError, UnauthorizedError
from app.core.security import decode_token
from app.db.session import get_db
from app.services.auth import AuthService

oauth2_scheme = OAuth2PasswordBearer(
    tokenUrl=f"{get_settings().api_v1_prefix}/auth/login", auto_error=False
)


@dataclass
class CurrentUser:
    """The authenticated principal resolved from a decoded access token."""

    id: str
    role: str
    permissions: list[str]
    jti: str


async def get_current_user(
    token: str | None = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_db),
) -> CurrentUser:
    """Decode the bearer token, reject blacklisted/invalid tokens."""
    if not token:
        raise UnauthorizedError("Tidak ada token")
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise UnauthorizedError("Token tidak valid")
    svc = AuthService(session)
    if await svc.is_blacklisted(payload.get("jti", "")):
        raise UnauthorizedError("Token sudah logout")
    return CurrentUser(
        id=payload["sub"], role=payload["role"],
        permissions=payload.get("permissions", []), jti=payload["jti"],
    )


def require_permission(code: str) -> Callable:
    """Dependency factory enforcing a single permission code."""

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions or code in user.permissions:
            return user
        raise ForbiddenError(f"Tidak memiliki izin: {code}")

    return _dep


def require_any_permission(*codes: str) -> Callable:
    """Dependency factory enforcing at least one of several permission codes.

    Use for endpoints shared by two otherwise-unrelated features (e.g. the
    Role catalog is read both by the approval-step picker and the user
    management screen), so each caller keeps its own permission boundary.
    """

    async def _dep(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if "*" in user.permissions or any(c in user.permissions for c in codes):
            return user
        raise ForbiddenError(f"Tidak memiliki izin: {' / '.join(codes)}")

    return _dep
