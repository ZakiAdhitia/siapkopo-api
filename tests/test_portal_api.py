"""Integration tests for Portal Desa admin CRUD + public read endpoints."""
import pytest


async def _headers(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    tok = r.json()["data"]["access_token"]
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_news_crud_and_public_read(client):
    h = await _headers(client, "kades", "kades123")
    created = await client.post("/api/v1/portal/news", json={
        "content_type": "berita", "judul": "Desa Kopo Raih Penghargaan",
        "tanggal": "2026-07-20", "excerpt": "Ringkasan singkat berita.",
    }, headers=h)
    assert created.status_code == 200
    news_id = created.json()["data"]["id"]

    public = await client.get("/api/v1/public/portal/news")
    assert public.status_code == 200
    titles = [n["judul"] for n in public.json()["data"]]
    assert "Desa Kopo Raih Penghargaan" in titles

    updated = await client.put(f"/api/v1/portal/news/{news_id}", json={"judul": "Judul Diperbarui"}, headers=h)
    assert updated.status_code == 200
    assert updated.json()["data"]["judul"] == "Judul Diperbarui"

    deleted = await client.delete(f"/api/v1/portal/news/{news_id}", headers=h)
    assert deleted.status_code == 200
    public_after = await client.get("/api/v1/public/portal/news")
    assert news_id not in [n["id"] for n in public_after.json()["data"]]


@pytest.mark.asyncio
async def test_gallery_ordering_via_public_read(client):
    h = await _headers(client, "kades", "kades123")
    await client.post("/api/v1/portal/gallery", json={
        "photo_path": "gallery/2.jpg", "order_index": 2,
    }, headers=h)
    await client.post("/api/v1/portal/gallery", json={
        "photo_path": "gallery/1.jpg", "order_index": 1,
    }, headers=h)

    gallery = await client.get("/api/v1/public/portal/gallery")
    assert [g["order_index"] for g in gallery.json()["data"]] == sorted(
        g["order_index"] for g in gallery.json()["data"]
    )


@pytest.mark.asyncio
async def test_public_profile_readable_without_auth(client, db_session):
    from app.models.master import VillageProfile

    db_session.add(VillageProfile(name="Desa Kopo Uji"))
    await db_session.commit()

    resp = await client.get("/api/v1/public/portal/profile")
    assert resp.status_code == 200
    assert resp.json()["data"]["name"] == "Desa Kopo Uji"


@pytest.mark.asyncio
async def test_portal_admin_endpoints_require_permission(client):
    h = await _headers(client, "warga", "warga123")
    resp = await client.post("/api/v1/portal/news", json={
        "content_type": "berita", "judul": "x", "tanggal": "2026-07-20",
    }, headers=h)
    assert resp.status_code == 403
