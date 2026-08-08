from datetime import date

import pytest
from sqlalchemy import select

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.models.auth import Role, User
from app.services.letter_template import LetterTemplateService
from app.services.submission import SubmissionService


async def _make_template_with_fields(session):
    svc = LetterTemplateService(session)
    template = await svc.create({
        "code": "domisili", "name": "Surat Domisili",
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
    template = await _make_template_with_fields(seeded_session)
    user = await _make_warga_user(seeded_session, "warga_test")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(
            user, template.id, {"alamat_tinggal_saat_ini": ""},  # missing keperluan
            "3516000000000001", "Warga Test",
        )


@pytest.mark.asyncio
async def test_create_validates_select_options(seeded_session):
    template = await _make_template_with_fields(seeded_session)
    user = await _make_warga_user(seeded_session, "warga_test2")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {
            "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "NotAnOption",
        }, "3516000000000002", "Warga Test")


@pytest.mark.asyncio
async def test_create_succeeds_with_valid_answers(seeded_session):
    template = await _make_template_with_fields(seeded_session)
    user = await _make_warga_user(seeded_session, "warga_test3")

    svc = SubmissionService(seeded_session)
    obj = await svc.create(user, template.id, {
        "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank",
    }, "3516000000000003", "Warga Test")
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
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p></p>", "required_documents": ["KTP"],
    })
    user = await _make_warga_user(seeded_session, "warga_att")

    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {}, "3516000000000004", "Warga Test")

    with pytest.raises(ValidationAppError):
        await svc.add_attachment(
            submission.id, "Bukan Dokumen Wajib", "x.png", b"abc", "image/png", user.id
        )

    att = await svc.add_attachment(submission.id, "KTP", "ktp.png", b"abc", "image/png", user.id)
    assert att.document_label == "KTP"
    assert att.original_filename == "ktp.png"

    other_user = await _make_warga_user(seeded_session, "warga_att_intruder")
    with pytest.raises(ForbiddenError):
        await svc.add_attachment(
            submission.id, "KTP", "ktp.png", b"abc", "image/png", other_user.id
        )


async def _setup_pending_submission(session):
    """A letter template + one PENDING submission.

    The village identity used by the final approval step's PDF issuance
    (VillageProfileService.get()) is hardcoded, not seeded (see
    app.models.master.VillageProfile's docstring).

    The approval chain is a fixed `SubmissionService.APPROVAL_STEP_COUNT`-
    step sequence with no per-step role gating -- anyone holding
    submission:approve may act at any step (see approve()'s docstring).
    """
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    warga = User(username="warga_flow", full_name="Warga Flow", hashed_password="x",
                 role_id=roles["warga"].id)
    staff = User(username="staff_flow", full_name="Staff Flow", hashed_password="x",
                 role_id=roles["staff"].id)
    admin = User(username="admin_flow", full_name="Admin Flow", hashed_password="x",
                 role_id=roles["admin"].id)
    session.add_all([warga, staff, admin])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(
        warga, template.id, {"alamat_tinggal_saat_ini": "Jl. Uji 1"},
        "3516000000000099", "Warga Flow",
    )
    # domisili's REQUIRED_STAFF_FIELDS_BY_JENIS block (2026-08-06) -- needed
    # for the tests in this file that approve() all the way to issuance.
    submission.staff_master_data = {
        "jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "1990-01-01",
        "pekerjaan": "Petani", "status_kawin": "Kawin",
    }
    await session.flush()
    return svc, submission, {"warga": warga, "staff": staff, "admin": admin}


@pytest.mark.asyncio
async def test_approve_out_of_turn_still_succeeds(seeded_session):
    """No per-step role gating: admin may approve the first step directly
    (previously "staff's turn"), advancing the chain like anyone else with
    submission:approve."""
    svc, submission, users = await _setup_pending_submission(seeded_session)
    advanced = await svc.approve(submission.id, users["admin"], None)
    assert advanced.current_step_index == 1
    assert advanced.status.value == "pending"


@pytest.mark.asyncio
async def test_approve_same_actor_completes_full_chain(seeded_session):
    """A single actor (e.g. staff) may call approve() through every step to
    issuance without waiting for a different role -- the chain no longer
    restricts who may act at each step."""
    svc, submission, users = await _setup_pending_submission(seeded_session)
    await svc.approve(submission.id, users["staff"], "ok")
    issued = await svc.approve(submission.id, users["staff"], "signed")
    assert issued.status.value == "issued"
    # Left blank -- no automatic numbering (see SubmissionService._issue's
    # docstring); staff fill it in by hand at the desa office.
    assert issued.letter_number is None


