import re
from datetime import date

import pytest
from sqlalchemy import select

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.models.auth import Role, User
from app.models.submission import Submission
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
    # domisili's REQUIRED_EXTRA_FIELDS_BY_JENIS block (2026-08-08, Fase 1 of
    # ALUR_REVIEW_INPUT_MASTER.md) -- also needed for the tests in this file
    # that approve() all the way to issuance.
    submission.staff_extra_data = {
        "alamat_asal": "Kp. Lama", "rt_asal": "001", "rw_asal": "002",
        "kel_desa_asal": "Kopo", "kec_asal": "Kec. Uji", "kab_kota_asal": "Kab. Uji",
        "provinsi_asal": "Jawa Barat", "masa_berlaku_bulan": "6",
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


@pytest.mark.asyncio
async def test_update_extra_data_merges_by_sesi(seeded_session):
    template = await _make_template_with_fields(seeded_session)  # code="domisili"
    user = await _make_warga_user(seeded_session, "warga_extra")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        user, template.id, {"alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank"},
        "3516000000000888", "Warga Extra",
    )

    await svc.update_extra_data(submission.id, {"alamat_asal": "Kp. Lama", "rt_asal": "002"})
    await svc.update_extra_data(submission.id, {"masa_berlaku_bulan": "6 Bulan"})

    got = await svc.get_or_404(submission.id)
    assert got.staff_extra_data["alamat_asal"] == "Kp. Lama"
    assert got.staff_extra_data["rt_asal"] == "002"
    assert got.staff_extra_data["masa_berlaku_bulan"] == "6 Bulan"


@pytest.mark.asyncio
async def test_update_extra_data_rejects_jenis_without_extra_schema(seeded_session):
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "numbering_prefix": "500", "numbering_pattern": "{prefix}/{seq}/Ekonomi",
        "pdf_body_template": "<p></p>",
    })
    user = await _make_warga_user(seeded_session, "warga_sku")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {}, "3516000000000889", "Warga SKU")

    with pytest.raises(ValidationAppError):
        await svc.update_extra_data(submission.id, {"anything": "value"})


@pytest.mark.asyncio
async def test_update_extra_data_wraps_pydantic_error_as_validation_app_error(seeded_session):
    """Regression: update_extra_data() called schema_cls.model_validate(merged)
    with no try/except, so a raw pydantic.ValidationError (not one of this
    app's recognized exception types) fell through to a generic HTTP 500
    instead of a proper 400-style ValidationAppError. An 11-item 'anggota'
    list fails KKExtraData's _max_10_anggota field_validator (max 10)."""
    from pydantic import ValidationError as PydanticValidationError

    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "474", "numbering_pattern": "{prefix}/{seq}/Pem",
        "pdf_body_template": "<p></p>",
    })
    user = await _make_warga_user(seeded_session, "warga_kk_extra_bad")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {}, "3516000000000993", "Warga KK Extra Bad")

    too_many_anggota = [
        {"nik": f"351600000000{i:04d}", "nama": f"Anggota {i}", "jk": "Laki-laki"}
        for i in range(11)
    ]
    with pytest.raises(ValidationAppError):
        await svc.update_extra_data(submission.id, {"anggota": too_many_anggota})

    # Also confirm the raw pydantic exception no longer escapes the service.
    try:
        await svc.update_extra_data(submission.id, {"anggota": too_many_anggota})
    except PydanticValidationError:
        pytest.fail("raw pydantic.ValidationError leaked out of update_extra_data")
    except ValidationAppError:
        pass


@pytest.mark.asyncio
async def test_create_walkin_blocks_jenis_needing_staff_extra_data(seeded_session):
    """Regression / explicit user decision: create_walkin() issues via
    _issue() directly, never going through the staff_extra_data
    completeness gate that approve() enforces. Since Task 14 moved fields
    like domisili's masa_berlaku_bulan out of citizen answers, walk-ins for
    domisili/lahir/mati/na/kk could silently issue letters with missing
    data -- Mode Loket has no UI yet to collect staff_extra_data. These 5
    jenis are now blocked from Mode Loket with a clear error instead."""
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "domisili", "name": "Surat Domisili", "icon": "home_pin",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    })
    roles = {r.name: r for r in (await seeded_session.scalars(select(Role))).all()}
    staff = User(username="staff_walkin_blocked", full_name="Staff", hashed_password="x",
                 role_id=roles["staff"].id)
    seeded_session.add(staff)
    await seeded_session.flush()

    svc = SubmissionService(seeded_session)
    before_count = len((await seeded_session.scalars(select(Submission))).all())
    with pytest.raises(ValidationAppError):
        await svc.create_walkin(
            staff, template.id, "3516000000000700", "Warga Loket",
            {"alamat_tinggal_saat_ini": "Jl. Loket"},
        )
    # Blocked before any submission row is created.
    after_count = len((await seeded_session.scalars(select(Submission))).all())
    assert after_count == before_count


