"""JWT and password hashing utilities."""
import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings
from app.core.exceptions import UnauthorizedError

_pwd = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(pw: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return _pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return _pwd.verify(pw, hashed)


def create_access_token(subject: str, role: str, permissions: list[str], jti: str) -> str:
    """Create a signed JWT access token."""
    s = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject, "role": role, "permissions": permissions, "jti": jti,
        "type": "access", "iat": now,
        "exp": now + timedelta(minutes=s.access_token_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm=s.jwt_algorithm)


def create_refresh_token_value() -> tuple[str, str]:
    """Return (raw_refresh_token, sha256_hash)."""
    raw = secrets.token_urlsafe(48)
    return raw, hash_token(raw)


def hash_token(raw: str) -> str:
    """SHA-256 hash of a token for at-rest storage."""
    return hashlib.sha256(raw.encode()).hexdigest()


def decode_token(token: str) -> dict:
    """Decode/verify a JWT, raising UnauthorizedError on failure."""
    s = get_settings()
    try:
        return jwt.decode(token, s.jwt_secret, algorithms=[s.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise UnauthorizedError("Invalid or expired token") from exc
