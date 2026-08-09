from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.auth import Role, User
from app.services.template_render import format_tanggal_indonesia


async def _token(client, identifier, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


async def _setup_village_template_workflow(client, db_session):
    """Seed a letter template.

    The village identity used by the final approval step's PDF issuance
    (VillageProfileService.get()) is hardcoded, not seeded (see
    app.models.master.VillageProfile's docstring). The approval chain
    itself is a fixed 2-step sequence (SubmissionService.APPROVAL_STEP_COUNT),
    not configured per-test.
    """
    admin_tok = await _token(client, "operator", "operator123")
    h = {"Authorization": f"Bearer {admin_tok}"}

    template = await client.post("/api/v1/templates", json={
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>",
        "required_documents": ["KTP"],
    }, headers=h)
    template_id = template.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    }, headers=h)
    return template_id


@pytest.mark.asyncio
async def test_full_submission_lifecycle_via_api(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
        })(),
    )
    template_id = await _setup_village_template_workflow(client, db_session)

    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji 99"},
        "applicant_nik": "3516000000000101", "applicant_nama": "Warga Uji",
    }, headers=wh)
    assert created.status_code == 200
    submission_id = created.json()["data"]["id"]

    mine = await client.get("/api/v1/submissions", headers=wh)
    assert mine.json()["data"]["total"] == 1

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}

    # 2026-08-06: staff fills the shared identity block (from KTP/KK photos)
    # before its own approve() -- domisili's REQUIRED_STAFF_FIELDS_BY_JENIS is
    # checked on every approve() call, not just the final one (blocking,
    # SubmissionService.get_missing_staff_fields), and "staff" is the role
    # that both holds submission:edit_master_data and owns the first step.
    master_data = await client.put(
        f"/api/v1/submissions/{submission_id}/master-data",
        json={
            "jk": "Perempuan", "tempat_lahir": "Bogor", "tanggal_lahir": "1990-01-01",
            "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
        },
        headers=sh,
    )
    assert master_data.status_code == 200

    # 2026-08-08 (Fase 1 of ALUR_REVIEW_INPUT_MASTER.md): domisili's
    # REQUIRED_EXTRA_FIELDS_BY_JENIS block (the letter-specific "alamat
    # asal" sesi) is now also checked on every approve() call, same as the
    # master-data block above.
    extra_data = await client.put(
        f"/api/v1/submissions/{submission_id}/extra-data",
        json={
            "alamat_asal": "Kp. Lama", "rt_asal": "001", "rw_asal": "002",
            "kel_desa_asal": "Kopo", "kec_asal": "Kec. Uji", "kab_kota_asal": "Kab. Uji",
            "provinsi_asal": "Jawa Barat", "masa_berlaku_bulan": "6",
        },
        headers=sh,
    )
    assert extra_data.status_code == 200

    approve1 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "ok"}, headers=sh
    )
    assert approve1.status_code == 200
    assert approve1.json()["data"]["status"] == "pending"

    # 2026-08-05: Kepala Desa (kades) can no longer approve/reject at all
    # (HASIL_UJICOBA_PERROLE.md kades item 2) -- only Sekretaris Desa
    # (sekdes) holds submission:approve within the "admin" Role now.
    sekdes_tok = await _token(client, "sekdes", "sekdes123")
    kh = {"Authorization": f"Bearer {sekdes_tok}"}
    approve2 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "signed"}, headers=kh
    )
    assert approve2.status_code == 200
    body = approve2.json()["data"]
    assert body["status"] == "issued"
    # Left blank -- no automatic numbering, staff fill it in by hand at the
    # desa office (see SubmissionService._issue's docstring).
    assert body["letter_number"] is None

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=wh)
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"

    history = await client.get(f"/api/v1/submissions/{submission_id}/history", headers=wh)
    assert [h["action"] for h in history.json()["data"]] == ["submitted", "approved", "issued"]


