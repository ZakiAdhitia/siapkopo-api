import pytest


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_replace_and_list_approval_steps(client, db_session):
    from app.models.auth import Role
    from sqlalchemy import select

    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    village_id = village.json()["data"]["id"]

    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}

    put_resp = await client.put(
        "/api/v1/approval-steps",
        json={
            "village_id": village_id,
            "steps": [{"role_id": roles["staff"]}, {"role_id": roles["admin"]}],
        },
        headers=h,
    )
    assert put_resp.status_code == 200
    assert len(put_resp.json()["data"]) == 2

    get_resp = await client.get(f"/api/v1/approval-steps?village_id={village_id}", headers=h)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 2


@pytest.mark.asyncio
async def test_replace_requires_manage_permission(client):
    # staff lacks approval_config:manage (admin -- kades/sekdes -- has it).
    tok = await _token(client, "staf", "staf123")
    resp = await client.put(
        "/api/v1/approval-steps",
        json={"village_id": "00000000-0000-0000-0000-000000000000", "steps": []},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403