@pytest.mark.asyncio
async def test_create_walkin_still_works_for_unaffected_jenis(seeded_session):
    """SKU (usaha) has no staff_extra_data schema -- Mode Loket must keep
    working for it exactly as before this fix."""
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "numbering_prefix": "500", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "jenis_usaha", "label": "Jenis Usaha", "field_type": "text", "is_required": True,
    })
    roles = {r.name: r for r in (await seeded_session.scalars(select(Role))).all()}
    staff = User(username="staff_walkin_ok", full_name="Staff", hashed_password="x",
                 role_id=roles["staff"].id)
    seeded_session.add(staff)
    await seeded_session.flush()

    svc = SubmissionService(seeded_session)
    obj = await svc.create_walkin(
        staff, template.id, "3516000000000701", "Warga Loket SKU",
        {"jenis_usaha": "Warung"},
    )
    assert obj.status.value == "issued"


@pytest.mark.asyncio
async def test_get_master_data_schema_returns_sesi_and_anchors(seeded_session):
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "numbering_prefix": "472", "numbering_pattern": "{prefix}/{seq}/Pem",
        "pdf_body_template": "<p></p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "nama_almarhum", "label": "Nama Almarhum", "field_type": "text", "is_required": True,
    })
    await tsvc.add_field(template.id, {
        "field_key": "nik_almarhum", "label": "NIK Almarhum", "field_type": "text", "is_required": True,
    })
    user = await _make_warga_user(seeded_session, "warga_mati")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        user, template.id, {"nama_almarhum": "Almarhum A", "nik_almarhum": "3516000000000999"},
        "3516000000000998", "Pelapor",
    )

    schema = await svc.get_master_data_schema(submission.id)
    assert schema["jenis"] == "kematian"
    assert [s["key"] for s in schema["sesi"]] == ["almarhum"]
    assert schema["anchors"]["almarhum"]["nama"] == "Almarhum A"
    assert schema["anchors"]["almarhum"]["nik"] == "3516000000000999"


@pytest.mark.asyncio
async def test_get_master_data_schema_na_calon_anchor_falls_back_to_applicant(seeded_session):
    """NA's "calon" sesi has no dedicated nama/nik answer keys -- the
    _ANCHOR_ANSWER_KEYS entry is (None, None), meaning the anchor should
    read straight off the submission's own applicant_nama/applicant_nik
    instead of trying answers.get(None)."""
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "na", "name": "Numpang Nikah", "icon": "favorite",
        "color_bg": "#FDEDF3", "color_fg": "#B23A6B",
        "numbering_prefix": "474", "numbering_pattern": "{prefix}/{seq}/Kua",
        "pdf_body_template": "<p></p>",
    })
    user = await _make_warga_user(seeded_session, "warga_na")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(
        user, template.id, {}, "3516000000000777", "Calon Pengantin",
    )

    schema = await svc.get_master_data_schema(submission.id)
    assert schema["jenis"] == "na"
    assert schema["anchors"]["calon"]["nama"] == submission.applicant_nama
    assert schema["anchors"]["calon"]["nik"] == submission.applicant_nik


@pytest.mark.asyncio
async def test_get_missing_staff_fields_includes_extra_data(seeded_session):
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "numbering_prefix": "472", "numbering_pattern": "{prefix}/{seq}/Pem",
        "pdf_body_template": "<p></p>",
    })
    user = await _make_warga_user(seeded_session, "warga_missing")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {}, "3516000000000997", "Warga Missing")

    missing = await svc.get_missing_staff_fields(submission)
    assert "Jenis Kelamin (Data Master)" in missing
    assert "Alamat (Data Master)" in missing

    submission.staff_extra_data = {
        "jk": "Laki-laki", "pekerjaan": "Petani", "alamat": "Kp. X", "rt": "001", "rw": "002",
    }
    await seeded_session.flush()
    still_missing = await svc.get_missing_staff_fields(submission)
    assert "Jenis Kelamin (Data Master)" not in still_missing