@pytest.mark.asyncio
async def test_approve_wrong_turn_returns_403(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji"},
        "applicant_nik": "3516000000000102", "applicant_nama": "Warga Uji",
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    kades_tok = await _token(client, "kades", "kades123")  # staff's turn, not admin
    resp = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={},
        headers={"Authorization": f"Bearer {kades_tok}"},
    )
    assert resp.status_code == 403


async def _create_second_warga(db_session, username: str = "warga2") -> None:
    """Insert a second warga-role user directly, so two distinct citizens exist."""
    role = (await db_session.scalars(select(Role).where(Role.name == "warga"))).first()
    db_session.add(User(
        username=username, full_name="Warga Kedua",
        hashed_password=hash_password("warga2pass"), role_id=role.id, is_active=True,
    ))
    await db_session.commit()


@pytest.mark.asyncio
async def test_get_submission_rejects_non_owner(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    await _create_second_warga(db_session)

    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji 1"},
        "applicant_nik": "3516000000000103", "applicant_nama": "Warga Uji",
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    # Owner can read their own submission.
    own = await client.get(
        f"/api/v1/submissions/{submission_id}", headers={"Authorization": f"Bearer {warga_tok}"}
    )
    assert own.status_code == 200

    # A different citizen must NOT be able to read it.
    warga2_tok = await _token(client, "warga2", "warga2pass")
    resp = await client.get(
        f"/api/v1/submissions/{submission_id}", headers={"Authorization": f"Bearer {warga2_tok}"}
    )
    assert resp.status_code == 403

    # Staff (submission:read_all) must still be able to read it.
    staf_tok = await _token(client, "staf", "staf123")
    staff_resp = await client.get(
        f"/api/v1/submissions/{submission_id}", headers={"Authorization": f"Bearer {staf_tok}"}
    )
    assert staff_resp.status_code == 200


@pytest.mark.asyncio
async def test_get_submission_history_rejects_non_owner(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    await _create_second_warga(db_session)

    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji 2"},
        "applicant_nik": "3516000000000104", "applicant_nama": "Warga Uji",
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    warga2_tok = await _token(client, "warga2", "warga2pass")
    resp = await client.get(
        f"/api/v1/submissions/{submission_id}/history",
        headers={"Authorization": f"Bearer {warga2_tok}"},
    )
    assert resp.status_code == 403

    # Staff (submission:read_all) must still be able to read the history.
    staf_tok = await _token(client, "staf", "staf123")
    staff_resp = await client.get(
        f"/api/v1/submissions/{submission_id}/history",
        headers={"Authorization": f"Bearer {staf_tok}"},
    )
    assert staff_resp.status_code == 200


@pytest.mark.asyncio
async def test_upload_attachment_rejects_non_owner(client, db_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
        })(),
    )
    template_id = await _setup_village_template_workflow(client, db_session)
    await _create_second_warga(db_session)

    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji 3"},
        "applicant_nik": "3516000000000105", "applicant_nama": "Warga Uji",
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    warga2_tok = await _token(client, "warga2", "warga2pass")
    resp = await client.post(
        f"/api/v1/submissions/{submission_id}/attachments",
        data={"document_label": "KTP"},
        files={"file": ("ktp.png", b"fake-bytes", "image/png")},
        headers={"Authorization": f"Bearer {warga2_tok}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_get_preview_html_shows_real_data_and_updates_after_edit(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Pertama"},
        "applicant_nik": "3516000000000102", "applicant_nama": "Warga Preview",
    }, headers=wh)
    submission_id = created.json()["data"]["id"]

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}

    preview1 = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=sh)
    assert preview1.status_code == 200
    html1 = preview1.json()["data"]["html"]
    assert "Warga Preview" in html1
    assert "Jl. Pertama" in html1

    updated = await client.put(
        f"/api/v1/submissions/{submission_id}/answers",
        json={"answers": {"alamat_tinggal_saat_ini": "Jl. Sudah Diedit"}},
        headers=sh,
    )
    assert updated.status_code == 200

    preview2 = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=sh)
    html2 = preview2.json()["data"]["html"]
    assert "Jl. Sudah Diedit" in html2
    assert "Jl. Pertama" not in html2


