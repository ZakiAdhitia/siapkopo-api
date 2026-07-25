"""ARQ background jobs.

Run with: `arq app.workers.tasks.WorkerSettings`

`NotificationService.notify()` already writes the Notification row and
calls the provider synchronously in the request path (today's
`LoggingNotificationProvider` is non-blocking, so there is no request-time
cost to defer). `send_notification_job` is the queue-ready seam for a
future provider that DOES block on real I/O (SMTP, etc.) -- callers can
enqueue it instead of calling `NotificationService.notify()` inline,
without any other code changing.
"""
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import AsyncSessionLocal
from app.services.notification import NotificationService

logger = get_logger("worker")


async def send_notification_job(
    ctx: dict, user_id: str, event_type: str, title: str, body: str,
    email_to: str | None = None,
) -> None:
    """Create a Notification row and dispatch it through the email channel."""
    async with AsyncSessionLocal() as session:
        await NotificationService(session).notify(user_id, event_type, title, body, email_to)


class WorkerSettings:
    functions = [send_notification_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