@pytest.mark.asyncio
async def test_get_missing_staff_fields_kk_requires_one_complete_anggota(seeded_session):
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "474", "numbering_pattern": "{prefix}/{seq}/Pem",
        "pdf_body_template": "<p></p>",
    })
    user = await _make_warga_user(seeded_session, "warga_kk_missing")
    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {}, "3516000000000996", "Warga KK")

    missing = await svc.get_missing_staff_fields(submission)
    assert "Data Anggota Keluarga (minimal 1 anggota)" in missing

    submission.staff_extra_data = {
        "nama_kk": "Budi", "dusun": "Dusun 1",
        "anggota": [{"nik": "3516000000000995", "nama": "Budi", "jk": "Laki-laki"}],
    }
    await seeded_session.flush()
    still_missing = await svc.get_missing_staff_fields(submission)
    assert "Data Anggota Keluarga (minimal 1 anggota)" not in still_missing


async def _approve_to_issued(svc, submission, staff_user):
    """Advance a PENDING submission through both approval steps."""
    await svc.approve(submission.id, staff_user, "ok")
    return await svc.approve(submission.id, staff_user, "signed")


@pytest.mark.asyncio
async def test_domisili_master_row_reads_alamat_asal_from_extra_data(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.master import MasterDomisili

    svc, submission, users = await _setup_pending_submission(seeded_session)
    submission.staff_extra_data = {
        "alamat_asal": "Kp. Lama", "rt_asal": "002", "rw_asal": "004",
        "kel_desa_asal": "Citeko", "kec_asal": "Cisarua", "kab_kota_asal": "Bogor",
        "provinsi_asal": "Jawa Barat", "masa_berlaku_bulan": "3 Bulan",
    }
    await seeded_session.flush()

    await _approve_to_issued(svc, submission, users["staff"])

    row = (await seeded_session.scalars(
        sa_select(MasterDomisili).where(MasterDomisili.submission_id == submission.id)
    )).first()
    assert row.almt_asal == "Kp. Lama"
    assert row.rt_asal == "002"
    assert row.provinsi_asal == "Jawa Barat"
    assert row.berlaku is not None


@pytest.mark.asyncio
async def test_domisili_issued_pdf_shows_real_berlaku_date_not_blank(seeded_session):
    """Regression: _issue() computed berlaku_date from
    render_answers.get('masa_berlaku_bulan') -- the citizen's own `answers`
    dict, which no longer contains this key at all since Task 14 moved it
    into staff_extra_data. That silently rendered a blank
    'Berlaku Sampai Dengan Tanggal : -' on every issued Domisili letter,
    even though _save_to_domain_master's MasterDomisili.berlaku column
    (checked by test_domisili_master_row_reads_alamat_asal_from_extra_data)
    was already correct -- that DB-only assertion is exactly why this bug
    slipped through review, so this test asserts on the actual rendered PDF
    text instead."""
    import io

    import pypdf

    svc, submission, users = await _setup_pending_submission(seeded_session)
    template = await svc.template_repo.get(submission.template_id)
    template.pdf_body_template = (
        "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>"
        "<p>Berlaku Sampai Dengan Tanggal : {{ berlaku }}</p>"
    )
    submission.staff_extra_data = {
        **submission.staff_extra_data,
        "masa_berlaku_bulan": "3 Bulan",
    }
    await seeded_session.flush()

    await _approve_to_issued(svc, submission, users["staff"])

    pdf_bytes = await svc.download_pdf(submission.id, users["warga"].id, ["submission:download"])
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    text = "\n".join(page.extract_text() or "" for page in reader.pages)

    assert "Berlaku Sampai Dengan Tanggal : -" not in text
    assert re.search(r"Berlaku Sampai Dengan Tanggal\s*:\s*\d{1,2} \w+ \d{4}", text), text


async def _setup_pending_na_submission(session):
    """Same shape as _setup_pending_submission but code='na', with the
    citizen-anchor answers (nama_ayah/nik_ayah/nama_ibu/nik_ibu/nama_
    pasangan/nik_pasangan/status_calon) already filled."""
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "code": "na", "name": "Pengantar Nikah (NA)", "icon": "favorite",
        "color_bg": "#FFF4EC", "color_fg": "#E06D20",
        "numbering_prefix": "474.2", "numbering_pattern": "{prefix}/{seq}/Kesra",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "status_calon", "label": "Status", "field_type": "select",
        "options": ["Jejaka", "Perawan"], "is_required": True,
    })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    warga = User(username="warga_na", full_name="Warga NA", hashed_password="x", role_id=roles["warga"].id)
    staff = User(username="staff_na", full_name="Staff NA", hashed_password="x", role_id=roles["staff"].id)
    session.add_all([warga, staff])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(
        warga, template.id, {
            "status_calon": "Jejaka", "nama_ayah": "Ayah Calon", "nik_ayah": "3516000000000111",
            "nama_ibu": "Ibu Calon", "nik_ibu": "3516000000000112",
            "nama_pasangan": "Calon Pasangan", "nik_pasangan": "3516000000000113",
        }, "3516000000000110", "Calon NA",
    )
    submission.staff_extra_data = {
        "calon": {
            "jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "1998-01-01",
            "kewarganegaraan": "Indonesia", "agama": "Islam", "pekerjaan": "Karyawan",
            "alamat": "Kp. A", "rt": "001", "rw": "002",
        },
        "ayah": {"tempat_lahir": "Bogor", "tanggal_lahir": "1970-01-01", "pekerjaan": "Petani",
                  "alamat": "Kp. A", "rt": "001", "rw": "002", "kel_desa": "Kopo", "kec": "Cisarua", "kab_kota": "Bogor"},
        "ibu": {"tempat_lahir": "Bogor", "tanggal_lahir": "1975-01-01", "pekerjaan": "IRT",
                 "alamat": "Kp. A", "rt": "001", "rw": "002", "kel_desa": "Kopo", "kec": "Cisarua", "kab_kota": "Bogor"},
        "csi": {"bin_binti": "Binti Ayah", "jk": "Perempuan", "ttl": "Bogor, 1999", "agama": "Islam",
                 "pekerjaan": "Karyawan", "alamat": "Kp. B", "rt": "003", "rw": "004",
                 "kel_desa": "Sukasirna", "kec": "Cibadak", "kab_kota": "Sukabumi", "provinsi": "Jawa Barat", "shdk": "-"},
    }
    await session.flush()
    return svc, submission, {"warga": warga, "staff": staff}


