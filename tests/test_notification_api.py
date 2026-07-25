"""Integration tests for the notification endpoints."""
import pytest


async def _headers(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    tok = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_full_notification_flow_via_api(client, db_session):
    from app.services.auth import AuthService
    from app.services.notification import NotificationService

    warga = await AuthService(db_session).users.get_by_username("warga")
    await NotificationService(db_session).notify(warga.id, "test:event", "Judul", "Isi pesan")

    h = await _headers(client, "warga", "warga123")
    listed = await client.get("/api/v1/notifications", headers=h)
    assert listed.status_code == 200
    body = listed.json()["data"]
    assert body["total"] == 1
    notif_id = body["items"][0]["id"]
    assert body["items"][0]["is_read"] is False

    marked = await client.post(f"/api/v1/notifications/{notif_id}/read", headers=h)
    assert marked.status_code == 200
    assert marked.json()["data"]["is_read"] is True

    read_all = await client.post("/api/v1/notifications/read-all", headers=h)
    assert read_all.status_code == 200


@pytest.mark.asyncio
async def test_notifications_require_auth(client):
    resp = await client.get("/api/v1/notifications")
    assert resp.status_code == 401
