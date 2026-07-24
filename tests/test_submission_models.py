from app.models.submission import (
    ApprovalStepConfig, HistoryAction, LetterNumberCounter, Submission,
    SubmissionAttachment, SubmissionStatus, SubmissionStatusHistory,
)


def test_submission_tables():
    assert ApprovalStepConfig.__tablename__ == "approval_step_configs"
    assert Submission.__tablename__ == "submissions"
    assert SubmissionStatusHistory.__tablename__ == "submission_status_history"
    assert SubmissionAttachment.__tablename__ == "submission_attachments"
    assert LetterNumberCounter.__tablename__ == "letter_number_counters"
    assert SubmissionStatus.PENDING == "pending"
    assert HistoryAction.ISSUED == "issued"
