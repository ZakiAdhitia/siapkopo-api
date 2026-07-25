import pytest
from app.core.exceptions import ConflictError
from app.models.auth import Role
from app.models.submission import Submission, SubmissionStatus
from app.services.approval_config import ApprovalStepConfigService
from sqlalchemy import select


@pytest.mark.asyncio
async def test_replace_all_then_list(seeded_session):
    roles = {
        r.name: r for r in (await seeded_session.scalars(select(Role))).all()
    }
    svc = ApprovalStepConfigService(seeded_session)
    steps = await svc.replace_all(
        [roles["staff"].id, roles["admin"].id]
    )
    assert [s.order_index for s in steps] == [0, 1]
    listed = await svc.list_steps()
    assert [s.role_id for s in listed] == [roles["staff"].id, roles["admin"].id]


@pytest.mark.asyncio
async def test_replace_all_rejected_when_pending_submission_exists(seeded_session):
    roles = {r.name: r for r in (await seeded_session.scalars(select(Role))).all()}
    svc = ApprovalStepConfigService(seeded_session)
    await svc.replace_all([roles["staff"].id])
    seeded_session.add(Submission(
        template_id="00000000-0000-0000-0000-000000000000",
        submitted_by_user_id="00000000-0000-0000-0000-000000000000",
        answers={}, status=SubmissionStatus.PENDING, current_step_index=0,
    ))
    await seeded_session.commit()
    with pytest.raises(ConflictError):
        await svc.replace_all([roles["admin"].id])
