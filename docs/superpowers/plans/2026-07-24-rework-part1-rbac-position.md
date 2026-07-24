# Rework Part 1: RBAC Foundation — Position Dimension Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce the `Position` dimension (jabatan + hierarchy level, separate from
`Role`) alongside the new 4-role catalog (`administrator-it`/`admin`/`staff`/`warga`),
with permission resolution as the union of Role and Position grants — the foundation
every later rework part builds on.

**Architecture:** `Position` + `position_permissions` mirror the existing
`Role`/`role_permissions` pattern exactly (same table shape, same seeding style) so the
RBAC model stays uniformly data-driven. `User` gains `email`, `position_id`, `rt_id`,
`rw_id`, `pending_approval`. `AuthService.permissions_for` becomes a union of
`user.role.permissions` and `user.position.permissions`.

**Tech Stack:** SQLAlchemy Async, Alembic, existing FastAPI app (no new dependencies).

## Global Constraints

- Every schema change goes through a **new** Alembic revision — never edit
  `12b433fe21f8_auth_tables.py` or any other already-applied revision.
- `Position` has **no CRUD API** (fixed reference data, seeded — like `Permission`).
- `position_id`/`rt_id`/`rw_id` on `User` are nullable at the DB level (avoids a
  backfill migration for already-existing rows); application code (later rework parts:
  registration, user management) is responsible for always setting `position_id` for
  real accounts going forward.
- `POSITION_PERMISSIONS` starts **empty for every position** in this part — no
  `lapduk:*` codes exist yet (LAPDUK is a later rework part). The union mechanism must
  work correctly with empty position grants; later parts populate it.
- Role catalog is exactly 4: `administrator-it` (`"*"`), `admin`, `staff`, `warga`.
  Position catalog is exactly 7, with `level` (lower = higher authority):
  `kepala_desa`=1, `sekretaris_desa`=2, `bendahara_desa`=3, `staff_desa`=4, `rw`=5,
  `rt`=6, `warga_desa`=7.
- Demo account usernames `staf`, `warga`, `kades`, `sekdes`, `operator` are reused
  verbatim (existing tests/README/memory reference them) even though their underlying
  `role` value changes — do not rename these usernames.
- `village:manage` permission code and its grant to `admin` are **intentionally kept
  as-is** in this part, even though the rework spec removes multi-desa support — that
  removal (dropping `Village`, the permission code, and the `/villages` endpoints
  together) is a separate, later rework part. Do not remove `village:manage` here.

---

### Task 1: `Position` model + `position_permissions` table

**Files:**
- Modify: `app/models/auth.py`

**Interfaces:**
- Produces: `Position` class (`id`, `slug`, `display_name`, `level`, `permissions`
  relationship), `position_permissions` association table. Both live in
  `app/models/auth.py` (not a separate file) specifically to avoid a circular import
  with `Permission`, which already lives there.

- [ ] **Step 1: Add the `position_permissions` table and `Position` model**

Add this right after the existing `role_permissions` table definition (before the
`Permission` class), reusing the same `Table`/`Column`/`GUID`/`ForeignKey` imports
already present in the file:

```python
position_permissions = Table(
    "position_permissions",
    Base.metadata,
    Column("position_id", GUID(), ForeignKey("positions.id"), primary_key=True),
    Column("permission_id", GUID(), ForeignKey("permissions.id"), primary_key=True),
)
```

Add the `Position` class right after the `Role` class:

```python
class Position(UUIDMixin, TimestampMixin, Base):
    """A jabatan (position): hierarchy level + optional extra permissions.

    Separate dimension from Role -- a user's effective permissions are the
    union of their Role's and their Position's permission rows (see
    ``AuthService.permissions_for``). Fixed reference data, seeded; no CRUD
    API by design (see the rework spec).
    """

    __tablename__ = "positions"
    slug: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(100))
    level: Mapped[int] = mapped_column()
    permissions: Mapped[list[Permission]] = relationship(
        secondary=position_permissions, lazy="selectin"
    )
```

- [ ] **Step 2: Verify the module still imports cleanly**

Run: `python -c "import app.models.auth"`
Expected: no output, exit code 0 (no circular import, no syntax error).

- [ ] **Step 3: Commit**

```bash
git add app/models/auth.py
git commit -m "feat(rbac): add Position model + position_permissions table"
```

---

