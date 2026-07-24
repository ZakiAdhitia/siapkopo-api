"""Tests for the public, no-auth letter verification endpoint."""
import pytest
from sqlalchemy import select

from app.models.auth import Role


async def _token(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_public_verify_returns_letter_details_for_issued_code(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
            "public_verify_base_url": "http://localhost:5173/verify",
        })(),
    )
    admin_tok = await _token(client, "operator", "operator123")
    h = {"Authorization": f"Bearer {admin_tok}"}
    village = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    village_id = village.json()["data"]["id"]
    template = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    template_id = template.json()["data"]["id"]
    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}
    await client.put("/api/v1/approval-steps", json={
        "village_id": village_id, "steps": [{"role_id": roles["staf"]}],
    }, headers=h)

    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {},
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    staf_tok = await _token(client, "staf", "staf123")
    approved = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={},
        headers={"Authorization": f"Bearer {staf_tok}"},
    )
    code = approved.json()["data"]["verification_code"]

    # No Authorization header at all — must work unauthenticated.
    resp = await client.get(f"/api/v1/public/verify/{code}")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["letter_number"] == approved.json()["data"]["letter_number"]
    assert body["template_name"] == "Surat Domisili"


@pytest.mark.asyncio
async def test_public_verify_unknown_code_returns_404(client):
    resp = await client.get("/api/v1/public/verify/NOPE-2026-000000")
    assert resp.status_code == 404
