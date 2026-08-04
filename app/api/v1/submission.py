"""Submission lifecycle endpoints: create, list, attach, approve, reject, download."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.common import Page
from app.schemas.submission import (
    ApplicantDataCompleteRequest, ApplicantDataRead, ApplicantLookupRead,
    SubmissionAnswersUpdateRequest, SubmissionApproveRequest, SubmissionAttachmentRead,
    SubmissionCreate, SubmissionRead, SubmissionRejectRequest, SubmissionStatusHistoryRead,
    SubmissionWalkinCreate,
)
from app.services.submission import SubmissionService

router = APIRouter(tags=["submissions"])


async def _load_user(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User row for the authenticated principal."""
    from uuid import UUID as _UUID
    user = await session.get(User, _UUID(current.id))
    return user


async def _submission_read(session: AsyncSession, obj) -> dict:
    """Build a SubmissionRead dict enriched with the applicant's name and
    supporting documents.

    Staff/admin reviewing a submission need to know who it's for, whether it
    came from a logged-in user or a guest -- resolve it the same way the
    PDF-issuance path already does
    (SubmissionService.resolve_applicant_data_for_submission).
    """
    service = SubmissionService(session)
    data = SubmissionRead.model_validate(obj).model_dump(mode="json")
    applicant = await service.resolve_applicant_data_for_submission(obj)
    data["applicant_nama"] = applicant["nama"]
    data["applicant_nik"] = applicant["nik"]
    data["applicant_alamat"] = applicant["alamat"]
    data["applicant_no_kk"] = applicant["no_kk"]
    data["applicant_in_master_data"] = obj.applicant_resident_id is not None
    data["applicant_resident_id"] = obj.applicant_resident_id
    data["applicant_jk"] = applicant.get("jk")
    data["applicant_tempat_lahir"] = applicant.get("tempat_lahir")
    data["applicant_tanggal_lahir"] = applicant.get("tanggal_lahir")
    data["applicant_pekerjaan"] = applicant.get("pekerjaan")
    data["applicant_status_kawin"] = applicant.get("status_kawin")
    data["applicant_rt_id"] = applicant.get("rt_id")
    data["missing_staff_fields"] = await service.get_missing_staff_fields(obj)
    attachments = await service.list_attachments(obj.id)
    data["attachments"] = [
        SubmissionAttachmentRead.model_validate(a).model_dump(mode="json") for a in attachments
    ]
    return data


async def _history_read(session: AsyncSession, history) -> list[dict]:
    """Build SubmissionStatusHistoryRead dicts enriched with the acting
    user's username (raw actor_user_id isn't useful to staff/guests
    checking who approved/rejected a submission)."""
    from uuid import UUID as _UUID

    actor_ids = {h.actor_user_id for h in history if h.actor_user_id is not None}
    usernames: dict[_UUID, str] = {}
    if actor_ids:
        users = await session.scalars(select(User).where(User.id.in_(actor_ids)))
        usernames = {u.id: u.username for u in users}
    result = []
    for h in history:
        data = SubmissionStatusHistoryRead.model_validate(h).model_dump(mode="json")
        data["actor_username"] = usernames.get(h.actor_user_id)
        result.append(data)
    return result


@router.post("/submissions", response_model=Envelope[SubmissionRead])
async def create_submission(
    body: SubmissionCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Create a new letter submission."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).create(
        user, body.template_id, body.answers, body.physical_documents_promised
    )
    return success_response(await _submission_read(session, obj), "Tersimpan")


@router.post("/submissions/walkin", response_model=Envelope[SubmissionRead])
async def create_walkin_submission(
    body: SubmissionWalkinCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:walkin")),
) -> dict:
    """Mode Loket: staff submits and immediately issues on a walk-in citizen's behalf."""
    actor = await _load_user(session, current)
    obj = await SubmissionService(session).create_walkin(
        actor, body.template_id, body.nik, body.answers,
        body.applicant_nama, body.applicant_alamat,
    )
    return success_response(await _submission_read(session, obj), "Surat terbit")