@pytest.mark.asyncio
async def test_get_preview_html_requires_submission_approve_permission(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji"},
        "applicant_nik": "3516000000000103", "applicant_nama": "Warga Uji Izin",
    }, headers=wh)
    submission_id = created.json()["data"]["id"]

    forbidden = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=wh)
    assert forbidden.status_code == 403


@pytest.mark.asyncio
async def test_get_preview_html_blocked_after_rejection(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Ditolak"},
        "applicant_nik": "3516000000000104", "applicant_nama": "Warga Ditolak",
    }, headers=wh)
    submission_id = created.json()["data"]["id"]

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}
    rejected = await client.post(
        f"/api/v1/submissions/{submission_id}/reject", json={"reason": "tidak lengkap"}, headers=sh
    )
    assert rejected.status_code == 200

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=sh)
    # ValidationAppError maps to 422 in this codebase (app/core/exceptions.py),
    # not 400 -- matches every other ValidationAppError raise site.
    assert preview.status_code == 422


@pytest.mark.asyncio
async def test_get_preview_html_for_issued_submission_anchors_to_issued_at_not_now(
    client, db_session, monkeypatch, tmp_path
):
    """Once a submission is ISSUED, the preview's date must match the
    already-issued PDF (anchored to `issued_at`), not drift forward with
    wall-clock "now" every time staff reopen the page -- same reasoning as
    `regenerate_pdf()`.

    Proven structurally: after issuance, `datetime.now` inside the service
    module is monkeypatched to a clearly-different fake moment (year 2099)
    and the preview is fetched again. If the code still read wall-clock
    "now" the rendered date would show the fake year; it must instead keep
    showing the real `issued_at` date from the approve response.
    """
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
        })(),
    )
    template_id = await _setup_village_template_workflow(client, db_session)

    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Terbit"},
        "applicant_nik": "3516000000000106", "applicant_nama": "Warga Terbit",
    }, headers=wh)
    submission_id = created.json()["data"]["id"]

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}
    await client.put(
        f"/api/v1/submissions/{submission_id}/master-data",
        json={
            "jk": "Perempuan", "tempat_lahir": "Bogor", "tanggal_lahir": "1990-01-01",
            "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
        },
        headers=sh,
    )
    await client.put(
        f"/api/v1/submissions/{submission_id}/extra-data",
        json={
            "alamat_asal": "Kp. Lama", "rt_asal": "001", "rw_asal": "002",
            "kel_desa_asal": "Kopo", "kec_asal": "Kec. Uji", "kab_kota_asal": "Kab. Uji",
            "provinsi_asal": "Jawa Barat", "masa_berlaku_bulan": "6",
        },
        headers=sh,
    )
    approve1 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "ok"}, headers=sh
    )
    assert approve1.status_code == 200

    sekdes_tok = await _token(client, "sekdes", "sekdes123")
    kh = {"Authorization": f"Bearer {sekdes_tok}"}
    approve2 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "signed"}, headers=kh
    )
    assert approve2.status_code == 200
    body = approve2.json()["data"]
    assert body["status"] == "issued"
    issued_at = datetime.fromisoformat(body["issued_at"])
    expected_tanggal = format_tanggal_indonesia(issued_at)

    # A fake "now" far in the future -- if get_preview_html still anchored
    # to wall-clock now() for ISSUED submissions, this is what would show up.
    fake_now = datetime(2099, 1, 1, tzinfo=timezone.utc)

    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return fake_now

    monkeypatch.setattr("app.services.submission.datetime", _FrozenDatetime)

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=sh)
    assert preview.status_code == 200
    html = preview.json()["data"]["html"]

    assert expected_tanggal in html
    assert format_tanggal_indonesia(fake_now) not in html