### Task 2: `User` model — new columns

**Files:**
- Modify: `app/models/auth.py`

**Interfaces:**
- Consumes: `Position` (Task 1, same file — no import needed).
- Produces: `User.email`, `User.position_id`, `User.rt_id`, `User.rw_id`,
  `User.pending_approval`, `User.position` relationship.

- [ ] **Step 1: Add the new columns to `User`**

Insert into the `User` class, after the existing `phone` column and before
`is_active`:

```python
    email: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True)
```

Insert after `resident_id`, before `role: Mapped[Role] = relationship(...)`:

```python
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("positions.id"), nullable=True
    )
    rt_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rt.id"), nullable=True)
    rw_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rw.id"), nullable=True)
    pending_approval: Mapped[bool] = mapped_column(Boolean, default=False)
```

Add the relationship right after the existing `role: Mapped[Role] = relationship(lazy="selectin")`:

```python
    position: Mapped[Position | None] = relationship(lazy="selectin")
```

Full `User` class after this + Task 2 combined should read (for verification, this is
what the class looks like once both tasks are applied — do not paste this as a
replacement, apply the incremental edits above):

```python
class User(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An authenticated principal: staff (username/password) or citizen (NIK/OTP)."""

    __tablename__ = "users"
    username: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True, index=True)
    nik: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150))
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    email: Mapped[str | None] = mapped_column(String(150), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))
    resident_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("residents.id"), nullable=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("positions.id"), nullable=True
    )
    rt_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rt.id"), nullable=True)
    rw_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rw.id"), nullable=True)
    pending_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    role: Mapped[Role] = relationship(lazy="selectin")
    position: Mapped[Position | None] = relationship(lazy="selectin")
```

- [ ] **Step 2: Verify import**

Run: `python -c "import app.models.auth"`
Expected: exit code 0.

- [ ] **Step 3: Commit**

```bash
git add app/models/auth.py
git commit -m "feat(rbac): add email/position_id/rt_id/rw_id/pending_approval to User"
```

---

### Task 3: Alembic migration

**Files:**
- Create: `alembic/versions/<autogenerated_hash>_position_and_user_attrs.py`

**Interfaces:**
- Consumes: `Position`, updated `User` from Tasks 1-2.
- Produces: applied schema on `db_kopo` (tables `positions`, `position_permissions`;
  new `users` columns).

- [ ] **Step 1: Autogenerate the revision**

Run: `alembic revision --autogenerate -m "position and user attrs"`

This creates a new file under `alembic/versions/`. Open it.

- [ ] **Step 2: Add the missing `import app.db.base`**

Autogenerate does not add this import (needed for the custom `GUID` type to resolve
inside the generated file) — same fix pattern used in every prior migration in this
project. Add near the top, alongside the `sqlalchemy as sa` import:

```python
import app.db.base
```

- [ ] **Step 3: Review the generated `upgrade()`/`downgrade()`**

Confirm it creates (in this order, respecting FK dependencies): `positions` table,
`position_permissions` table, then `ALTER TABLE users ADD COLUMN` for `email`,
`position_id`, `rt_id`, `rw_id`, `pending_approval`. If autogenerate emits a NOT NULL
column for `pending_approval` without a default, add `server_default=sa.text('false')`
to that column's `op.add_column` call so the migration succeeds against the existing
non-empty `users` table in `db_kopo`.

- [ ] **Step 4: Apply to `db_kopo`**

Run: `alembic upgrade head`
Expected: no errors; `positions` and `position_permissions` tables exist; `users` has
the 5 new columns.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(rbac): migration for positions + user attribute columns"
```

---

### Task 4: `registry.py` — new role/position catalog

**Files:**
- Modify: `app/permissions/registry.py`

**Interfaces:**
- Produces: `ROLE_DEFS` (4 roles), `ROLE_PERMISSIONS` (4 roles), `POSITION_DEFS` (7
  positions, `(slug, display_name, level)` tuples), `POSITION_PERMISSIONS` (7 positions,
  all empty lists in this part), `DEMO_ACCOUNTS` (8 accounts, each with `role`,
  `position` slug, and — for the two RT/RW demo accounts only — a
  `link_resident_name` used later by seeding to resolve their `rt_id`/`rw_id`).

- [ ] **Step 1: Replace the whole file**

```python
"""Data-driven RBAC registry: permissions, role/position mappings, demo accounts."""

