"""OTP generation/verification backed by Redis."""
import secrets

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis

logger = get_logger("otp")


class OtpService:
    """Generate and verify one-time passwords stored in Redis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = get_redis()

    def _key(self, nik: str) -> str:
        return f"otp:{nik}"

    async def request_otp(self, nik: str) -> str:
        """Generate an OTP, store with TTL, return it (dev delivery)."""
        code = "".join(secrets.choice("0123456789") for _ in range(self.settings.otp_length))
        await self.redis.set(self._key(nik), code, ex=self.settings.otp_ttl_seconds)
        logger.info("OTP for %s: %s (dev)", nik, code)
        return code

    async def verify_otp(self, nik: str, code: str) -> bool:
        """Verify and consume the OTP."""
        stored = await self.redis.get(self._key(nik))
        if stored and stored == code:
            await self.redis.delete(self._key(nik))
            return True
        return False
