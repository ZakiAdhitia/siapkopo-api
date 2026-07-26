"""Integration tests for master-data CRUD endpoints."""
import pytest

from app.models.master import VillageProfile


async def _token(client, identifier="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


async def _auth_headers(client, username="operator", password="operator123"):
    tok = await _token(client, username, password)
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_village_profile_not_found_until_seeded(client):
    """GET /village-profile 404s before the singleton row exists.

    There is no create/delete for the village profile (it's a singleton --
    see VillageProfileService); this replaces the old multi-village create
    test, which no longer applies since that capability was removed.
    """
    h = await _auth_headers(client)
    missing = await client.get("/api/v1/village-profile", headers=h)
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "NOT_FOUND"


@pytest.mark.asyncio
async def test_village_profile_get_and_update_flow(client, db_session):
    """GET/PUT work once the singleton row exists (seeded directly, since
    there's no POST for it)."""
    db_session.add(VillageProfile(name="Desa Kopo"))
    await db_session.commit()

    h = await _auth_headers(client)
    got = await client.get("/api/v1/village-profile", headers=h)
    assert got.status_code == 200
    assert got.json()["data"]["name"] == "Desa Kopo"

    updated = await client.put(
        "/api/v1/village-profile", json={"slogan": "Kopo Kita"}, headers=h
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["slogan"] == "Kopo Kita"

    got_again = await client.get("/api/v1/village-profile", headers=h)
    assert got_again.json()["data"]["slogan"] == "Kopo Kita"


@pytest.mark.asyncio
async def test_village_profile_requires_auth(client):
    resp = await client.get("/api/v1/village-profile")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_village_profile_update_requires_permission(client, db_session):
    db_session.add(VillageProfile(name="Desa Kopo"))
    await db_session.commit()

    # staff has no village:manage — updating must 403.
    h = await _auth_headers(client, "staf", "staf123")
    resp = await client.put(
        "/api/v1/village-profile", json={"slogan": "Nope"}, headers=h
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_dusun_rw_rt_family_card_crud(client):
    h = await _auth_headers(client)

    dusun = await client.post("/api/v1/dusun", json={"name": "Krajan"}, headers=h)
    assert dusun.status_code == 200
    did = dusun.json()["data"]["id"]
    assert (await client.get(f"/api/v1/dusun/{did}", headers=h)).json()["data"]["name"] == "Krajan"

    rw = await client.post("/api/v1/rw", json={"dusun_id": did, "number": "001"}, headers=h)
    assert rw.status_code == 200
    rw_id = rw.json()["data"]["id"]

    rt = await client.post("/api/v1/rt", json={"rw_id": rw_id, "number": "002"}, headers=h)
    assert rt.status_code == 200
    rt_id = rt.json()["data"]["id"]

    fc = await client.post(
        "/api/v1/family-cards",
        json={"kk_number": "1234567890123456"},
        headers=h,
    )
    assert fc.status_code == 200
    fc_id = fc.json()["data"]["id"]

    for path, item_id, update_body in [
        ("dusun", did, {"name": "Krajan Baru"}),
        ("rw", rw_id, {"number": "003"}),
        ("rt", rt_id, {"number": "004"}),
        ("family-cards", fc_id, {"address": "Jl Melati"}),
    ]:
        upd = await client.put(f"/api/v1/{path}/{item_id}", json=update_body, headers=h)
        assert upd.status_code == 200, path
        lst = await client.get(f"/api/v1/{path}", headers=h)
        assert lst.status_code == 200
        assert lst.json()["data"]["total"] >= 1
        dele = await client.delete(f"/api/v1/{path}/{item_id}", headers=h)
        assert dele.status_code == 200, path


@pytest.mark.asyncio
async def test_resident_crud_search_and_filter(client):
    h = await _auth_headers(client)

    created = await client.post(
        "/api/v1/residents",
        json={"nik": "1234567890123456", "full_name": "Budi Santoso"},
        headers=h,
    )
    assert created.status_code == 200
    rid = created.json()["data"]["id"]

    searched = await client.get("/api/v1/residents", params={"search": "Budi"}, headers=h)
    assert searched.status_code == 200
    assert searched.json()["data"]["total"] == 1

    updated = await client.put(
        f"/api/v1/residents/{rid}", json={"occupation": "Petani"}, headers=h
    )
    assert updated.status_code == 200
    assert updated.json()["data"]["occupation"] == "Petani"

    deleted = await client.delete(f"/api/v1/residents/{rid}", headers=h)
    assert deleted.status_code == 200


@pytest.mark.asyncio
async def test_resident_create_duplicate_nik_returns_409(client):
    """A DB-level unique-constraint violation must surface as 409 CONFLICT, not 500."""
    h = await _auth_headers(client)

    first = await client.post(
        "/api/v1/residents",
        json={"nik": "5555555555555555", "full_name": "Warga Pertama"},
        headers=h,
    )
    assert first.status_code == 200

    dup = await client.post(
        "/api/v1/residents",
        json={"nik": "5555555555555555", "full_name": "Warga Duplikat"},
        headers=h,
    )
    assert dup.status_code == 409
    body = dup.json()
    assert body["success"] is False
    assert body["error_code"] == "CONFLICT"


@pytest.mark.asyncio
async def test_resident_requires_permission(client):
    # kades has only resident:read — creating must 403
    h = await _auth_headers(client, "kades", "kades123")
    resp = await client.post(
        "/api/v1/residents",
        json={"nik": "1111000000000009", "full_name": "Z"},
        headers=h,
    )
    assert resp.status_code == 403
    assert resp.json()["error_code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_resident_read_allowed_for_kades(client):
    h_admin = await _auth_headers(client)
    await client.post(
        "/api/v1/residents",
        json={"nik": "1111000000000999", "full_name": "Y"},
        headers=h_admin,
    )

    h_kades = await _auth_headers(client, "kades", "kades123")
    resp = await client.get("/api/v1/residents", headers=h_kades)
    assert resp.status_code == 200
