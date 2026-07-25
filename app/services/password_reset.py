"""Password-reset code generation/verification backed by Redis.

Same generate/store/verify/consume pattern the old OtpService used for
login OTPs -- OTP login itself is gone (see the rework spec), but the
underlying Redis-TTL-code mechanism is still the right tool for a
short-lived, single-use password-reset code.
"""
import secrets
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.auth import User

logger = get_logger("password_reset")


class PasswordResetService:
    """Generate and verify one-time password-reset codes stored in Redis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = get_redis()

    def _key(self, user_id: uuid.UUID) -> str:
        return f"pwreset:{user_id}"

    async def request_reset(self, user: User) -> str:
        """Generate a reset code, store with TTL, return it (dev delivery)."""
        code = "".join(
            secrets.choice("0123456789") for _ in range(self.settings.password_reset_code_length)
        )
        await self.redis.set(self._key(user.id), code, ex=self.settings.password_reset_ttl_seconds)
        if self.settings.app_env != "production":
            logger.info("Password reset code for user_id=%s: %s (dev)", user.id, code)
        else:
            logger.info("Password reset code generated for user_id=%s", user.id)
        return code

    async def verify_and_consume(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify and consume a reset code."""
        stored = await self.redis.get(self._key(user_id))
        if stored and stored == code:
            await self.redis.delete(self._key(user_id))
            return True
        return False
