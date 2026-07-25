import pytest
from sqlalchemy import select

from app.core.exceptions import ForbiddenError, ValidationAppError
from app.core.security import hash_password
from app.models.auth import Position, Role, User
from app.models.master import RT, RW, Dusun
from app.services.auth import AuthService
from app.services.lapduk import LapdukService


async def _make_rw_rt(session):
    """Create one Dusun -> RW -> RT chain and return (rw, rt)."""
    dusun = Dusun(name="Dusun Uji")
    session.add(dusun)
    await session.flush()
    rw = RW(dusun_id=dusun.id, number="01")
    session.add(rw)
    await session.flush()
    rt = RT(rw_id=rw.id, number="01")
    session.add(rt)
    await session.flush()
    return rw, rt


async def _make_actor(session, *, role_name: str, position_slug: str | None, rt_id=None, rw_id=None):
    role = await session.scalar(select(Role).where(Role.name == role_name))
    position = None
    if position_slug:
        position = await session.scalar(select(Position).where(Position.slug == position_slug))
    user = User(
        username=f"lapduk_{role_name}_{position_slug}", full_name="Actor Uji",
        hashed_password=hash_password("pass1234"), email=f"{role_name}{position_slug}@test.local",
        role_id=role.id, position_id=position.id if position else None,
        rt_id=rt_id, rw_id=rw_id, is_active=True,
    )
    user.role = role
    user.position = position
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_rt_can_upsert_own_rt(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    rt_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rt", rt_id=rt.id)
    perms = AuthService(seeded_session).permissions_for(rt_actor)

    obj = await LapdukService(seeded_session).upsert(
        rt_actor, perms, {"rt_id": rt.id, "period": "2026-07", "jumlah_kk": 10}
    )
    assert obj.jumlah_kk == 10
    assert obj.rt_id == rt.id


@pytest.mark.asyncio
async def test_rt_cannot_upsert_other_rt(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    _, other_rt = await _make_rw_rt(seeded_session)
    rt_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rt", rt_id=rt.id)
    perms = AuthService(seeded_session).permissions_for(rt_actor)

    with pytest.raises(ForbiddenError):
        await LapdukService(seeded_session).upsert(
            rt_actor, perms, {"rt_id": other_rt.id, "period": "2026-07"}
        )


@pytest.mark.asyncio
async def test_upsert_is_idempotent_per_rt_period(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    rt_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rt", rt_id=rt.id)
    perms = AuthService(seeded_session).permissions_for(rt_actor)
    svc = LapdukService(seeded_session)

    await svc.upsert(rt_actor, perms, {"rt_id": rt.id, "period": "2026-07", "jumlah_kk": 5})
    updated = await svc.upsert(rt_actor, perms, {"rt_id": rt.id, "period": "2026-07", "jumlah_kk": 9})

    rows, total = await svc.list(rt_actor, perms, 1, 20, None, None, None)
    assert total == 1
    assert updated.jumlah_kk == 9


@pytest.mark.asyncio
async def test_upsert_rejects_nonexistent_rt(seeded_session):
    """An unrestricted actor (past the write-authorization check) still gets
    a clean ValidationAppError for a nonexistent rt_id, not an integrity
    error or silent success."""
    import uuid

    admin = await AuthService(seeded_session).users.get_by_username("operator")
    perms = AuthService(seeded_session).permissions_for(admin)

    with pytest.raises(ValidationAppError):
        await LapdukService(seeded_session).upsert(
            admin, perms, {"rt_id": uuid.uuid4(), "period": "2026-07"}
        )


@pytest.mark.asyncio
async def test_rw_can_list_own_rw_rts_only(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    _, other_rt = await _make_rw_rt(seeded_session)
    rw_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rw", rw_id=rw.id)
    rw_perms = AuthService(seeded_session).permissions_for(rw_actor)

    # Seed both RTs' reports via an unrestricted actor (administrator-it).
    admin = await AuthService(seeded_session).users.get_by_username("operator")
    admin_perms = AuthService(seeded_session).permissions_for(admin)
    svc = LapdukService(seeded_session)
    await svc.upsert(admin, admin_perms, {"rt_id": rt.id, "period": "2026-07", "jumlah_kk": 1})
    await svc.upsert(admin, admin_perms, {"rt_id": other_rt.id, "period": "2026-07", "jumlah_kk": 2})

    rows, total = await svc.list(rw_actor, rw_perms, 1, 20, None, None, None)
    assert total == 1
    assert rows[0].rt_id == rt.id


@pytest.mark.asyncio
async def test_rw_cannot_write_directly(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    rw_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rw", rw_id=rw.id)
    perms = AuthService(seeded_session).permissions_for(rw_actor)

    with pytest.raises(ForbiddenError):
        await LapdukService(seeded_session).upsert(
            rw_actor, perms, {"rt_id": rt.id, "period": "2026-07"}
        )


@pytest.mark.asyncio
async def test_staff_can_write_and_read_all(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    staff = await AuthService(seeded_session).users.get_by_username("staf")
    perms = AuthService(seeded_session).permissions_for(staff)
    svc = LapdukService(seeded_session)

    await svc.upsert(staff, perms, {"rt_id": rt.id, "period": "2026-07", "jumlah_kk": 4})
    rows, total = await svc.list(staff, perms, 1, 20, None, None, None)
    assert total == 1


@pytest.mark.asyncio
async def test_actor_without_lapduk_permission_denied(seeded_session):
    warga = await AuthService(seeded_session).users.get_by_username("warga")
    perms = AuthService(seeded_session).permissions_for(warga)
    assert not ({"lapduk:manage_own", "lapduk:read_rw", "lapduk:read_all", "*"} & set(perms))

    with pytest.raises(ForbiddenError):
        await LapdukService(seeded_session).list(warga, perms, 1, 20, None, None, None)


@pytest.mark.asyncio
async def test_export_requires_export_permission(seeded_session):
    rw, rt = await _make_rw_rt(seeded_session)
    rt_actor = await _make_actor(seeded_session, role_name="warga", position_slug="rt", rt_id=rt.id)
    perms = AuthService(seeded_session).permissions_for(rt_actor)

    with pytest.raises(ForbiddenError):
        await LapdukService(seeded_session).export_bytes(rt_actor, perms, None, None)


@pytest.mark.asyncio
async def test_import_isolates_bad_rows(seeded_session):
    import io

    import openpyxl

    rw, rt = await _make_rw_rt(seeded_session)
    staff = await AuthService(seeded_session).users.get_by_username("staf")
    perms = AuthService(seeded_session).permissions_for(staff)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["rt_id", "period", "jumlah_kk", "laki_laki", "perempuan", "pindah", "datang", "lahir", "meninggal"])
    ws.append([str(rt.id), "2026-07", 3, 1, 2, 0, 0, 0, 0])
    ws.append(["not-a-uuid", "2026-07", 1, 1, 0, 0, 0, 0, 0])
    buf = io.BytesIO()
    wb.save(buf)

    result = await LapdukService(seeded_session).import_bytes(staff, perms, buf.getvalue())
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3
