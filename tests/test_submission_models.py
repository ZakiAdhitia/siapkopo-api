from app.models.submission import (
    HistoryAction, Submission,
    SubmissionAttachment, SubmissionStatus, SubmissionStatusHistory,
)


def test_submission_tables():
    assert Submission.__tablename__ == "submissions"
    assert SubmissionStatusHistory.__tablename__ == "submission_status_history"
    assert SubmissionAttachment.__tablename__ == "submission_attachments"
    assert SubmissionStatus.PENDING == "pending"
    assert HistoryAction.ISSUED == "issued"
