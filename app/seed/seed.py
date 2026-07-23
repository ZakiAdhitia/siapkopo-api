"""Idempotent database seeding."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.auth import Permission, Role, User
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, ROLE_DEFS, ROLE_PERMISSIONS,
)


async def seed_rbac(session: AsyncSession) -> None:
    """Seed permissions, roles, role-permission mappings, and demo users."""
    # Permissions
    existing_perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for code in PERMISSIONS:
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
        codes = ROLE_PERMISSIONS[name]
        role.permissions = (
            list(existing_perms.values()) if codes == ["*"]
            else [existing_perms[c] for c in codes]
        )
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


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders (master-data seeding appended in Task 20)."""
    await seed_rbac(session)
