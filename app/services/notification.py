"""Email notification provider abstraction.

Real outbound delivery (SMTP, etc.) is out of scope for this rework part --
`LoggingNotificationProvider` is the only concrete provider, log-only. It is
swappable without touching any caller: everything goes through the
`NotificationProvider` interface.
"""
from abc import ABC, abstractmethod

from app.core.logging import get_logger

logger = get_logger("notification")


class NotificationProvider(ABC):
    """Abstract outbound channel for notifications. Email-only today --
    no WhatsApp channel exists anywhere in this system (see rework spec)."""

    @abstractmethod
    def send_email(
        self, to: str, subject: str, body: str,
        attachment: tuple[str, bytes] | None = None,
    ) -> None:
        """Send (or, for the log-only provider, record) an email.

        `attachment`, if given, is (filename, content) -- e.g. the issued
        letter PDF sent alongside the "surat terbit" notification.
        """


class LoggingNotificationProvider(NotificationProvider):
    """Log-only provider: no real email is sent. Ready to be swapped for a
    real SMTP-backed provider later without changing any caller."""

    def send_email(
        self, to: str, subject: str, body: str,
        attachment: tuple[str, bytes] | None = None,
    ) -> None:
        if attachment:
            filename, content = attachment
            logger.info(
                "Email (log-only) to=%s subject=%s body=%s attachment=%s (%d bytes)",
                to, subject, body, filename, len(content),
            )
        else:
            logger.info("Email (log-only) to=%s subject=%s body=%s", to, subject, body)
