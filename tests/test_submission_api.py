import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.auth import Role, User
from app.models.master import FamilyCard, Resident, VillageProfile


async def _token(client, identifier, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


async def _setup_village_template_workflow(client, db_session):
    """Seed the village profile singleton + a letter template + a 2-step workflow.

    The village profile has no create/delete endpoint (singleton -- see
    VillageProfileService), so it's seeded directly via the DB session
    rather than through the API. It's still required here because the
    final approval step's PDF issuance reads it via VillageProfileService.get().
    """
    db_session.add(VillageProfile(name="Desa Kopo"))
    await db_session.commit()

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

    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}
    await client.put("/api/v1/approval-steps", json={
        "steps": [{"role_id": roles["staff"]}, {"role_id": roles["admin"]}],
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
    }, headers=wh)
    assert created.status_code == 200
    submission_id = created.json()["data"]["id"]

    mine = await client.get("/api/v1/submissions", headers=wh)
    assert mine.json()["data"]["total"] == 1

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}
    approve1 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "ok"}, headers=sh
    )
    assert approve1.status_code == 200
    assert approve1.json()["data"]["status"] == "pending"

    kades_tok = await _token(client, "kades", "kades123")
    kh = {"Authorization": f"Bearer {kades_tok}"}
    approve2 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "signed"}, headers=kh
    )
    assert approve2.status_code == 200
    body = approve2.json()["data"]
    assert body["status"] == "issued"
    assert body["letter_number"]

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=wh)
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"

    history = await client.get(f"/api/v1/submissions/{submission_id}/history", headers=wh)
    assert [h["action"] for h in history.json()["data"]] == ["submitted", "approved", "issued"]


@pytest.mark.asyncio
async def test_get_my_applicant_data_falls_back_to_user_fields(client, db_session):
    """The `client` fixture only seeds RBAC (no seed_master/link step), so the
    demo 'warga' account has no linked Resident here -- exercises the
    User-fallback branch of SubmissionService.resolve_applicant_data.
    """
    warga_tok = await _token(client, "warga", "warga123")
    resp = await client.get(
        "/api/v1/submissions/me/applicant-data",
        headers={"Authorization": f"Bearer {warga_tok}"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data == {"nama": "Siti Rohmah", "nik": "3516064588020003", "alamat": "-", "no_kk": "-"}


@pytest.mark.asyncio
async def test_get_my_applicant_data_returns_linked_resident(client, db_session):
    """When the user IS linked to a Resident/FamilyCard, prefer that over the
    User-row fallback (exercises the other branch of resolve_applicant_data).
    """
    fc = FamilyCard(kk_number="3516000000009999", address="Jl. Merdeka 1")
    db_session.add(fc)
    await db_session.flush()
    resident = Resident(
        nik="3516000000001234", full_name="Warga Uji", family_card_id=fc.id,
        address="Jl. Merdeka 1 RT 01/RW 01",
    )
    db_session.add(resident)
    await db_session.flush()

    warga_user = await db_session.scalar(select(User).where(User.username == "warga"))
    warga_user.resident_id = resident.id
    await db_session.commit()

    warga_tok = await _token(client, "warga", "warga123")
    resp = await client.get(
        "/api/v1/submissions/me/applicant-data",
        headers={"Authorization": f"Bearer {warga_tok}"},
    )
    assert resp.status_code == 200
    assert resp.json()["data"] == {
        "nama": "Warga Uji", "nik": "3516000000001234",
        "alamat": "Jl. Merdeka 1 RT 01/RW 01", "no_kk": "3516000000009999",
    }


@pytest.mark.asyncio
async def test_approve_wrong_turn_returns_403(client, db_session):
    template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji"},
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
