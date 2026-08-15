"""Submission lifecycle endpoints: create, list, attach, approve, reject, download."""
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_any_permission, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.common import Page
from app.schemas.submission import (
    SubmissionAnswersUpdateRequest, SubmissionApproveRequest, SubmissionAttachmentRead,
    SubmissionCreate, SubmissionMasterDataUpdateRequest, SubmissionPreviewHtmlUpdateRequest,
    SubmissionRead, SubmissionRejectRequest, SubmissionStatusHistoryRead, SubmissionWalkinCreate,
)
from app.services.submission import SubmissionService

router = APIRouter(tags=["submissions"])


async def _load_user(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User row for the authenticated principal."""
    from uuid import UUID as _UUID
    user = await session.get(User, _UUID(current.id))
    return user


async def _submission_read(session: AsyncSession, obj) -> dict:
    """Build a SubmissionRead dict enriched with the staff-entered master-
    data block and supporting documents.

    applicant_nik/applicant_nama are now real columns on `obj`, picked up
    automatically by `model_validate` -- only the staff-entered identity
    block (alamat/RT/jk/TTL/pekerjaan/status/no_kk,
    SubmissionService.build_applicant_snapshot) needs resolving here.
    """
    service = SubmissionService(session)
    data = SubmissionRead.model_validate(obj).model_dump(mode="json")
    applicant = await service.build_applicant_snapshot(obj)
    data["applicant_alamat"] = applicant["alamat"]
    data["applicant_no_kk"] = applicant["no_kk"]
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
        user, body.template_id, body.answers,
        body.applicant_nik, body.applicant_nama, body.physical_documents_promised,
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
        actor, body.template_id, body.applicant_nik, body.applicant_nama, body.answers,
        body.master_data.model_dump(mode="json") if body.master_data else None,
    )
    return success_response(await _submission_read(session, obj), "Surat terbit")


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


@router.put("/submissions/{submission_id}/master-data", response_model=Envelope[SubmissionRead])
async def update_submission_master_data(
    submission_id: UUID,
    body: SubmissionMasterDataUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:edit_master_data")),
) -> dict:
    """Staff fills in the shared identity block (alamat/RT/jk/tempat_lahir/
    tanggal_lahir/pekerjaan/status_kawin/no_kk) from the citizen's KTP/KK
    photo attachments -- blocking for Approve on letter types that need it
    (SubmissionService.get_missing_staff_fields)."""
    obj = await SubmissionService(session).update_master_data(
        submission_id, body.model_dump(mode="json")
    )
    return success_response(await _submission_read(session, obj), "Data master tersimpan")


@router.put("/submissions/{submission_id}/extra-data", response_model=Envelope[SubmissionRead])
async def update_submission_extra_data(
    submission_id: UUID,
    body: dict,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:edit_master_data")),
) -> dict:
    """Staff fills in the letter-specific master-data sesi (Tahap 3) that
    doesn't fit the generic identity block -- e.g. Domisili's alamat asal,
    NA's ayah/ibu/CSI blocks, KK's anggota keluarga table. Partial merge:
    only the sesi keys present in the body are updated."""
    obj = await SubmissionService(session).update_extra_data(submission_id, body)
    return success_response(await _submission_read(session, obj), "Data master tersimpan")


@router.get("/submissions/{submission_id}/master-data-schema", response_model=Envelope[dict])
async def get_submission_master_data_schema(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:edit_master_data")),
) -> dict:
    """Sesi definitions (Tahap 3) for this submission's letter type, plus
    current staff-entered values and citizen-provided anchor identities."""
    data = await SubmissionService(session).get_master_data_schema(submission_id)
    return success_response(data)


# 2026-08-13: every binary endpoint below returns a plain `Response`, not
# `StreamingResponse` -- even though the content is already fully-buffered
# `bytes` (read whole from disk before the handler returns), wrapping it in
# `StreamingResponse(io.BytesIO(...))` added a reproducible ~2s of latency
# per request. Root cause: this app's `RequestIdMiddleware` is a
# `BaseHTTPMiddleware`, and Starlette's `BaseHTTPMiddleware` has a
# long-standing interaction bug with `StreamingResponse` (extra event-loop
# round trips per chunk) -- confirmed by timing the service call alone
# (<10ms) vs. the full HTTP round trip (~2-4s) for the exact same request.
# `StreamingResponse` should only be used for content that's genuinely
# generated/read incrementally; anything already in memory as `bytes`
# belongs in a plain `Response`.
@router.get("/submissions/{submission_id}/attachments/{attachment_id}/file")
async def download_submission_attachment(
    submission_id: UUID,
    attachment_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> Response:
    """Return one of a submission's uploaded supporting documents, for
    staff/admin to view lampiran on the detail page."""
    from uuid import UUID as _UUID
    content, attachment = await SubmissionService(session).get_attachment_file(
        submission_id, attachment_id, _UUID(current.id), current.permissions
    )
    return Response(
        content=content, media_type=attachment.content_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.original_filename}"'},
    )


@router.get("/submissions/{submission_id}/attachments/{attachment_id}/preview")
async def preview_submission_attachment(
    submission_id: UUID,
    attachment_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> Response:
    """Downscaled preview of a lampiran (see
    FileStorageService.read_preview) for the staff viewer's carousel
    thumbnail + main preview -- much lighter than the full original served
    by /file, which stays available (unchanged) for "Unduh"."""
    from uuid import UUID as _UUID
    content, content_type, attachment = await SubmissionService(session).get_attachment_preview(
        submission_id, attachment_id, _UUID(current.id), current.permissions
    )
    return Response(
        content=content, media_type=content_type,
        headers={"Content-Disposition": f'inline; filename="{attachment.original_filename}"'},
    )


@router.get("/submissions/{submission_id}/pdf")
async def download_submission_pdf(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:download")),
) -> Response:
    """Download the issued PDF for a submission."""
    from uuid import UUID as _UUID
    pdf_bytes = await SubmissionService(session).download_pdf(
        submission_id, _UUID(current.id), current.permissions
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="surat-{submission_id}.pdf"'},
    )


@router.get("/submissions/{submission_id}/pdf/{sub_doc_code}")
async def download_submission_sub_doc_pdf(
    submission_id: UUID,
    sub_doc_code: str,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:download")),
) -> Response:
    """Download a specific sub-document PDF for an issued submission (e.g. NA sub-documents)."""
    from uuid import UUID as _UUID
    pdf_bytes = await SubmissionService(session).download_sub_document_pdf(
        submission_id, sub_doc_code, _UUID(current.id), current.permissions
    )
    return Response(
        content=pdf_bytes, media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{sub_doc_code}-{submission_id}.pdf"'},
    )


@router.get("/submissions/{submission_id}/preview-html", response_model=Envelope[dict])
async def get_submission_preview_html(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(
        require_any_permission("submission:approve", "submission:read_all")
    ),
) -> dict:
    """Pratinjau HTML surat dengan data pengajuan yang sesungguhnya (Tahap 4,
    ALUR_REVIEW_INPUT_MASTER.md) -- bukan PDF final, tidak menyimpan
    apapun, aman dipanggil berulang kali sebelum surat benar-benar
    disetujui.

    Gated on submission:approve OR submission:read_all (not approve alone)
    so Kepala Desa -- view-only by design (submission:approve deliberately
    withheld, see permissions/registry.py), but still holding
    submission:read_all/download -- can see this read-only preview of data
    he's already entitled to see in full.
    """
    html = await SubmissionService(session).get_preview_html(submission_id)
    return success_response({"html": html})


@router.get("/submissions/{submission_id}/preview-pdf")
async def get_submission_preview_pdf(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(
        require_any_permission("submission:approve", "submission:read_all")
    ),
) -> Response:
    """Pratinjau PDF surat dalam format resmi asli (docx specimen F-1.02/
    F-1.03/dll untuk 8 dari 9 jenis surat -- 2026-08-13, Tahap 4 redesign)
    dengan data pengajuan yang sesungguhnya. Bukan PDF final (tidak
    menyimpan/menandai terbit), aman dipanggil berulang kali. Sama gating-nya
    dengan preview-html.
    """
    pdf_bytes = await SubmissionService(session).get_preview_pdf(submission_id)
    return Response(content=pdf_bytes, media_type="application/pdf")


@router.put("/submissions/{submission_id}/preview-html", response_model=Envelope[SubmissionRead])
async def update_submission_preview_html(
    submission_id: UUID,
    body: SubmissionPreviewHtmlUpdateRequest,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Staff's manually-edited full letter HTML (Tahap 4 WYSIWYG editor) --
    becomes the source of truth for the issued/regenerated PDF. Rejected for
    letter types rendered from a real docx specimen (SubmissionService.
    update_preview_html's guard) -- Tahap 4's UI only shows this editor for
    the one jenis without one ("ubah_data")."""
    obj = await SubmissionService(session).update_preview_html(submission_id, body.html)
    return success_response(await _submission_read(session, obj), "Surat diperbarui")