# Resource:action permission codes. Extend as new features arrive.
PERMISSIONS: list[str] = [
    "auth:me",
    "resident:create", "resident:read", "resident:update", "resident:delete",
    "resident:import", "resident:export",
    "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
    "template:manage", "template:read",
    "submission:create", "submission:read", "submission:read_all",
    "submission:approve", "submission:reject", "submission:download",
    "approval_config:manage",
]

# Role name -> permission codes. "*" means all permissions.
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me", "submission:create", "submission:read", "submission:download"],
    "staff": ["auth:me", "resident:read", "resident:create", "resident:update",
              "resident:import", "resident:export", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download"],
    "admin": ["auth:me", "resident:read", "resident:update",
              "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
              "template:manage", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download", "approval_config:manage"],
    "administrator-it": ["*"],
}

ROLE_DEFS: list[tuple[str, str]] = [
    ("warga", "Warga"),
    ("staff", "Staff"),
    ("admin", "Admin"),
    ("administrator-it", "Administrator IT"),
]

# Position slug -> (display_name, level). Lower level = higher authority.
POSITION_DEFS: list[tuple[str, str, int]] = [
    ("kepala_desa", "Kepala Desa", 1),
    ("sekretaris_desa", "Sekretaris Desa", 2),
    ("bendahara_desa", "Bendahara Desa", 3),
    ("staff_desa", "Staff Desa", 4),
    ("rw", "RW", 5),
    ("rt", "RT", 6),
    ("warga_desa", "Warga Desa", 7),
]

# Position slug -> permission codes GRANTED IN ADDITION to the user's Role.
# Empty for every position in this part of the rework -- populated later
# (e.g. the LAPDUK rework part adds "lapduk:manage_own" to "rt" and
# "lapduk:read_rw" to "rw"). Every slug from POSITION_DEFS must have an
# entry here, even if empty, so seeding can always look it up.
POSITION_PERMISSIONS: dict[str, list[str]] = {
    "kepala_desa": [],
    "sekretaris_desa": [],
    "bendahara_desa": [],
    "staff_desa": [],
    "rw": [],
    "rt": [],
    "warga_desa": [],
}

# Demo accounts mirrored from the frontend mockData.js `accounts` map, extended
# with the new role/position dimensions. `link_resident_name` (RT/RW accounts
# only) is resolved to a concrete rt_id/rw_id by seed.seed_link_demo_rt_rw
# once master data (RT/RW rows) exists.
DEMO_ACCOUNTS: list[dict] = [
    {"username": "warga", "password": "warga123", "full_name": "Siti Rohmah",
     "role": "warga", "position": "warga_desa", "nik": "3516064588020003",
     "email": "siti.rohmah@example.test"},
    {"username": "staf", "password": "staf123", "full_name": "Nur Aini",
     "role": "staff", "position": "staff_desa", "nik": None,
     "email": "nur.aini@example.test"},
    {"username": "bendahara", "password": "bendahara123", "full_name": "Bambang Sujarwo",
     "role": "staff", "position": "bendahara_desa", "nik": None,
     "email": "bambang.sujarwo@example.test"},
    {"username": "sekdes", "password": "sekdes123", "full_name": "Dewi Lestari",
     "role": "admin", "position": "sekretaris_desa", "nik": None,
     "email": "dewi.lestari@example.test"},
    {"username": "kades", "password": "kades123", "full_name": "Wiwin Wildan",
     "role": "admin", "position": "kepala_desa", "nik": None,
     "email": "wiwin.wildan@example.test"},
    {"username": "operator", "password": "operator123", "full_name": "Operator IT",
     "role": "administrator-it", "position": None, "nik": None,
     "email": "operator.it@example.test"},
    {"username": "rt001", "password": "rt123", "full_name": "Sugeng Riyadi",
     "role": "warga", "position": "rt", "nik": None,
     "email": "sugeng.riyadi@example.test",
     "link_resident_name": "Sugeng Riyadi"},
    {"username": "rw001", "password": "rw123", "full_name": "Ahmad Fauzi",
     "role": "warga", "position": "rw", "nik": None,
     "email": "ahmad.fauzi@example.test",
     "link_resident_name": "Ahmad Fauzi"},
]
```

- [ ] **Step 2: Verify import**

Run: `python -c "from app.permissions.registry import PERMISSIONS, ROLE_PERMISSIONS, ROLE_DEFS, POSITION_DEFS, POSITION_PERMISSIONS, DEMO_ACCOUNTS; print(len(DEMO_ACCOUNTS))"`
Expected: prints `8`.

- [ ] **Step 3: Commit**

```bash
git add app/permissions/registry.py
git commit -m "feat(rbac): rework role catalog (4 roles) + add Position catalog"
```

---

### Task 5: `AuthService.permissions_for` — union of Role and Position

**Files:**
- Modify: `app/services/auth.py`
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Consumes: `User.position` (Task 2).
- Produces: `AuthService.permissions_for(user) -> list[str]` returning the deduplicated
  union of `user.role.permissions` and (if `user.position` is set)
  `user.position.permissions`.

- [ ] **Step 1: Write the failing test**

First change the existing top-of-file import in `tests/test_auth_service.py` from
`from app.models.auth import Permission, Role` to
`from app.models.auth import Permission, Position, Role` (adds `Position`, keeps the
two existing names).

Then add this test:

```python
@pytest.mark.asyncio
async def test_permissions_for_unions_role_and_position(seeded_session):
    svc = AuthService(seeded_session)
    user = await svc.users.get_by_username("rt001")
    # Position "rt" grants nothing yet in this part of the rework, but the
    # union must still include the user's Role permissions (warga's set).
    perms = svc.permissions_for(user)
    assert "submission:create" in perms

    # Directly attach an extra permission to Position "rt" and confirm the
    # union picks it up without going through the Role at all.
    position = await seeded_session.scalar(
        select(Position).where(Position.slug == "rt")
    )
    extra = Permission(code="lapduk:manage_own")
    seeded_session.add(extra)
    await seeded_session.flush()
    position.permissions.append(extra)
    await seeded_session.commit()
    await seeded_session.refresh(user)
    perms_after = svc.permissions_for(user)
    assert "lapduk:manage_own" in perms_after
    assert "submission:create" in perms_after  # role grant still present
```

- [ ] **Step 2: Run it, confirm it fails**

Run: `pytest tests/test_auth_service.py::test_permissions_for_unions_role_and_position -v`
Expected: FAIL (`user` is `None` — `seed_rbac` doesn't create `rt001` yet; this will
be resolved once Task 6 lands `seed_positions`/updated `seed_rbac`. Note this test as
depending on Task 6 and re-run it once that task is also done — do not treat this as
a Task 5 failure if the only failure reason is the missing seeded user).

Given the dependency, implement Task 5's production code now (Step 3) and defer this
specific test's green run to immediately after Task 6, in the same PR/commit sequence
— the task reviewer for Task 6 should confirm this test passes.

- [ ] **Step 3: Implement the union**

In `app/services/auth.py`, replace `permissions_for`:

```python
    def permissions_for(self, user: User) -> list[str]:
        """Resolve effective permission codes for a user: Role ∪ Position.

        Purely data-driven from the database: whatever permission rows are
        assigned to the user's role (including a literal ``"*"`` row for
        wildcard roles) and, if set, the user's position, are unioned and
        returned. Order is not significant; duplicates are removed.
        """
        codes = {p.code for p in user.role.permissions}
        if user.position is not None:
            codes.update(p.code for p in user.position.permissions)
        return list(codes)
```

- [ ] **Step 4: Commit**

```bash
git add app/services/auth.py tests/test_auth_service.py
git commit -m "feat(rbac): permissions_for unions Role and Position grants"
```

---

### Task 6: `seed.py` — `seed_positions` + updated `seed_rbac` + RT/RW demo linking

**Files:**
- Modify: `app/seed/seed.py`

**Interfaces:**
- Consumes: `POSITION_DEFS`, `POSITION_PERMISSIONS`, `DEMO_ACCOUNTS` (Task 4).
- Produces: `seed_positions(session)`, updated `seed_rbac(session)`,
  `seed_link_demo_rt_rw(session)`. `seed_all` calls all three (positions before rbac,
  rt/rw linking after `seed_master`).

- [ ] **Step 1: Add imports**

At the top of `app/seed/seed.py`, update the registry import and add `Position`:

```python
from app.models.auth import Permission, Position, Role, User
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, POSITION_DEFS, POSITION_PERMISSIONS,
    ROLE_DEFS, ROLE_PERMISSIONS,
)
```

- [ ] **Step 2: Add `seed_positions`**

Insert a new function before `seed_rbac`:

```python
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
```

- [ ] **Step 3: Update `seed_rbac` to set `email`/`position_id` on demo users**

Replace the "Demo users" block inside `seed_rbac` (the `for acc in DEMO_ACCOUNTS:` loop)
with:

```python
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
```

Note: this requires `seed_positions` to have already run in the same session before
`seed_rbac` (so `existing_positions` is non-empty) — enforced by the `seed_all` order
in Step 5.

- [ ] **Step 4: Add `seed_link_demo_rt_rw`**

Insert after the existing `seed_link_demo_resident` function:

```python
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
```

This needs `RT` imported — add it to the existing
`from app.models.master import RT, RW, Dusun, Resident, Village` import line (already
present; `RT` and `Resident` are already imported, no change needed there).

- [ ] **Step 5: Update `seed_all`**

```python
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
```

- [ ] **Step 6: Run the previously-deferred Task 5 test**

Run: `pytest tests/test_auth_service.py::test_permissions_for_unions_role_and_position -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add app/seed/seed.py
git commit -m "feat(rbac): seed Position catalog + demo user position/email/rt/rw links"
```

---

### Task 7: Fix tests broken by the role-catalog rename

**Files:**
- Modify: `tests/test_permissions_registry.py`
- Test (search, no dedicated new file): any other test file referencing the old role
  names (`"sekretaris"`, `"kades"`, `"staf"` as a role — NOT as a username, which stays
  `"staf"`/`"kades"`/`"sekdes"` — and `"administrator"`)

- [ ] **Step 1: Search for old role-name references**

Run: `grep -rn '"sekretaris"\|"kades"\|"administrator"' tests/ app/ --include=*.py`

(Note: `"staf"` alone is ambiguous — it's both an old role name AND the demo
*username*, which is unchanged. Only fix occurrences that are clearly using it as a
**role** value, e.g. `ROLE_PERMISSIONS["staf"]`, `role.name == "staf"`. Do not touch
`DEMO_ACCOUNTS`/`get_by_username("staf")`/login test calls using `"staf"` as a
username+password pair.)

For each hit outside `app/permissions/registry.py` and `app/seed/seed.py` (already
handled in Tasks 4/6), update to the new role slugs: `"sekretaris"` → not applicable
(role removed; positions `sekretaris_desa`/`kepala_desa` now share role `"admin"`),
`"kades"` → `"admin"` (or check position via `user.position.slug == "kepala_desa"` if
the test's intent was specifically Kepala Desa, not just "an admin-role user"),
`"administrator"` → `"administrator-it"`.

- [ ] **Step 2: Rewrite `tests/test_permissions_registry.py`**

```python
from app.permissions.registry import (
    DEMO_ACCOUNTS, PERMISSIONS, POSITION_DEFS, POSITION_PERMISSIONS,
    ROLE_DEFS, ROLE_PERMISSIONS,
)


