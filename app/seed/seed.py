"""Idempotent database seeding."""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.auth import Permission, Position, Role, User
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import RT, RW, Dusun, Resident, Village
from app.models.submission import ApprovalStepConfig
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, POSITION_DEFS, POSITION_PERMISSIONS,
    ROLE_DEFS, ROLE_PERMISSIONS,
)
from app.seed.data import DUSUN, RESIDENTS, VILLAGE
from app.seed.letter_template_data import SURAT_TEMPLATES

logger = get_logger("seed")


async def seed_positions(session: AsyncSession) -> None:
    """Seed the fixed Position catalog (jabatan + hierarchy level).

    Idempotent: looks up existing positions by slug before inserting, same
    pattern as seed_rbac's role/permission handling.
    """
    all_codes = set(PERMISSIONS) | {
        code for codes in POSITION_PERMISSIONS.values() for code in codes
    }
    existing_perms = {p.code: p for p in (await session.scalars(select(Permission))).all()}
    for code in all_codes:
        if code not in existing_perms:
            p = Permission(code=code)
            session.add(p)
            existing_perms[code] = p
    await session.flush()

    existing_positions = {p.slug: p for p in (await session.scalars(select(Position))).all()}
    for slug, display_name, level in POSITION_DEFS:
        position = existing_positions.get(slug)
        if position is None:
            position = Position(slug=slug, display_name=display_name, level=level)
            session.add(position)
            existing_positions[slug] = position
        else:
            position.display_name = display_name
            position.level = level
        position.permissions = [existing_perms[c] for c in POSITION_PERMISSIONS[slug]]
    await session.commit()
    logger.info("seed_positions complete: %d positions", len(existing_positions))


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
    existing_positions = {p.slug: p for p in (await session.scalars(select(Position))).all()}
    for acc in DEMO_ACCOUNTS:
        if acc["username"] in existing_users:
            continue
        position_id = (
            existing_positions[acc["position"]].id if acc["position"] else None
        )
        session.add(User(
            username=acc["username"], nik=acc["nik"], full_name=acc["full_name"],
            hashed_password=hash_password(acc["password"]), email=acc["email"],
            role_id=existing_roles[acc["role"]].id, position_id=position_id,
            is_active=True,
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


async def seed_letter_templates(session: AsyncSession) -> None:
    """Seed the 11 letter templates (with fields) from mockData's suratTypes.

    Idempotent: skips any template whose code already exists for the village.
    Requires seed_master to have already created the village.
    """
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        raise RuntimeError("seed_letter_templates requires seed_master to run first")

    existing = {
        t.code for t in (await session.scalars(
            select(LetterTemplate).where(LetterTemplate.village_id == village.id)
        )).all()
    }
    created = 0
    for entry in SURAT_TEMPLATES:
        if entry["code"] in existing:
            continue
        template = LetterTemplate(
            village_id=village.id,
            code=entry["code"],
            name=entry["name"],
            description=entry["description"],
            icon=entry["icon"],
            color_bg=entry["color_bg"],
            color_fg=entry["color_fg"],
            is_active=True,
            required_documents=entry["required_documents"],
            numbering_prefix=entry["numbering_prefix"],
            numbering_pattern="{prefix}/{seq}/Ds.Kopo/{year}",
            pdf_body_template=entry["pdf_body_template"],
        )
        session.add(template)
        await session.flush()
        for order_index, (key, label, ftype, options, placeholder, required, rules) in enumerate(
            entry["fields"]
        ):
            session.add(TemplateField(
                template_id=template.id, order_index=order_index, field_key=key,
                label=label, field_type=FieldType(ftype), options=options,
                placeholder=placeholder, is_required=required, validation_rules=rules,
            ))
        created += 1
    await session.commit()
    logger.info("seed_letter_templates complete: %d templates created (%d already present)",
                created, len(existing))


async def seed_link_demo_resident(session: AsyncSession) -> None:
    """Link the demo 'warga' user to its matching Resident row.

    Both represent Siti Rohmah but currently exist as unlinked rows (see
    the plan's Task 15 rationale). Idempotent: no-op if already linked or
    if either side is missing.

    Matches by full_name, not NIK/ID — fine for this MVP seed dataset,
    which has exactly one "Siti Rohmah". If the dataset ever grows to
    include a second resident with the same name, this would silently
    link to whichever one the DB happens to return first (session.scalar
    does not raise on multiple matches). Not a concern for seed data, but
    do not reuse this name-matching pattern for non-seed application code.
    """
    user = await session.scalar(select(User).where(User.username == "warga"))
    if user is None or user.resident_id is not None:
        return
    resident = await session.scalar(select(Resident).where(Resident.full_name == "Siti Rohmah"))
    if resident is None:
        return
    user.resident_id = resident.id
    await session.commit()
    logger.info("seed_link_demo_resident: linked warga user to resident id=%s", resident.id)


async def seed_link_demo_rt_rw(session: AsyncSession) -> None:
    """Link the demo 'rt001'/'rw001' users to their matching RT/RW rows.

    Both demo accounts are seeded (in seed_rbac) before RT/RW master data
    exists (in seed_master), so their rt_id/rw_id start out null and get
    patched here, same two-pass pattern as seed_link_demo_resident.

    Matches by resident full_name -> that resident's own RT/RW, same
    fragility caveat as seed_link_demo_resident: fine for this single-match
    seed dataset, not a pattern to reuse for non-seed application code.
    """
    for acc in DEMO_ACCOUNTS:
        resident_name = acc.get("link_resident_name")
        if resident_name is None:
            continue
        user = await session.scalar(select(User).where(User.username == acc["username"]))
        if user is None or (user.rt_id is not None or user.rw_id is not None):
            continue
        resident = await session.scalar(
            select(Resident).where(Resident.full_name == resident_name)
        )
        if resident is None or resident.rt_id is None:
            continue
        rt = await session.get(RT, resident.rt_id)
        if rt is None:
            continue
        if acc["position"] == "rt":
            user.rt_id = rt.id
        elif acc["position"] == "rw":
            user.rw_id = rt.rw_id
    await session.commit()
    logger.info("seed_link_demo_rt_rw complete")


async def seed_approval_steps(session: AsyncSession) -> None:
    """Seed the default 2-step approval chain (staff, admin) for the
    seeded village.

    Note: mockData's SETTINGS.approvalMode='3' (a 3-step staf/sekretaris/
    kades chain) no longer maps 1:1 onto the 4-role catalog -- sekretaris_
    desa and kepala_desa now share the "admin" Role (see Position), so a
    literal 3-distinct-role chain isn't expressible anymore. This seeds the
    2-step chain the new catalog supports (staff, then admin); redesigning
    the approval-chain shape itself belongs to the later Submission/
    Approval/PDF rework part, not this RBAC/Position part.

    Idempotent: skips if the village already has any configured steps.
    """
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        raise RuntimeError("seed_approval_steps requires seed_master to run first")

    existing_count = await session.scalar(
        select(func.count()).select_from(ApprovalStepConfig).where(
            ApprovalStepConfig.village_id == village.id
        )
    )
    if existing_count:
        logger.info("seed_approval_steps: village already configured, skipping")
        return

    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    for index, role_name in enumerate(("staff", "admin")):
        session.add(ApprovalStepConfig(
            village_id=village.id, order_index=index, role_id=roles[role_name].id
        ))
    await session.commit()
    logger.info("seed_approval_steps: seeded 2-step chain for village_id=%s", village.id)


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: positions, RBAC/demo-users, village hierarchy+residents,
    letter templates, demo-resident/RT/RW links, default approval steps."""
    await seed_positions(session)
    await seed_rbac(session)
    await seed_master(session)
    await seed_letter_templates(session)
    await seed_link_demo_resident(session)
    await seed_link_demo_rt_rw(session)
    await seed_approval_steps(session)
