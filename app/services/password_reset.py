"""Password-reset code generation/verification, backed by the database.

Same generate/store/verify/consume pattern the old OtpService used for
login OTPs -- OTP login itself is gone (see the rework spec), but the
short-lived, single-use password-reset code mechanism is still the right
tool. Previously stored as a Redis key with TTL; now a ``PasswordResetCode``
row with an ``expires_at`` column (no Redis dependency).
"""
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.auth import PasswordResetCode, User
from app.services.notification import LoggingNotificationProvider, NotificationProvider
from app.services.whatsapp import WhatsAppProvider

logger = get_logger("password_reset")


class PasswordResetService:
    """Generate and verify one-time password-reset codes."""

    def __init__(
        self, session: AsyncSession,
        provider: NotificationProvider | None = None,
        whatsapp: WhatsAppProvider | None = None,
    ) -> None:
        self.session = session
        self.settings = get_settings()
        self.provider = provider or LoggingNotificationProvider()
        self.whatsapp = whatsapp or WhatsAppProvider()

    async def request_reset(self, user: User) -> str:
        """Generate a reset code, store with an expiry (replacing any
        existing code for this user), send it over every contact channel
        the account has on file (WhatsApp via Fonnte + email), and return
        it (dev delivery)."""
        code = "".join(
            secrets.choice("0123456789") for _ in range(self.settings.password_reset_code_length)
        )
        expires_at = datetime.now(timezone.utc) + timedelta(
            seconds=self.settings.password_reset_ttl_seconds
        )
        existing = await self.session.scalar(
            select(PasswordResetCode).where(PasswordResetCode.user_id == user.id)
        )
        if existing is not None:
            existing.code = code
            existing.expires_at = expires_at
        else:
            self.session.add(PasswordResetCode(user_id=user.id, code=code, expires_at=expires_at))
        await self.session.commit()

        message = (
            f"Kode reset password SIAPKOPO Anda: {code} "
            f"(berlaku {self.settings.password_reset_ttl_seconds // 60} menit)"
        )
        if user.phone:
            await self.whatsapp.send_message(user.phone, message)
        if user.email:
            self.provider.send_email(user.email, "Kode Reset Password SIAPKOPO", message)
        if self.settings.app_env != "production":
            logger.info("Password reset code for user_id=%s: %s (dev)", user.id, code)
        else:
            logger.info("Password reset code generated for user_id=%s", user.id)
        return code

    async def verify_and_consume(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify and consume a reset code. A wrong code does not consume
        the stored one, matching the prior Redis behavior (only a
        successful match deletes it)."""
        row = await self.session.scalar(
            select(PasswordResetCode).where(
                PasswordResetCode.user_id == user_id,
                PasswordResetCode.expires_at > datetime.now(timezone.utc),
            )
        )
        if row is not None and row.code == code:
            await self.session.delete(row)
            await self.session.commit()
            return True
        return False
