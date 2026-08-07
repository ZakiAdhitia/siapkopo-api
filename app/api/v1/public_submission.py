"""Public, no-auth submission endpoints: zero-friction guest flow (Bagian
3.2, STRATEGI doc) -- submit without an account, then check status later
using NIK/WhatsApp/Email instead of a login (Bagian 8, STRATEGI doc rev.
2026-07-26 -- no tracking number to save, just one of the three identifiers
the citizen already knows). The issued PDF is no longer downloadable by the
guest here (Revisi 2026-07-26 sore): it's an internal working document for
staff to print/sign/stamp, not a citizen-facing digital deliverable -- see
`GET /submissions/{id}/pdf` (authenticated, staff/admin only).
"""
import json
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.submission import _history_read, _submission_read
from app.core.exceptions import ValidationAppError
from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.rate_limit import rate_limit
from app.schemas.letter_template import LetterTemplateRead, TemplateFieldRead
from app.schemas.master import RTRead, RWRead
from app.schemas.submission import GuestTrackRead
from app.services.letter_template import LetterTemplateService
from app.services.master import RTService, RWService
from app.services.submission import SubmissionService

_EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
_WHATSAPP_PATTERN = r"^(\+62|62|0)8[1-9][0-9]{6,10}$"

router = APIRouter(tags=["public-submissions"])


@router.get("/public/templates", response_model=Envelope[list[LetterTemplateRead]])
async def list_public_templates(session: AsyncSession = Depends(get_db)) -> dict:
    """Active letter types for the guest submission picker (no login)."""
    items, _ = await LetterTemplateService(session).list(page=1, size=100, is_active=True)
    return success_response(
        [LetterTemplateRead.model_validate(i).model_dump(mode="json") for i in items]
    )


@router.get("/public/templates/{template_id}/fields", response_model=Envelope[list[TemplateFieldRead]])
async def list_public_template_fields(
    template_id: UUID, session: AsyncSession = Depends(get_db)
) -> dict:
    """Dynamic form fields for one letter type, for the guest submission form.

    2026-08-05 TAMBAHAN item 6: every field is now warga-input at
    submission time -- the `is_staff_only` filter is kept as a defensive
    no-op (no seeded field sets it anymore) rather than removed outright,
    in case a future letter type genuinely needs a staff-verified-only
    field again.
    """
    fields = await LetterTemplateService(session).list_fields(template_id)
    return success_response(
        [
            TemplateFieldRead.model_validate(f).model_dump(mode="json")
            for f in fields if not f.is_staff_only
        ]
    )


@router.get("/public/rw", response_model=Envelope[list[RWRead]])
async def list_public_rw(session: AsyncSession = Depends(get_db)) -> dict:
    """RW catalog for the guest submission form's RT/RW dropdown (2026-08-05
    TAMBAHAN item 5: RT/RW must be picked from real master data, never
    free-typed) -- just {id, number}, safe to expose with no auth."""
    items, _ = await RWService(session).list(page=1, size=500)
    return success_response([RWRead.model_validate(i).model_dump(mode="json") for i in items])


@router.get("/public/rt", response_model=Envelope[list[RTRead]])
async def list_public_rt(session: AsyncSession = Depends(get_db)) -> dict:
    """RT catalog (with parent rw_id) for the guest submission form's
    cascading RW -> RT dropdown -- see list_public_rw."""
    items, _ = await RTService(session).list(page=1, size=500)
    return success_response([RTRead.model_validate(i).model_dump(mode="json") for i in items])


@router.post(
    "/submissions/guest",
    response_model=Envelope[GuestTrackRead],
    dependencies=[Depends(rate_limit("guest_submit", limit=5, window_seconds=300))],
)
async def create_guest_submission(
    template_id: UUID = Form(...),
    applicant_nik: str = Form(..., min_length=16, max_length=16, pattern=r"^\d{16}$"),
    applicant_nama: str = Form(..., min_length=1),
    contact_email: str | None = Form(default=None, pattern=_EMAIL_PATTERN),
    contact_whatsapp: str = Form(..., pattern=_WHATSAPP_PATTERN),
    answers: str = Form(default="{}"),
    document_labels: list[str] = Form(default=[]),
    documents: list[UploadFile] = File(default=[]),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Submit a letter request with no account: NIK+nama + contact + the
    template's required supporting documents (mandatory upload, checked for
    blur -- Bagian 6, STRATEGI doc rev. 2026-07-26 anti-fraud requirement;
    no more "I'll bring it physically" opt-out for guests). 2026-08-06: no
    more identity autofill/lookup -- alamat/RT/jk/TTL/pekerjaan/status/no_kk
    are staff-entered later from KTP/KK photos via PUT .../master-data, not
    asked of the citizen here.
    """
    try:
        parsed_answers = json.loads(answers)
    except json.JSONDecodeError as exc:
        raise ValidationAppError("Format jawaban tidak valid") from exc
    if len(document_labels) != len(documents):
        raise ValidationAppError("Jumlah label dokumen tidak sesuai jumlah file")

    attachments = []
    for label, file in zip(document_labels, documents):
        content = await file.read()
        attachments.append(
            (label, file.filename or "upload", content, file.content_type or "application/octet-stream")
        )

    obj = await SubmissionService(session).create_guest(
        template_id, applicant_nik, applicant_nama, parsed_answers, contact_whatsapp, attachments,
        contact_email,
    )
    return success_response(await _guest_track_read(session, obj), "Pengajuan terkirim")


@router.get(
    "/submissions/guest/search",
    response_model=Envelope[list[GuestTrackRead]],
    dependencies=[Depends(rate_limit("guest_track", limit=20, window_seconds=300))],
)
async def search_guest_submissions(
    nik: str = Query(..., min_length=16, max_length=16, pattern=r"^\d{16}$"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """List every guest/Mode Loket submission matching the given NIK."""
    subs = await SubmissionService(session).search_guest_submissions(nik)
    return success_response([await _guest_track_read(session, s) for s in subs])


async def _guest_track_read(session: AsyncSession, obj) -> dict:
    """Build the combined GuestTrackRead payload: submission + history +
    just enough template info to render the status page (guests have no
    permission to call the authenticated /templates/{id} endpoint)."""
    service = SubmissionService(session)
    template = await LetterTemplateService(session).get_or_404(obj.template_id)
    history = await service.list_history(obj.id)
    return {
        "submission": await _submission_read(session, obj),
        "history": await _history_read(session, history),
        "template_name": template.name,
        "template_icon": template.icon,
        "template_color_bg": template.color_bg,
        "template_color_fg": template.color_fg,
        "template_output_category": template.output_category,
        "template_post_issuance_note": template.post_issuance_note,
    }