@router.get("/submissions/walkin/applicant-lookup", response_model=Envelope[ApplicantLookupRead])
async def lookup_walkin_applicant(
    nik: str = Query(..., min_length=16, max_length=16, pattern=r"^\d{16}$"),
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:walkin")),
) -> dict:
    """Autofill lookup for the Mode Loket form: exact NIK match only."""
    data = await SubmissionService(session).lookup_applicant_by_nik(nik)
    if data is None:
        raise NotFoundError("NIK belum terdaftar")
    return success_response(data)


@router.get("/submissions/me/applicant-data", response_model=Envelope[ApplicantDataRead])
async def get_my_applicant_data(
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Auto-fill data (nama/nik/alamat/no_kk) for the caller's own submission form.

    Static route: must precede /submissions/{submission_id} so "me" is never
    parsed as a submission id.
    """
    user = await _load_user(session, current)
    data = await SubmissionService(session).resolve_applicant_data(user)
    return success_response(data)


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
    return success_response({
        "items": [await _submission_read(session, i) for i in items],
        "total": total, "page": p.page, "size": p.size,
    })


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
    return success_response(await _submission_read(session, obj))


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
    return success_response(await _submission_read(session, obj), "Diproses")


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
    return success_response(await _submission_read(session, obj), "Ditolak")


@router.post("/submissions/{submission_id}/regenerate-pdf", response_model=Envelope[SubmissionRead])
async def regenerate_submission_pdf(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Re-render an already-issued submission's PDF from its current data,
    overwriting the stored file(s) -- a separate, deliberate action from
    "Setujui" so staff can refresh the frozen PDF after correcting data
    post-issuance without re-running the approval flow (and without
    accidentally triggering it by re-clicking Setujui)."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).regenerate_pdf(submission_id, user)
    return success_response(await _submission_read(session, obj), "PDF berhasil digenerate ulang")


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
    return success_response(await _history_read(session, history))


@router.patch("/submissions/{submission_id}/applicant-data", response_model=Envelope[SubmissionRead])
async def complete_applicant_data(
    submission_id: UUID,
    body: ApplicantDataCompleteRequest,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Staff fills in master-data fields (No. KK, RT, identity snapshot) for
    a guest submission whose NIK wasn't already on file -- applied to
    residents/family_cards once this submission is approved (Bagian 5,
    Master Data rework)."""
    obj = await SubmissionService(session).complete_applicant_data(
        submission_id, body.no_kk, body.rt_id,
        body.jk, body.tempat_lahir, body.tanggal_lahir, body.pekerjaan, body.status_kawin,
        body.alamat,
    )
    return success_response(await _submission_read(session, obj), "Data pemohon diperbarui")


@router.put("/submissions/{submission_id}/answers", response_model=Envelope[SubmissionRead])
async def update_submission_answers(
    submission_id: UUID,
    body: SubmissionAnswersUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Staff correction of a pending submission's own "Data Formulir" answers
    (e.g. a typo the citizen made) -- only while still pending, re-validated
    against the template's field rules exactly like a fresh submission."""
    obj = await SubmissionService(session).update_answers(submission_id, body.answers)
    return success_response(await _submission_read(session, obj), "Data formulir diperbarui")


@router.get("/submissions/{submission_id}/attachments/{attachment_id}/file")
async def download_submission_attachment(
    submission_id: UUID,
    attachment_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> StreamingResponse:
    """Stream one of a submission's uploaded supporting documents, for
    staff/admin to view lampiran on the detail page."""
    from uuid import UUID as _UUID
    content, attachment = await SubmissionService(session).get_attachment_file(
        submission_id, attachment_id, _UUID(current.id), current.permissions
    )
    return StreamingResponse(
        io.BytesIO(content), media_type=attachment.content_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.original_filename}"'},
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


@router.get("/submissions/{submission_id}/pdf/{sub_doc_code}")
async def download_submission_sub_doc_pdf(
    submission_id: UUID,
    sub_doc_code: str,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:download")),
) -> StreamingResponse:
    """Download a specific sub-document PDF for an issued submission (e.g. NA sub-documents)."""
    from uuid import UUID as _UUID
    pdf_bytes = await SubmissionService(session).download_sub_document_pdf(
        submission_id, sub_doc_code, _UUID(current.id), current.permissions
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{sub_doc_code}-{submission_id}.pdf"'},
    )

