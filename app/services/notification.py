"""Notification hook stub — the Phase 8 integration point.

Real WhatsApp/Email dispatch through an ARQ queue is out of scope here;
this function only logs, so status-transition call sites (SubmissionService)
already have a clean place to call into once Phase 8 builds the real sender.
"""
from app.core.logging import get_logger
from app.models.submission import Submission

logger = get_logger("notification")


def notify_status_change(submission: Submission, event: str) -> None:
    """Log a submission status-change event (stub for future dispatch)."""
    logger.info(
        "Notification stub: submission_id=%s event=%s status=%s",
        submission.id, event, submission.status.value,
    )
