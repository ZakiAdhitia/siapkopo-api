"""Idempotent database seeding."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.auth import Position, Role, User
from app.models.letter_template import (
    FieldType,
    LetterOutputCategory,
    LetterTemplate,
    TemplateField,
)
from app.models.master import RT, RW
from app.permissions.registry import DEMO_ACCOUNTS, POSITION_DEFS, ROLE_DEFS
from app.seed.data import RW_RT_PAIRS
from app.seed.letter_template_data import SURAT_TEMPLATES

logger = get_logger("seed")


async def seed_positions(session: AsyncSession) -> None:
    """Seed the fixed Position catalog (jabatan + hierarchy level).

    Idempotent: looks up existing positions by slug before inserting.
    Permissions are resolved purely from ``app.permissions.registry`` at
    read time (``AuthService.permissions_for``), not stored here.
    """
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
    await session.commit()
    logger.info("seed_positions complete: %d positions", len(existing_positions))


async def seed_rbac(session: AsyncSession) -> None:
    """Seed roles and demo users. Permissions are resolved purely from
    ``app.permissions.registry`` at read time (``AuthService.permissions_for``),
    not stored in the database."""
    existing_roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    for name, display in ROLE_DEFS:
        role = existing_roles.get(name)
        if role is None:
            role = Role(name=name, display_name=display)
            session.add(role)
            existing_roles[name] = role
    await session.flush()

    # Demo users: create or update with latest role/position/email from DEMO_ACCOUNTS
    #
    # NOTE (matches purely by username): this looks up existing users by
    # `acc["username"]` alone. Today that's safe because there is no
    # self-registration endpoint -- every user row in the DB was put there
    # by this seed script or by an admin, so a username collision with
    # DEMO_ACCOUNTS can only mean "this is the demo account". Once
    # self-registration exists (a later rework part, not built yet), a real
    # citizen could register with a username that happens to collide with a
    # DEMO_ACCOUNTS entry (e.g. "staf", "warga", or an "admin"-ish name),
    # and re-running this seed would silently overwrite that real user's
    # role/position/email with demo values. Not exploitable today -- but
    # this must be revisited when self-registration ships (e.g. scope the
    # match/seed to a reserved namespace or flag), not forgotten.
    existing_users = {u.username: u for u in (await session.scalars(select(User))).all()}
    existing_positions = {p.slug: p for p in (await session.scalars(select(Position))).all()}
    for acc in DEMO_ACCOUNTS:
        position_id = (
            existing_positions[acc["position"]].id if acc["position"] else None
        )
        user = existing_users.get(acc["username"])
        if user is None:
            # Create new user
            session.add(User(
                username=acc["username"], full_name=acc["full_name"],
                hashed_password=hash_password(acc["password"]), email=acc["email"],
                role_id=existing_roles[acc["role"]].id, position_id=position_id,
                is_active=True,
            ))
        else:
            # Update existing user with new role/position/email. Deliberately
            # NOT touching hashed_password/full_name here: a re-seed must
            # never reset a password someone changed, nor rename/reactivate
            # a user outside the demo-data contract -- only role/position/
            # email are considered "managed" by DEMO_ACCOUNTS on update.
            user.role_id = existing_roles[acc["role"]].id
            user.position_id = position_id
            user.email = acc["email"]
    await session.commit()
    logger.info("seed_rbac complete: %d roles, %d demo users",
                len(existing_roles), len(DEMO_ACCOUNTS))


async def seed_master(session: AsyncSession) -> None:
    """Seed the RW/RT hierarchy from RW_RT_PAIRS.

    2026-08-06: no more Resident population registry (couldn't be kept up
    to date, see SISTEM_PENGOLAHAN_DATA_WARGA.md) -- this now seeds RW/RT
    directly instead of as a side effect of iterating resident rows.
    Idempotent: re-running skips any RW/RT that already exists.
    """
    rw_map = {rw.number: rw for rw in (await session.scalars(select(RW))).all()}
    existing_rt = {(rt.rw_id, rt.number) for rt in (await session.scalars(select(RT))).all()}
    created = 0
    for rw_no, rt_no in RW_RT_PAIRS:
        rw = rw_map.get(rw_no)
        if rw is None:
            rw = RW(number=rw_no)
            session.add(rw)
            await session.flush()
            rw_map[rw_no] = rw
        if (rw.id, rt_no) in existing_rt:
            continue
        session.add(RT(rw_id=rw.id, number=rt_no))
        existing_rt.add((rw.id, rt_no))
        created += 1
    await session.commit()
    logger.info("seed_master complete: %d RT created (%d RW total)", created, len(rw_map))


async def seed_letter_templates(session: AsyncSession) -> None:
    """Seed the 9 letter templates (with fields) from mockData's suratTypes.

    Idempotent: skips any template whose code already exists.
    """
    existing = {
        t.code for t in (await session.scalars(select(LetterTemplate))).all()
    }
    created = 0
    for entry in SURAT_TEMPLATES:
        if entry["code"] in existing:
            continue
        template = LetterTemplate(
            code=entry["code"],
            name=entry["name"],
            description=entry["description"],
            icon=entry["icon"],
            color_bg=entry["color_bg"],
            color_fg=entry["color_fg"],
            is_active=entry.get("is_active", True),
            required_documents=entry["required_documents"],
            optional_documents=entry.get("optional_documents", []),
            numbering_prefix=entry["numbering_prefix"],
            numbering_pattern=entry.get("numbering_pattern", "{prefix}/{seq}/Ds.Kopo/{year}"),
            pdf_body_template=entry["pdf_body_template"],
            output_category=LetterOutputCategory(entry["output_category"]),
            category_field_key=entry.get("category_field_key"),
            required_documents_by_category=entry.get("required_documents_by_category"),
            post_issuance_note=entry.get("post_issuance_note"),
            sub_documents=entry.get("sub_documents"),
        )
        session.add(template)
        await session.flush()
        for order_index, field_tuple in enumerate(entry["fields"]):
            # 8th element (is_staff_only) is optional -- defaults False, so
            # every pre-existing 7-tuple field definition still works as-is.
            key, label, ftype, options, placeholder, required, rules, *rest = field_tuple
            session.add(TemplateField(
                template_id=template.id, order_index=order_index, field_key=key,
                label=label, field_type=FieldType(ftype), options=options,
                placeholder=placeholder, is_required=required, validation_rules=rules,
                is_staff_only=rest[0] if rest else False,
            ))
        created += 1
    await session.commit()
    logger.info("seed_letter_templates complete: %d templates created (%d already present)",
                created, len(existing))


async def sync_letter_template_fields(session: AsyncSession) -> None:
    """Keep already-seeded templates' fields in sync with
    `letter_template_data.py` for templates created before a source edit
    (2026-08-05, HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md fixes) -- unlike
    `seed_letter_templates` (whole-template create-once), this updates each
    existing field's label/is_required/validation_rules/options/placeholder
    by `field_key` match, and adds any field newly present in the source
    that an existing template doesn't have yet. Never deletes a field, so
    it can't orphan an existing submission's `answers`. Also refreshes
    `pdf_body_template` and (2026-08-13, HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md
    round) the template-level attachment configuration
    (required_documents/optional_documents/category_field_key/
    required_documents_by_category) -- these used to be silently ignored on
    re-seed (only set once by `seed_letter_templates` at template creation),
    so editing e.g. NA's `_NA_WAJIB` list in source never reached an
    already-seeded dev DB until now.
    """
    updated_fields = 0
    added_fields = 0
    updated_templates = 0
    for entry in SURAT_TEMPLATES:
        template = await session.scalar(
            select(LetterTemplate).where(LetterTemplate.code == entry["code"])
        )
        if template is None:
            continue
        template_changed = False
        if template.pdf_body_template != entry["pdf_body_template"]:
            template.pdf_body_template = entry["pdf_body_template"]
            template_changed = True
        entry_optional_documents = entry.get("optional_documents", [])
        entry_category_field_key = entry.get("category_field_key")
        entry_required_documents_by_category = entry.get("required_documents_by_category")
        if (template.required_documents, template.optional_documents,
                template.category_field_key, template.required_documents_by_category) != (
                entry["required_documents"], entry_optional_documents,
                entry_category_field_key, entry_required_documents_by_category):
            template.required_documents = entry["required_documents"]
            template.optional_documents = entry_optional_documents
            template.category_field_key = entry_category_field_key
            template.required_documents_by_category = entry_required_documents_by_category
            template_changed = True
        if template_changed:
            updated_templates += 1
        existing_fields = {
            f.field_key: f for f in (await session.scalars(
                select(TemplateField).where(TemplateField.template_id == template.id)
            )).all()
        }
        for order_index, field_tuple in enumerate(entry["fields"]):
            key, label, ftype, options, placeholder, required, rules, *rest = field_tuple
            is_staff_only = rest[0] if rest else False
            existing = existing_fields.get(key)
            if existing is None:
                session.add(TemplateField(
                    template_id=template.id, order_index=order_index, field_key=key,
                    label=label, field_type=FieldType(ftype), options=options,
                    placeholder=placeholder, is_required=required, validation_rules=rules,
                    is_staff_only=is_staff_only,
                ))
                added_fields += 1
                continue
            if (existing.label, existing.field_type, existing.is_required, existing.validation_rules,
                    existing.options, existing.placeholder, existing.is_staff_only) \
                    != (label, FieldType(ftype), required, rules, options, placeholder, is_staff_only):
                existing.label = label
                existing.field_type = FieldType(ftype)
                existing.is_required = required
                existing.validation_rules = rules
                existing.options = options
                existing.placeholder = placeholder
                existing.is_staff_only = is_staff_only
                updated_fields += 1
    await session.commit()
    logger.info(
        "sync_letter_template_fields complete: %d templates refreshed, %d fields updated, %d fields added",
        updated_templates, updated_fields, added_fields,
    )


async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: positions, RBAC/demo-users, master data, letter
    templates. (Village identity is hardcoded, not seeded -- see
    app.models.master.VillageProfile.)"""
    await seed_positions(session)
    await seed_rbac(session)
    await seed_master(session)
    await seed_letter_templates(session)
    await sync_letter_template_fields(session)