@pytest.mark.asyncio
async def test_na_master_row_reads_ayah_ibu_csi_from_extra_data(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.master import MasterNA

    svc, submission, users = await _setup_pending_na_submission(seeded_session)
    await _approve_to_issued(svc, submission, users["staff"])

    row = (await seeded_session.scalars(
        sa_select(MasterNA).where(MasterNA.submission_id == submission.id)
    )).first()
    assert row.pkj_ayah == "Petani"
    assert row.kelurahan_atau_desa_ayah == "Kopo"
    assert row.almt_csi == "Kp. B"
    assert row.provinsi_csi == "Jawa Barat"
    assert row.ayah == "Ayah Calon"  # anchor, still from answers


async def _setup_pending_kk_submission(session):
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "474", "numbering_pattern": "{prefix}/{seq}/Pem",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "status_perubahan", "label": "Status Perubahan", "field_type": "select",
        "options": ["Baru Menikah (Pecah KK Mandiri)"], "is_required": True,
    })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    warga = User(username="warga_kk", full_name="Warga KK", hashed_password="x", role_id=roles["warga"].id)
    staff = User(username="staff_kk", full_name="Staff KK", hashed_password="x", role_id=roles["staff"].id)
    session.add_all([warga, staff])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(
        warga, template.id, {"status_perubahan": "Baru Menikah (Pecah KK Mandiri)"},
        "3516000000000200", "Kepala Keluarga",
    )
    # REQUIRED_STAFF_FIELDS_BY_JENIS["kk"] needs rt_id too -- a real FK, so
    # a real RT/RW row is required (not just any UUID).
    from app.models.master import RT, RW
    rw = RW(number="005")
    session.add(rw)
    await session.flush()
    rt = RT(rw_id=rw.id, number="003")
    session.add(rt)
    await session.flush()
    submission.staff_master_data = {
        "alamat": "Kp. KK", "no_kk": "3516000000000001", "rt_id": str(rt.id),
        "jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "1985-05-05",
        "status_kawin": "Kawin",
    }
    submission.staff_extra_data = {
        "nama_kk": "Kepala Keluarga", "dusun": "Dusun 2",
        "anggota": [
            {"nik": "3516000000000200", "nama": "Kepala Keluarga", "jk": "Laki-laki",
             "tempat_lahir": "Bogor", "tanggal_lahir": "1985-05-05", "agama": "Islam",
             "pendidikan": "SMA", "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
             "shdk": "Kepala Keluarga", "wni_wna": "WNI"},
            {"nik": "3516000000000201", "nama": "Istri Kepala Keluarga", "jk": "Perempuan",
             "tempat_lahir": "Bogor", "tanggal_lahir": "1987-06-06", "agama": "Islam",
             "pendidikan": "SMA", "pekerjaan": "IRT", "status_kawin": "Kawin",
             "shdk": "Istri", "wni_wna": "WNI"},
        ],
        "nama_ayah": "Ayah Kepala Keluarga", "nama_ibu": "Ibu Kepala Keluarga",
    }
    await session.flush()
    return svc, submission, {"warga": warga, "staff": staff}


