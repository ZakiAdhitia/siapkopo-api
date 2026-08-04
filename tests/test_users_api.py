"""Integration tests for the admin-driven user management CRUD endpoints."""
import pytest
from sqlalchemy import select

from app.models.auth import Position, User


async def _token(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    return r.json()["data"]["access_token"]


async def _headers(client, username, password):
    tok = await _token(client, username, password)
    return {"Authorization": f"Bearer {tok}"}


async def _position_id(db_session, slug: str) -> str:
    position = (await db_session.scalars(select(Position).where(Position.slug == slug))).first()
    return str(position.id)


async def _user_by_username(db_session, username: str) -> User:
    return (await db_session.scalars(select(User).where(User.username == username))).first()


@pytest.mark.asyncio
async def test_list_positions_returns_seeded_catalog(client):
    resp = await client.get("/api/v1/positions", headers=await _headers(client, "kades", "kades123"))
    assert resp.status_code == 200
    slugs = [p["slug"] for p in resp.json()["data"]]
    assert "kepala_desa" in slugs
    assert "warga_desa" in slugs


@pytest.mark.asyncio
async def test_list_positions_requires_user_manage_permission(client):
    resp = await client.get("/api/v1/positions", headers=await _headers(client, "staf", "staf123"))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_create_user_by_kades_succeeds(client, db_session):
    """kades (level 1) may create a bendahara_desa (level 3) account -- role
    is derived from the position via POSITION_ROLE_MAP."""
    h = await _headers(client, "kades", "kades123")
    position_id = await _position_id(db_session, "bendahara_desa")

    resp = await client.post("/api/v1/users", json={
        "full_name": "Budi Bendahara Baru", "username": "bendahara_baru",
        "password": "rahasia123", "email": "bendahara.baru@example.test",
        "phone": "081234500001", "position_id": position_id,
    }, headers=h)

    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["role_name"] == "staff"
    assert data["position_name"] == "Bendahara Desa"


@pytest.mark.asyncio
async def test_create_user_by_sekdes_for_kepala_desa_forbidden(client, db_session):
    """sekdes (level 2) may NOT create an account at a higher-authority
    (lower level number) position such as kepala_desa (level 1)."""
    h = await _headers(client, "sekdes", "sekdes123")
    position_id = await _position_id(db_session, "kepala_desa")

    resp = await client.post("/api/v1/users", json={
        "full_name": "Calon Kepala Desa", "username": "calon_kades",
        "password": "rahasia123", "email": "calon.kades@example.test",
        "phone": "081234500002", "position_id": position_id,
    }, headers=h)

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_list_users_hides_warga_by_default_and_shows_with_flag(client):
    h = await _headers(client, "kades", "kades123")

    default_resp = await client.get("/api/v1/users", headers=h)
    assert default_resp.status_code == 200
    default_items = default_resp.json()["data"]["items"]
    assert all(item["position_name"] != "Warga Desa" for item in default_items)

    included_resp = await client.get("/api/v1/users", params={"include_warga": True}, headers=h)
    assert included_resp.status_code == 200
    included_items = included_resp.json()["data"]["items"]
    assert any(item["position_name"] == "Warga Desa" for item in included_items)


@pytest.mark.asyncio
async def test_list_users_search_filters_to_exact_match(client):
    h = await _headers(client, "kades", "kades123")

    resp = await client.get("/api/v1/users", params={"search": "kades"}, headers=h)

    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 1
    assert items[0]["username"] == "kades"


@pytest.mark.asyncio
async def test_update_user_by_kades_on_sekdes_succeeds(client, db_session):
    h = await _headers(client, "kades", "kades123")
    sekdes = await _user_by_username(db_session, "sekdes")

    resp = await client.put(
        f"/api/v1/users/{sekdes.id}", json={"full_name": "Dewi Lestari Baru"}, headers=h
    )

    assert resp.status_code == 200
    assert resp.json()["data"]["full_name"] == "Dewi Lestari Baru"


@pytest.mark.asyncio
async def test_update_user_by_sekdes_on_kades_forbidden(client, db_session):
    """sekdes (level 2) may NOT update kades (level 1) -- higher authority."""
    h = await _headers(client, "sekdes", "sekdes123")
    kades = await _user_by_username(db_session, "kades")

    resp = await client.put(
        f"/api/v1/users/{kades.id}", json={"full_name": "Tidak Boleh Diubah"}, headers=h
    )

    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_delete_user_by_kades_on_bendahara(client, db_session):
    h = await _headers(client, "kades", "kades123")
    bendahara = await _user_by_username(db_session, "bendahara")

    resp = await client.delete(f"/api/v1/users/{bendahara.id}", headers=h)
    assert resp.status_code == 200

    followup = await client.get(f"/api/v1/users/{bendahara.id}", headers=h)
    assert followup.status_code == 404


@pytest.mark.asyncio
async def test_approve_pending_registration(client, db_session):
    reg = await client.post("/api/v1/auth/register", json={
        "full_name": "Calon Staff Satu", "username": "calon_staff1",
        "password": "rahasia123", "email": "calon.staff1@example.test",
        "position_choice": "staff",
    })
    assert reg.status_code == 200
    assert reg.json()["data"]["status"] == "pending_approval"

    pending = await _user_by_username(db_session, "calon_staff1")
    assert pending is not None
    assert pending.pending_approval is True

    h = await _headers(client, "kades", "kades123")
    resp = await client.post(f"/api/v1/users/{pending.id}/approve", headers=h)

    assert resp.status_code == 200
    assert resp.json()["data"]["pending_approval"] is False

    login = await client.post("/api/v1/auth/login", json={
        "identifier": "calon_staff1", "password": "rahasia123",
    })
    assert login.status_code == 200


@pytest.mark.asyncio
async def test_reject_pending_registration(client, db_session):
    reg = await client.post("/api/v1/auth/register", json={
        "full_name": "Calon Staff Dua", "username": "calon_staff2",
        "password": "rahasia123", "email": "calon.staff2@example.test",
        "position_choice": "staff",
    })
    assert reg.status_code == 200

    pending = await _user_by_username(db_session, "calon_staff2")
    assert pending is not None

    h = await _headers(client, "kades", "kades123")
    resp = await client.post(f"/api/v1/users/{pending.id}/reject", headers=h)
    assert resp.status_code == 200

    login = await client.post("/api/v1/auth/login", json={
        "identifier": "calon_staff2", "password": "rahasia123",
    })
    assert login.status_code == 401


@pytest.mark.asyncio
async def test_users_endpoints_require_permission(client):
    no_token = await client.get("/api/v1/users")
    assert no_token.status_code == 401

    warga_h = await _headers(client, "warga", "warga123")
    forbidden = await client.get("/api/v1/users", headers=warga_h)
    assert forbidden.status_code == 403
