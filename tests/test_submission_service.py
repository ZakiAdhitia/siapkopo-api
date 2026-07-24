import pytest
from sqlalchemy import select

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.models.auth import Role, User
from app.services.approval_config import ApprovalStepConfigService
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService
from app.services.submission import SubmissionService


async def _make_template_with_fields(session, village_id):
    svc = LetterTemplateService(session)
    template = await svc.create({
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ alamat_tinggal_saat_ini }}</p>",
    })
    await svc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat Tinggal Saat Ini",
        "field_type": "text", "is_required": True,
    })
    await svc.add_field(template.id, {
        "field_key": "keperluan", "label": "Keperluan", "field_type": "select",
        "options": ["Bank", "Sekolah"], "is_required": True,
    })
    return template


async def _make_warga_user(session, username: str) -> User:
    """Create a warga-role User for a test, using the seeded 'warga' Role row."""
    role = (await session.scalars(select(Role).where(Role.name == "warga"))).first()
    user = User(username=username, full_name="Warga Test", hashed_password="x", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_create_validates_required_fields(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {"alamat_tinggal_saat_ini": ""})  # missing keperluan


@pytest.mark.asyncio
async def test_create_validates_select_options(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test2")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {
            "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "NotAnOption",
        })


@pytest.mark.asyncio
async def test_create_succeeds_with_valid_answers(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test3")

    svc = SubmissionService(seeded_session)
    obj = await svc.create(user, template.id, {
        "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank",
    })
    assert obj.status.value == "pending"
    assert obj.current_step_index == 0

    got = await svc.get_or_404(obj.id)
    assert got.answers["keperluan"] == "Bank"


@pytest.mark.asyncio
async def test_add_attachment_validates_document_label(seeded_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
        })(),
    )
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p></p>", "required_documents": ["KTP"],
    })
    user = await _make_warga_user(seeded_session, "warga_att")

    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {})

    with pytest.raises(ValidationAppError):
        await svc.add_attachment(submission.id, "Bukan Dokumen Wajib", "x.png", b"abc", "image/png")

    att = await svc.add_attachment(submission.id, "KTP", "ktp.png", b"abc", "image/png")
    assert att.document_label == "KTP"
    assert att.original_filename == "ktp.png"


async def _setup_pending_submission(session):
    """Village + 3-step workflow (staf, sekretaris, kades) + one PENDING submission."""
    village = await VillageService(session).create({"name": "Desa Kopo"})
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    await ApprovalStepConfigService(session).replace_all(
        village.id, [roles["staf"].id, roles["sekretaris"].id, roles["kades"].id]
    )
    warga = User(username="warga_flow", full_name="Warga Flow", hashed_password="x",
                 role_id=roles["warga"].id)
    staf = User(username="staf_flow", full_name="Staf Flow", hashed_password="x",
                role_id=roles["staf"].id)
    sekdes = User(username="sekdes_flow", full_name="Sekdes Flow", hashed_password="x",
                  role_id=roles["sekretaris"].id)
    kades = User(username="kades_flow", full_name="Kades Flow", hashed_password="x",
                 role_id=roles["kades"].id)
    session.add_all([warga, staf, sekdes, kades])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(warga, template.id, {"alamat_tinggal_saat_ini": "Jl. Uji 1"})
    return svc, submission, {"warga": warga, "staf": staf, "sekdes": sekdes, "kades": kades}


@pytest.mark.asyncio
async def test_approve_wrong_turn_rejected(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    with pytest.raises(ForbiddenError):
        await svc.approve(submission.id, users["sekdes"], None)  # staf's turn, not sekdes


@pytest.mark.asyncio
async def test_approve_full_chain_issues_pdf(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)

    s1 = await svc.approve(submission.id, users["staf"], "ok")
    assert s1.current_step_index == 1
    assert s1.status.value == "pending"

    s2 = await svc.approve(submission.id, users["sekdes"], "ok")
    assert s2.current_step_index == 2

    s3 = await svc.approve(submission.id, users["kades"], "signed")
    assert s3.status.value == "issued"
    assert s3.letter_number is not None
    assert s3.verification_code is not None
    assert s3.pdf_storage_path is not None
    assert s3.issued_at is not None

    pdf_bytes = await svc.download_pdf(submission.id, users["warga"].id, ["submission:download"])
    assert pdf_bytes[:5] == b"%PDF-"

    history = await svc.list_history(submission.id)
    actions = [h.action.value for h in history]
    assert actions == ["submitted", "approved", "approved", "issued"]


@pytest.mark.asyncio
async def test_reject_is_terminal(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    rejected = await svc.reject(submission.id, users["staf"], "Berkas tidak lengkap")
    assert rejected.status.value == "rejected"
    assert rejected.rejection_reason == "Berkas tidak lengkap"
    with pytest.raises(ValidationAppError):
        await svc.approve(submission.id, users["staf"], None)


@pytest.mark.asyncio
async def test_download_pdf_rejects_non_owner_without_read_all(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    await svc.approve(submission.id, users["staf"], None)
    await svc.approve(submission.id, users["sekdes"], None)
    await svc.approve(submission.id, users["kades"], None)
    with pytest.raises(ForbiddenError):
        await svc.download_pdf(submission.id, users["staf"].id, ["submission:download"])