def test_registry_shapes():
    assert "resident:create" in PERMISSIONS
    assert set(ROLE_PERMISSIONS) == {"warga", "staff", "admin", "administrator-it"}
    assert ROLE_PERMISSIONS["administrator-it"] == ["*"]
    assert {r[0] for r in ROLE_DEFS} == set(ROLE_PERMISSIONS)
    usernames = {a["username"] for a in DEMO_ACCOUNTS}
    assert {"warga", "staf", "bendahara", "sekdes", "kades", "operator", "rt001", "rw001"} == usernames


def test_position_shapes():
    assert {p[0] for p in POSITION_DEFS} == {
        "kepala_desa", "sekretaris_desa", "bendahara_desa", "staff_desa", "rw", "rt", "warga_desa",
    }
    assert set(POSITION_PERMISSIONS) == {p[0] for p in POSITION_DEFS}
    levels = {slug: level for slug, _, level in POSITION_DEFS}
    assert levels["kepala_desa"] < levels["sekretaris_desa"] < levels["bendahara_desa"]
    assert levels["bendahara_desa"] < levels["staff_desa"] < levels["rw"] < levels["rt"] < levels["warga_desa"]


def test_template_permissions_registered():
    assert "template:manage" in PERMISSIONS
    assert "template:read" in PERMISSIONS
    assert "template:read" in ROLE_PERMISSIONS["staff"]
    assert "template:manage" in ROLE_PERMISSIONS["admin"]


