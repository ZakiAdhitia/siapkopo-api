"""Integration tests for the dashboard aggregation endpoints."""
import pytest
from sqlalchemy import select

from app.models.auth import Role


async def _headers(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    tok = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


async def _setup_and_submit(client, db_session):
    # 2026-08-05: template create/field-add/approval-step-config now require
    # template:manage/approval_config:manage, which Kepala Desa (kades) no
    # longer holds (HASIL_UJICOBA_PERROLE.md kades items 1/4) -- use the
    # unrestricted "operator" (administrator-it, "*") account for setup,
    # same pattern as test_submission_api.py's _setup_village_template_workflow.
    h = await _headers(client, "operator", "operator123")
    template = await client.post("/api/v1/templates", json={
        "code": "dashuji", "name": "Surat Dashboard Uji",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "999", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ catatan }}</p>",
        "required_documents": ["KTP"],
    }, headers=h)
    template_id = template.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "catatan", "label": "Catatan", "field_type": "text", "is_required": True,
    }, headers=h)
    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}
    await client.put("/api/v1/approval-steps", json={
        "steps": [{"role_id": roles["staff"]}, {"role_id": roles["admin"]}],
    }, headers=h)

    wh = await _headers(client, "warga", "warga123")
    await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"catatan": "uji dashboard"},
    }, headers=wh)


@pytest.mark.asyncio
async def test_stats_and_inbox_reflect_pending_submission(client, db_session):
    await _setup_and_submit(client, db_session)
    h = await _headers(client, "staf", "staf123")

    stats = await client.get("/api/v1/dashboard/stats", headers=h)
    assert stats.status_code == 200
    assert stats.json()["data"]["pending"] >= 1

    inbox = await client.get("/api/v1/dashboard/inbox", headers=h)
    assert inbox.status_code == 200
    assert len(inbox.json()["data"]) >= 1

    per_jenis = await client.get("/api/v1/dashboard/per-jenis", headers=h)
    assert per_jenis.status_code == 200

    trend = await client.get("/api/v1/dashboard/trend?days=7", headers=h)
    assert trend.status_code == 200
    assert len(trend.json()["data"]) == 7


@pytest.mark.asyncio
async def test_dashboard_requires_permission(client):
    h = await _headers(client, "warga", "warga123")
    resp = await client.get("/api/v1/dashboard/stats", headers=h)
    assert resp.status_code == 403
