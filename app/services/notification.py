"""Notification provider abstraction + in-app NotificationService (Bagian 9).

Real outbound delivery (SMTP, etc.) is out of scope for this rework part --
`LoggingNotificationProvider` is the only concrete provider, log-only. It is
swappable without touching any caller: everything goes through the
`NotificationProvider` interface.
"""
import uuid
from abc import ABC, abstractmethod

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.notification import Notification

logger = get_logger("notification")


class NotificationProvider(ABC):
    """Abstract outbound channel for notifications. In-app-only today --
    no WhatsApp channel exists anywhere in this system (see rework spec)."""

    @abstractmethod
    def send_email(self, to: str, subject: str, body: str) -> None:
        """Send (or, for the log-only provider, record) an email."""


class LoggingNotificationProvider(NotificationProvider):
    """Log-only provider: no real email is sent. Ready to be swapped for a
    real SMTP-backed provider later without changing any caller."""

    def send_email(self, to: str, subject: str, body: str) -> None:
        logger.info("Email (log-only) to=%s subject=%s body=%s", to, subject, body)


class NotificationService:
    """Creates in-app Notification rows and dispatches them through a
    NotificationProvider. Used for submission status changes, registration
    approval/rejection, and password-reset codes.
    """

    def __init__(self, session: AsyncSession, provider: NotificationProvider | None = None) -> None:
        self.session = session
        self.provider = provider or LoggingNotificationProvider()

    async def notify(
        self, user_id: uuid.UUID, event_type: str, title: str, body: str,
        email_to: str | None = None,
    ) -> Notification:
        """Create an in-app notification and, if `email_to` is given, also
        dispatch it through the email channel."""
        notif = Notification(user_id=user_id, event_type=event_type, title=title, body=body)
        self.session.add(notif)
        await self.session.commit()
        if email_to:
            self.provider.send_email(email_to, title, body)
        logger.info("Notification created id=%s user_id=%s event=%s", notif.id, user_id, event_type)
        return notif

    async def list(
        self, user_id: uuid.UUID, page: int, size: int
    ) -> tuple[list[Notification], int]:
        """List a user's notifications, newest first."""
        stmt = select(Notification).where(Notification.user_id == user_id)
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = stmt.order_by(Notification.created_at.desc()).offset((page - 1) * size).limit(size)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        """Mark one of the user's own notifications as read."""
        notif = await self.session.scalar(
            select(Notification).where(
                Notification.id == notification_id, Notification.user_id == user_id
            )
        )
        if notif is None:
            raise NotFoundError("Notifikasi tidak ditemukan")
        notif.is_read = True
        await self.session.commit()
        return notif

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        """Mark all of the user's unread notifications as read; return count changed."""
        stmt = select(Notification).where(
            Notification.user_id == user_id, Notification.is_read.is_(False)
        )
        rows = list((await self.session.scalars(stmt)).all())
        for row in rows:
            row.is_read = True
        await self.session.commit()
        return len(rows)