def test_submission_permissions_registered():
    for code in (
        "submission:create", "submission:read", "submission:read_all",
        "submission:approve", "submission:reject", "submission:download",
        "approval_config:manage",
    ):
        assert code in PERMISSIONS
    assert ROLE_PERMISSIONS["warga"] == [
        "auth:me", "submission:create", "submission:read", "submission:download",
    ]
    for role in ("staff", "admin"):
        for code in (
            "submission:read", "submission:read_all", "submission:approve",
            "submission:reject", "submission:download",
        ):
            assert code in ROLE_PERMISSIONS[role]
```

- [ ] **Step 3: Run the full test suite**

Run: `pytest -v`
Expected: identify every remaining failure caused by the role-catalog rename (likely
in `tests/test_auth.py`, `tests/test_auth_models.py`, `tests/test_seed_master.py`, any
API test logging in as `"sekdes"`/`"kades"` and asserting on `role` in the response).
Fix each by updating the expected role string to the new catalog (`"admin"` for
kades/sekdes logins, `"administrator-it"` for operator, `"staff"` for staf/bendahara).
Do not change assertions unrelated to role naming.

- [ ] **Step 4: Confirm everything passes**

Run: `pytest -v`
Expected: all tests PASS, 0 failures.

Run: `ruff check app tests`
Expected: no errors.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "test(rbac): fix tests for new 4-role catalog + Position"
```