@pytest.mark.asyncio
async def test_kk_master_row_populates_anggota_from_extra_data(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.master import MasterKK

    svc, submission, users = await _setup_pending_kk_submission(seeded_session)
    await _approve_to_issued(svc, submission, users["staff"])

    row = (await seeded_session.scalars(
        sa_select(MasterKK).where(MasterKK.submission_id == submission.id)
    )).first()
    assert row.nama_kk == "Kepala Keluarga"
    assert row.dusun == "Dusun 2"
    assert row.nama1 == "Kepala Keluarga"
    assert row.nik1 == "3516000000000200"
    assert row.nama2 == "Istri Kepala Keluarga"
    assert row.shdk2 == "Istri"
    assert row.namaAyah1 == "Ayah Kepala Keluarga"
    assert row.namaIbu1 == "Ibu Kepala Keluarga"
    assert row.nama3 is None


@pytest.mark.asyncio
async def test_kk_approve_no_longer_blocked_by_stale_generic_fields(seeded_session):
    """Regression: REQUIRED_STAFF_FIELDS_BY_JENIS['kk'] used to require
    jk/tempat_lahir/tanggal_lahir/status_kawin even though Task 12 rewired
    the kk branch of _save_to_domain_master to source member #1 from
    staff_extra_data's anggota array, not these generic applicant.get(...)
    keys -- forcing staff to redundantly re-enter data already captured in
    the anggota sesi. Only alamat/rt_id/no_kk are genuinely still read by
    the kk branch, so a submission missing the 4 stale fields (but with a
    complete anggota row) must no longer be blocked."""
    svc, submission, users = await _setup_pending_kk_submission(seeded_session)
    submission.staff_master_data = {
        "alamat": "Kp. KK", "no_kk": "3516000000000001",
        "rt_id": submission.staff_master_data["rt_id"],
    }
    await seeded_session.flush()

    missing = await svc.get_missing_staff_fields(submission)
    assert "Jenis Kelamin (Data Master)" not in missing
    assert "Tempat Lahir (Data Master)" not in missing
    assert "Tanggal Lahir (Data Master)" not in missing
    assert "Status Kawin (Data Master)" not in missing
    assert missing == []

    issued = await _approve_to_issued(svc, submission, users["staff"])
    assert issued.status.value == "issued"


@pytest.mark.asyncio
async def test_kk_approve_still_blocked_when_no_kk_missing(seeded_session):
    """The under-blocking half of the fix: no_kk IS genuinely read by the kk
    branch (applicant.get('no_kk')) but was missing from
    REQUIRED_STAFF_FIELDS_BY_JENIS['kk'] before this fix. It must now
    correctly block Approve when absent."""
    svc, submission, users = await _setup_pending_kk_submission(seeded_session)
    submission.staff_master_data = {
        "alamat": "Kp. KK", "rt_id": submission.staff_master_data["rt_id"],
        # no_kk deliberately omitted
    }
    await seeded_session.flush()

    missing = await svc.get_missing_staff_fields(submission)
    assert "No. KK (Data Master)" in missing

    with pytest.raises(ValidationAppError):
        await svc.approve(submission.id, users["staff"], "ok")


async def _setup_pending_uhc_submission(session):
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "code": "uhc", "name": "Surat Keterangan Tidak Mampu (SKTM)", "icon": "volunteer_activism",
        "color_bg": "#EAFBF4", "color_fg": "#108050",
        "numbering_prefix": "440", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    for key, label in [("no_kk", "No. KK"), ("tgl_dikeluarkan_kk", "Tgl KK"),
                        ("tanggal_pengantar_rt", "Tgl Pengantar RT"), ("keperluan", "Keperluan")]:
        field_type = "date" if key.startswith("tgl") or key.startswith("tanggal") else "text"
        await tsvc.add_field(template.id, {
            "field_key": key, "label": label, "field_type": field_type, "is_required": True,
        })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    warga = User(username="warga_uhc", full_name="Warga UHC", hashed_password="x", role_id=roles["warga"].id)
    staff = User(username="staff_uhc", full_name="Staff UHC", hashed_password="x", role_id=roles["staff"].id)
    session.add_all([warga, staff])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(
        warga, template.id, {
            "no_kk": "3516000000000300", "tgl_dikeluarkan_kk": "2020-01-01",
            "tanggal_pengantar_rt": "2026-08-01", "keperluan": "Keringanan biaya rumah sakit",
        }, "3516000000000301", "Pemohon SKTM",
    )
    # REQUIRED_STAFF_FIELDS_BY_JENIS["uhc"] needs rt_id too -- a real FK.
    from app.models.master import RT, RW
    rw = RW(number="006")
    session.add(rw)
    await session.flush()
    rt = RT(rw_id=rw.id, number="004")
    session.add(rt)
    await session.flush()
    submission.staff_master_data = {
        "jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "1990-01-01",
        "pekerjaan": "Buruh", "status_kawin": "Kawin", "alamat": "Kp. SKTM",
        "no_kk": "3516000000000300", "rt_id": str(rt.id),
    }
    await session.flush()
    return svc, submission, {"warga": warga, "staff": staff}


@pytest.mark.asyncio
async def test_uhc_master_row_saves_keperluan_and_pengantar_rt(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.master import MasterUHC

    svc, submission, users = await _setup_pending_uhc_submission(seeded_session)
    await _approve_to_issued(svc, submission, users["staff"])

    row = (await seeded_session.scalars(
        sa_select(MasterUHC).where(MasterUHC.submission_id == submission.id)
    )).first()
    assert row.keperluan == "Keringanan biaya rumah sakit"
    assert row.tanggal_pengantar_rt is not None
    assert row.nama_pasien == "Pemohon SKTM"
    assert row.nama_kepala_keluarga is None
    assert row.peruntukan is None


@pytest.mark.asyncio
async def test_seed_domisili_no_longer_asks_alamat_asal_or_masa_berlaku(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.letter_template import LetterTemplate, TemplateField
    from app.seed.seed import seed_letter_templates

    # seeded_session only seeds positions/RBAC, not letter templates --
    # seed those explicitly here to exercise the real SURAT_TEMPLATES data.
    await seed_letter_templates(seeded_session)

    template = (await seeded_session.scalars(
        sa_select(LetterTemplate).where(LetterTemplate.code == "domisili")
    )).first()
    fields = (await seeded_session.scalars(
        sa_select(TemplateField).where(TemplateField.template_id == template.id)
    )).all()
    keys = {f.field_key for f in fields}
    assert "alamat_asal" not in keys
    assert "masa_berlaku_bulan" not in keys
    assert "alamat_domisili" in keys  # stays citizen-input


@pytest.mark.asyncio
async def test_seed_mati_no_longer_asks_jk_or_pekerjaan_almarhum(seeded_session):
    from sqlalchemy import select as sa_select
    from app.models.letter_template import LetterTemplate, TemplateField
    from app.seed.seed import seed_letter_templates

    # seeded_session only seeds positions/RBAC, not letter templates --
    # seed those explicitly here to exercise the real SURAT_TEMPLATES data.
    await seed_letter_templates(seeded_session)

    template = (await seeded_session.scalars(
        sa_select(LetterTemplate).where(LetterTemplate.code == "mati")
    )).first()
    fields = (await seeded_session.scalars(
        sa_select(TemplateField).where(TemplateField.template_id == template.id)
    )).all()
    keys = {f.field_key for f in fields}
    assert "jk_almarhum" not in keys
    assert "pekerjaan_almarhum" not in keys
    assert "nama_almarhum" in keys  # anchor, stays
    assert "sebab_meninggal" in keys  # event knowledge, stays
