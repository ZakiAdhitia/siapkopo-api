"""Public, no-auth letter verification endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.models.auth import User
from app.models.letter_template import LetterTemplate
from app.models.submission import Submission, SubmissionStatus
from app.schemas.submission import PublicVerifyRead
from app.services.submission import SubmissionService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/verify/{code}", response_model=Envelope[PublicVerifyRead])
async def verify_letter(code: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Publicly verify an issued letter by its verification code. No auth required."""
    submission = await session.scalar(
        select(Submission).where(
            Submission.verification_code == code,
            Submission.status == SubmissionStatus.ISSUED,
        )
    )
    if submission is None:
        raise NotFoundError("Kode verifikasi tidak ditemukan")

    template = await session.get(LetterTemplate, submission.template_id)
    applicant = await SubmissionService(session).resolve_applicant_data(
        await session.get(User, submission.submitted_by_user_id)
    )
    signer_name = await SubmissionService(session).resolve_signer_name()

    return success_response(PublicVerifyRead(
        letter_number=submission.letter_number or "",
        template_name=template.name if template else "",
        applicant_name=applicant["nama"],
        issued_at=submission.issued_at,
        signed_by=signer_name,
    ).model_dump(mode="json"))