---

### Task 8: Live verification against `db_kopo` + README note

**Files:**
- Modify: `README.md` (Demo Accounts table)

**Interfaces:**
- None (verification + docs task).

- [ ] **Step 1: Re-seed live `db_kopo`**

Run: `python -m app.seed`
Expected: `Seeding complete.` — creates 7 `positions` rows, 8 demo users (5 previously
existing usernames now carry updated role/position/email; 3 new: `bendahara`, `rt001`,
`rw001`), `rt001`/`rw001` have non-null `rt_id`/`rw_id` after the RT/RW link step.

- [ ] **Step 2: Spot-check via psql or a quick script**

Run (adjust connection string to match local `db_kopo`):
```bash
python -c "
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.auth import User

async def main():
    async with AsyncSessionLocal() as s:
        for username in ('kades', 'sekdes', 'staf', 'bendahara', 'operator', 'rt001', 'rw001', 'warga'):
            u = await s.scalar(select(User).where(User.username == username))
            print(username, u.role.name, u.position.slug if u.position else None, u.rt_id, u.rw_id)

asyncio.run(main())
"
```
Expected: `kades`/`sekdes` show role `admin` with position `kepala_desa`/`sekretaris_desa`
respectively; `staf` shows `staff`/`staff_desa`; `bendahara` shows `staff`/`bendahara_desa`;
`operator` shows `administrator-it`/`None`; `rt001` shows `warga`/`rt` with a non-null
`rt_id`; `rw001` shows `warga`/`rw` with a non-null `rw_id`; `warga` shows `warga`/`warga_desa`.

If `AsyncSessionLocal` isn't the actual exported session-maker name, check
`app/db/session.py` for the correct name and adjust the script — do not skip this
verification.

- [ ] **Step 3: Update README's Demo Accounts table**

Replace the table in `README.md` under "## Demo Accounts" with:

```markdown
| Username    | Password        | Role              | Position          | Notes |
|-------------|------------------|-------------------|--------------------|-------|
| `warga`     | `warga123`      | Warga             | Warga Desa         | NIK `3516064588020003` |
| `staf`      | `staf123`       | Staff             | Staff Desa         | password login |
| `bendahara` | `bendahara123`  | Staff             | Bendahara Desa     | password login |
| `sekdes`    | `sekdes123`     | Admin             | Sekretaris Desa    | password login, final approval |
| `kades`     | `kades123`      | Admin             | Kepala Desa        | password login, final approval |
| `operator`  | `operator123`   | Administrator IT  | — | password login, full permissions |
| `rt001`     | `rt123`         | Warga             | RT                 | password login, linked to an RT |
| `rw001`     | `rw123`         | Warga             | RW                 | password login, linked to an RW |
```

(Leave the surrounding login-flow prose as-is for now — OTP login is removed in a
later rework part, not this one; do not edit that paragraph yet.)

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update demo accounts table for Role+Position rework"
```