@pytest.mark.asyncio
async def test_approve_full_chain_issues_pdf(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)

    s1 = await svc.approve(submission.id, users["staff"], "ok")
    assert s1.current_step_index == 1
    assert s1.status.value == "pending"

    s2 = await svc.approve(submission.id, users["admin"], "signed")
    assert s2.status.value == "issued"
    assert s2.letter_number is None
    assert s2.pdf_storage_path is not None
    assert s2.issued_at is not None

    pdf_bytes = await svc.download_pdf(submission.id, users["warga"].id, ["submission:download"])
    assert pdf_bytes[:5] == b"%PDF-"

    history = await svc.list_history(submission.id)
    actions = [h.action.value for h in history]
    assert actions == ["submitted", "approved", "issued"]


@pytest.mark.asyncio
async def test_reject_is_terminal(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    rejected = await svc.reject(submission.id, users["staff"], "Berkas tidak lengkap")
    assert rejected.status.value == "rejected"
    assert rejected.rejection_reason == "Berkas tidak lengkap"
    with pytest.raises(ValidationAppError):
        await svc.approve(submission.id, users["staff"], None)


@pytest.mark.asyncio
async def test_get_scoped_rejects_non_owner_without_read_all(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    other_warga = await _make_warga_user(seeded_session, "warga_intruder")
    with pytest.raises(ForbiddenError):
        await svc.get_scoped(submission.id, other_warga.id, ["submission:read"])


@pytest.mark.asyncio
async def test_get_scoped_allows_owner_and_read_all(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    owner_got = await svc.get_scoped(submission.id, users["warga"].id, ["submission:read"])
    assert owner_got.id == submission.id

    staff_got = await svc.get_scoped(
        submission.id, users["staff"].id, ["submission:read", "submission:read_all"]
    )
    assert staff_got.id == submission.id


@pytest.mark.asyncio
async def test_download_pdf_rejects_non_owner_without_read_all(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    await svc.approve(submission.id, users["staff"], None)
    await svc.approve(submission.id, users["admin"], None)
    with pytest.raises(ForbiddenError):
        await svc.download_pdf(submission.id, users["staff"].id, ["submission:download"])


@pytest.mark.asyncio
async def test_master_uhc_has_keperluan_and_pengantar_rt_columns(seeded_session):
    from app.models.master import MasterUHC
    row = MasterUHC(
        nama_pasien="Test", nik_pasien="3516000000000123",
        keperluan="Keringanan biaya rumah sakit",
        tanggal_pengantar_rt=date(2026, 8, 1),
    )
    seeded_session.add(row)
    await seeded_session.flush()
    assert row.keperluan == "Keringanan biaya rumah sakit"
    assert row.tanggal_pengantar_rt == date(2026, 8, 1)


@pytest.mark.asyncio
async def test_build_applicant_snapshot_includes_flattened_extra_data(seeded_session):
    template = await _make_template_with_fields(seeded_session)  # code="domisili"
    user = await _make_warga_user(seeded_session, "warga_snapshot")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        user, template.id, {"alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank"},
        "3516000000000777", "Warga Snapshot",
    )
    submission.staff_extra_data = {"alamat_asal": "Kp. Lama", "rt_asal": "002", "masa_berlaku_bulan": "3 Bulan"}
    await seeded_session.flush()

    snapshot = await svc.build_applicant_snapshot(submission)
    assert snapshot["alamat_asal"] == "Kp. Lama"
    assert snapshot["rt_asal"] == "002"
    assert snapshot["masa_berlaku_bulan"] == "3 Bulan"
    # Existing generic keys still present and unaffected.
    assert snapshot["nama"] == "Warga Snapshot"


@pytest.mark.asyncio
async def test_build_applicant_snapshot_handles_no_extra_data(seeded_session):
    template = await _make_template_with_fields(seeded_session)
    user = await _make_warga_user(seeded_session, "warga_snapshot2")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        user, template.id, {"alamat_tinggal_saat_ini": "Jl. B", "keperluan": "Bank"},
        "3516000000000778", "Warga Snapshot 2",
    )
    snapshot = await svc.build_applicant_snapshot(submission)
    assert snapshot.get("alamat_asal") is None
