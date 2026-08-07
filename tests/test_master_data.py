"""Integration tests for master-data CRUD endpoints."""
import pytest


async def _token(client, identifier="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


async def _auth_headers(client, username="operator", password="operator123"):
    tok = await _token(client, username, password)
    return {"Authorization": f"Bearer {tok}"}


@pytest.mark.asyncio
async def test_village_profile_get(client):
    """GET /village-profile always returns the hardcoded village identity
    (no DB row -- see app.models.master.VillageProfile's docstring)."""
    h = await _auth_headers(client)
    got = await client.get("/api/v1/village-profile", headers=h)
    assert got.status_code == 200
    assert got.json()["data"]["name"] == "Kopo"


@pytest.mark.asyncio
async def test_village_profile_requires_auth(client):
    resp = await client.get("/api/v1/village-profile")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_rw_rt_crud(client):
    """No more family-cards here (2026-08-06: FamilyCard removed along with
    Resident, see app/models/master.py's module docstring)."""
    h = await _auth_headers(client)

    rw = await client.post("/api/v1/rw", json={"number": "001"}, headers=h)
    assert rw.status_code == 200
    rw_id = rw.json()["data"]["id"]

    rt = await client.post("/api/v1/rt", json={"rw_id": rw_id, "number": "002"}, headers=h)
    assert rt.status_code == 200
    rt_id = rt.json()["data"]["id"]

    for path, item_id, update_body in [
        ("rw", rw_id, {"number": "003"}),
        ("rt", rt_id, {"number": "004"}),
    ]:
        upd = await client.put(f"/api/v1/{path}/{item_id}", json=update_body, headers=h)
        assert upd.status_code == 200, path
        lst = await client.get(f"/api/v1/{path}", headers=h)
        assert lst.status_code == 200
        assert lst.json()["data"]["total"] >= 1
        dele = await client.delete(f"/api/v1/{path}/{item_id}", headers=h)
        assert dele.status_code == 200, path
