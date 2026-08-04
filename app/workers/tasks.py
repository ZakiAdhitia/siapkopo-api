"""ARQ background jobs.

Run with: `arq app.workers.tasks.WorkerSettings`

`LoggingNotificationProvider.send_email()` is called synchronously today
(it's non-blocking, so there is no request-time cost to defer).
`send_email_job` is the queue-ready seam for a future provider that DOES
block on real I/O (SMTP, etc.) -- callers can enqueue it instead of calling
the provider inline, without any other code changing.
"""
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.notification import LoggingNotificationProvider

logger = get_logger("worker")


async def send_email_job(ctx: dict, to: str, subject: str, body: str) -> None:
    """Dispatch an email through the notification provider."""
    LoggingNotificationProvider().send_email(to, subject, body)


class WorkerSettings:
    functions = [send_email_job]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
