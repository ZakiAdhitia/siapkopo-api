"""Idempotent database seeding."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.auth import Permission, Role, User
from app.models.master import RT, RW, Dusun, Resident, Village
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, ROLE_DEFS, ROLE_PERMISSIONS,
)
from app.seed.data import DUSUN, RESIDENTS, VILLAGE

logger = get_logger("seed")


async def seed_rbac(session: AsyncSession) -> None:
    """Seed permissions, roles, role-permission mappings, and demo users."""
    # Permissions: union of the concrete PERMISSIONS list and every code
    # referenced by any role (including the "*" wildcard sentinel), so the
    # wildcard is a real DB row and permission resolution stays purely
    # data-driven (no static-registry short-circuit at read time).
    all_codes = set(PERMISSIONS) | {
        code for codes in ROLE_PERMISSIONS.values() for code in codes
    }
    existing_perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for code in all_codes:
        if code not in existing_perms:
            p = Permission(code=code)
            session.add(p)
            existing_perms[code] = p
    await session.flush()

    # Roles + mappings
    existing_roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    for name, display in ROLE_DEFS:
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, display_name=display)
            session.add(role)
            existing_roles[name] = role
        role.permissions = [existing_perms[c] for c in ROLE_PERMISSIONS[name]]
    await session.flush()

    # Demo users
    existing_users = {u.username: u for u in (await session.scalars(select(User))).all()}
    for acc in DEMO_ACCOUNTS:
        if acc["username"] in existing_users:
            continue
        session.add(User(
            username=acc["username"], nik=acc["nik"], full_name=acc["full_name"],
            hashed_password=hash_password(acc["password"]),
            role_id=existing_roles[acc["role"]].id, is_active=True,
        ))
    await session.commit()
    logger.info("seed_rbac complete: %d permissions, %d roles, %d demo users",
                len(existing_perms), len(existing_roles), len(DEMO_ACCOUNTS))


async def seed_master(session: AsyncSession) -> None:
    """Seed the village, dusun, RW/RT, and residents from mockData.

    Idempotent: re-running keeps the village/dusun singletons and skips any
    resident whose synthetic NIK already exists.
    """
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        village = Village(**VILLAGE)
        session.add(village)
        await session.flush()

    dusun_map = {d.name: d for d in (await session.scalars(select(Dusun))).all()}
    for name in DUSUN:
        if name not in dusun_map:
            d = Dusun(village_id=village.id, name=name)
            session.add(d)
            dusun_map[name] = d
    await session.flush()

    # Build RW/RT lazily keyed by (dusun, rw) and (rw_obj.id, rt).
    rw_cache: dict[tuple[str, str], RW] = {}
    rt_cache: dict[tuple, RT] = {}
    existing_niks = {r.nik for r in (await session.scalars(select(Resident))).all()}
    created = 0
    for nik_suffix, name, _kk, dusun_name, rt_no, rw_no in RESIDENTS:
        # Synthetic resident NIK, intentionally distinct from demo-user NIKs.
        nik = f"3516{nik_suffix.zfill(12)[:12]}"
        if nik in existing_niks:
            continue
        dusun = dusun_map[dusun_name]
        rw = rw_cache.get((dusun_name, rw_no))
        if rw is None:
            rw = RW(dusun_id=dusun.id, number=rw_no)
            session.add(rw)
            await session.flush()
            rw_cache[(dusun_name, rw_no)] = rw
        rt = rt_cache.get((rw.id, rt_no))
        if rt is None:
            rt = RT(rw_id=rw.id, number=rt_no)
            session.add(rt)
            await session.flush()
            rt_cache[(rw.id, rt_no)] = rt
        session.add(Resident(village_id=village.id, nik=nik, full_name=name, rt_id=rt.id))
        created += 1
    await session.commit()
    logger.info("seed_master complete: %d residents created (%d already present)",
                created, len(existing_niks))


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: RBAC/demo-users, then village hierarchy + residents."""
    await seed_rbac(session)
    await seed_master(session)
