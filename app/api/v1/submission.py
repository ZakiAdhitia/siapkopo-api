"""Submission lifecycle endpoints: create, list, attach, approve, reject, download."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.common import Page, build_page
from app.schemas.submission import (
    SubmissionApproveRequest, SubmissionAttachmentRead, SubmissionCreate, SubmissionRead,
    SubmissionRejectRequest, SubmissionStatusHistoryRead,
)
from app.services.submission import SubmissionService

router = APIRouter(tags=["submissions"])


async def _load_user(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User row for the authenticated principal."""
    from uuid import UUID as _UUID
    user = await session.get(User, _UUID(current.id))
    return user


@router.post("/submissions", response_model=Envelope[SubmissionRead])
async def create_submission(
    body: SubmissionCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Create a new letter submission."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).create(user, body.template_id, body.answers)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/submissions", response_model=Envelope[Page[SubmissionRead]])
async def list_submissions(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """List submissions: own only, unless the caller has submission:read_all."""
    from uuid import UUID as _UUID
    items, total = await SubmissionService(session).list(
        current.permissions, _UUID(current.id), p.page, p.size
    )
    return success_response(build_page(items, total, p.page, p.size, SubmissionRead))


@router.get("/submissions/{submission_id}", response_model=Envelope[SubmissionRead])
async def get_submission(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """Get a single submission by id: own only, unless the caller has submission:read_all."""
    from uuid import UUID as _UUID
    obj = await SubmissionService(session).get_scoped(
        submission_id, _UUID(current.id), current.permissions
    )
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"))


@router.post("/submissions/{submission_id}/attachments", response_model=Envelope[SubmissionAttachmentRead])
async def upload_attachment(
    submission_id: UUID,
    document_label: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Upload a supporting document for a submission."""
    from uuid import UUID as _UUID
    content = await file.read()
    obj = await SubmissionService(session).add_attachment(
        submission_id, document_label, file.filename or "upload",
        content, file.content_type or "application/octet-stream", _UUID(current.id),
    )
    return success_response(
        SubmissionAttachmentRead.model_validate(obj).model_dump(mode="json"), "Lampiran tersimpan"
    )


@router.post("/submissions/{submission_id}/approve", response_model=Envelope[SubmissionRead])
async def approve_submission(
    submission_id: UUID,
    body: SubmissionApproveRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Approve a submission at its current step (or issue it if this was the final step)."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).approve(submission_id, user, body.note)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Diproses")


@router.post("/submissions/{submission_id}/reject", response_model=Envelope[SubmissionRead])
async def reject_submission(
    submission_id: UUID,
    body: SubmissionRejectRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:reject")),
) -> dict:
    """Reject a submission with a mandatory reason (terminal)."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).reject(submission_id, user, body.reason)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Ditolak")


@router.get("/submissions/{submission_id}/history", response_model=Envelope[list[SubmissionStatusHistoryRead]])
async def get_submission_history(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """Return a submission's status history, oldest first.

    Own submissions only, unless the caller has submission:read_all.
    """
    from uuid import UUID as _UUID
    service = SubmissionService(session)
    await service.get_scoped(submission_id, _UUID(current.id), current.permissions)
    history = await service.list_history(submission_id)
    return success_response(
        [SubmissionStatusHistoryRead.model_validate(h).model_dump(mode="json") for h in history]
    )


@router.get("/submissions/{submission_id}/pdf")
async def download_submission_pdf(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:download")),
) -> StreamingResponse:
    """Download the issued PDF for a submission."""
    from uuid import UUID as _UUID
    pdf_bytes = await SubmissionService(session).download_pdf(
        submission_id, _UUID(current.id), current.permissions
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="surat-{submission_id}.pdf"'},
    )
