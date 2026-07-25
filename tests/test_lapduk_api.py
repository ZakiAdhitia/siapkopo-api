"""Integration tests for the LAPDUK endpoints (routing + permission wiring)."""
import pytest
from sqlalchemy import select

from app.core.security import hash_password
from app.models.auth import Position, Role, User
from app.models.master import RT, RW, Dusun


async def _token(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    return r.json()["data"]["access_token"]


async def _headers(client, username, password):
    tok = await _token(client, username, password)
    return {"Authorization": f"Bearer {tok}"}


async def _make_rt(db_session):
    dusun = Dusun(name="Dusun API Uji")
    db_session.add(dusun)
    await db_session.flush()
    rw = RW(dusun_id=dusun.id, number="02")
    db_session.add(rw)
    await db_session.flush()
    rt = RT(rw_id=rw.id, number="02")
    db_session.add(rt)
    await db_session.commit()
    return rt


async def _make_rt_user(db_session, rt_id, username="rtapiuser"):
    role = (await db_session.scalars(select(Role).where(Role.name == "warga"))).first()
    position = (await db_session.scalars(select(Position).where(Position.slug == "rt"))).first()
    user = User(
        username=username, full_name="RT API Uji", hashed_password=hash_password("rtpass123"),
        email=f"{username}@example.test", role_id=role.id, position_id=position.id,
        rt_id=rt_id, is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    return user


@pytest.mark.asyncio
async def test_upsert_and_list_via_api_as_rt(client, db_session):
    rt = await _make_rt(db_session)
    await _make_rt_user(db_session, rt.id)
    h = await _headers(client, "rtapiuser", "rtpass123")

    resp = await client.post("/api/v1/lapduk", json={
        "rt_id": str(rt.id), "period": "2026-07", "jumlah_kk": 12,
    }, headers=h)
    assert resp.status_code == 200
    assert resp.json()["data"]["jumlah_kk"] == 12

    listed = await client.get("/api/v1/lapduk", headers=h)
    assert listed.status_code == 200
    assert listed.json()["data"]["total"] == 1


@pytest.mark.asyncio
async def test_upsert_other_rt_forbidden_via_api(client, db_session):
    rt = await _make_rt(db_session)
    other_rt = await _make_rt(db_session)
    await _make_rt_user(db_session, rt.id)
    h = await _headers(client, "rtapiuser", "rtpass123")

    resp = await client.post("/api/v1/lapduk", json={
        "rt_id": str(other_rt.id), "period": "2026-07",
    }, headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_warga_without_lapduk_access_gets_forbidden(client):
    h = await _headers(client, "warga", "warga123")
    resp = await client.get("/api/v1/lapduk", headers=h)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_staff_can_export(client, db_session):
    rt = await _make_rt(db_session)
    h = await _headers(client, "staf", "staf123")
    await client.post("/api/v1/lapduk", json={
        "rt_id": str(rt.id), "period": "2026-07", "jumlah_kk": 7,
    }, headers=h)

    resp = await client.get("/api/v1/lapduk/export", headers=h)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
