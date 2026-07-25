"""Village approval-step configuration endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.schemas.submission import ApprovalStepConfigRead, ApprovalStepsReplaceRequest
from app.services.approval_config import ApprovalStepConfigService

router = APIRouter(tags=["approval-config"])


@router.get("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def list_approval_steps(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List the ordered approval steps."""
    steps = await ApprovalStepConfigService(session).list_steps()
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps]
    )


@router.put("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def replace_approval_steps(
    body: ApprovalStepsReplaceRequest,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("approval_config:manage")),
) -> dict:
    """Replace the entire approval-step chain."""
    steps = await ApprovalStepConfigService(session).replace_all(
        [item.role_id for item in body.steps]
    )
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps],
        "Alur persetujuan diperbarui",
    )
