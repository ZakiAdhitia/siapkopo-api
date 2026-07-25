# Rework Part 5: User & Position Management

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `admin`/`administrator-it` can list/create/update/soft-delete user accounts and assign any Position (including `kepala_desa`/`sekretaris_desa`/`bendahara_desa`, which self-registration cannot choose), gated by a numeric position-authority hierarchy rule; and can approve/reject the `pending_approval=true` accounts self-registration (Part 3) creates for `staff`/`rt`/`rw`.

**Architecture:** New `UserManagementService` (business logic + hierarchy enforcement) + new `app/api/v1/users.py` router, following the exact CRUD-router shape already used by `app/api/v1/master.py`. No new tables. No changes to `AuthService`/`app/services/auth.py` — self-registration (Part 3) is untouched; this is a separate, admin-only path onto the same `User`/`Position`/`Role` tables.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2.

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-07-24-fitur-adjustment-rework-design.md` Bagian 3 and 8.
- Hierarchy rule (Bagian 8, verbatim): "actor hanya boleh CRUD target dengan `level` **lebih besar** (otoritas lebih rendah) dari `level` miliknya. Perbandingan numerik murni, tidak hardcode nama posisi." Lower numeric `level` = higher authority (`kepala_desa`=1 is the highest).
- No hardcoded `if role == "..."` / `if position == "..."` checks anywhere in authorization logic (CLAUDE.md). A fixed reference-data lookup table (like the existing `AuthService._POSITION_CHOICE_MAP`) is NOT the same thing as a hardcoded branch and is the established pattern for position→role assignment — reuse that pattern here, do not invent an `if`/`elif` chain.
- `administrator-it` (permission `"*"`) is unrestricted by the hierarchy rule — it has no position ceiling.
- Async only, no business logic in routers, all endpoints keep a response model, UTC timestamps, soft delete via `deleted_at` (never a hard DELETE).
- Run `pytest` and `ruff check app tests` at the end of every task; all must pass before commit.

---

### Task 1: `UserManagementService` — hierarchy enforcement, CRUD, approve/reject

**Files:**
- Create: `app/services/user_management.py`
- Create: `app/schemas/user_management.py`
- Modify: `app/permissions/registry.py`
- Create: `tests/test_user_management_service.py`

**Interfaces:**
- Produces: `UserManagementService(session).list(actor, actor_permissions, page, size, position_id, search, include_warga) -> tuple[list[User], int]`
- Produces: `UserManagementService(session).get_or_404(id_) -> User`
- Produces: `UserManagementService(session).create(actor, actor_permissions, data: dict) -> User`
- Produces: `UserManagementService(session).update(actor, actor_permissions, target_id, data: dict) -> User`
- Produces: `UserManagementService(session).delete(actor, actor_permissions, target_id) -> None`
- Produces: `UserManagementService(session).approve(actor, actor_permissions, target_id) -> User`
- Produces: `UserManagementService(session).reject(actor, actor_permissions, target_id) -> None`
- Produces: `app.services.user_management.POSITION_ROLE_MAP: dict[str, str]` (position slug → role name)
- Produces: schemas `UserCreate`, `UserUpdate`, `UserRead` in `app/schemas/user_management.py`
- Consumed by: Task 2's router.

- [ ] **Step 1: Add the `user:manage` permission**

In `app/permissions/registry.py`, add `"user:manage"` to the `PERMISSIONS` list, and add `"user:manage"` to `ROLE_PERMISSIONS["admin"]`'s list (do NOT add it to `"staff"` or `"warga"` — only `admin` and the `"*"` wildcard on `administrator-it` may manage users, per spec Bagian 8). `seed_rbac` (in `app/seed/seed.py`) already unions `PERMISSIONS` with every role's permission list and re-syncs `role.permissions` on every run, so no other seed change is needed for this step.

- [ ] **Step 2: Write the failing service tests**

Create `tests/test_user_management_service.py`. Use the `seeded_session` fixture (seeds positions + RBAC + demo accounts — see `tests/conftest.py`) as your starting point; look at `tests/test_auth_service.py` for the house style of fetching a seeded demo user by username (`select(User).where(User.username == "kades")`) and building `actor_permissions` via `AuthService(session).permissions_for(actor)`.

Cover at minimum (write these as real async test functions, not placeholders):
1. `create()`: kades (position `kepala_desa`, level 1) creates a new user with `position_choice`-equivalent `position_id` = the `bendahara_desa` position (level 3) → succeeds, returned user has `role.name == "staff"` (via `POSITION_ROLE_MAP`) and `is_active=True, pending_approval=False`.
2. `create()`: sekdes (level 2) attempts to create a user with position `kepala_desa` (level 1, numerically HIGHER authority than sekdes's own) → raises `ForbiddenError`.
3. `create()`: username/email uniqueness both raise `ConflictError`.
4. `create()` with `position_id` = `rt`'s position but no `rt_id` in the data → raises `ValidationAppError`; with a non-existent `rt_id` → also raises `ValidationAppError`.
5. `update()`: kades (level 1) can update sekdes (level 2) — e.g. change `full_name` — succeeds.
6. `update()`: sekdes (level 2) attempts to update kades (level 1) → raises `ForbiddenError` (hierarchy is NOT symmetric even though both share the `admin` Role — this is the key spec assertion: hierarchy is purely position-level, independent of Role).
7. `update()`: kades attempts to change a target's `position_id` to a position with `level <= kades.position.level` (e.g. tries to promote someone to `kepala_desa` or `sekretaris_desa`) → raises `ForbiddenError`.
8. `delete()`: soft-deletes (assert `deleted_at is not None` after; assert `get_or_404` on that id now raises `NotFoundError`).
9. `list()`: with `include_warga=False` (default), a user whose position is `warga_desa` does not appear; with `include_warga=True`, it does.
10. `list()`: `search="kades"` returns the kades demo user (matches on `full_name`/`username`/`nik`, case-insensitive).
11. `approve()`: create a `pending_approval=True` user directly via the ORM (mirrors what `AuthService.register` produces for a `staff`/`rt`/`rw` choice — set `is_active=False, pending_approval=True`), have kades approve it → `is_active=True, pending_approval=False`.
12. `approve()`/`reject()` on a user whose `pending_approval` is already `False` → raises `ValidationAppError`.
13. `administrator-it` (the seeded `operator` demo account, `position=None`, permission `"*"`) can create/update/delete/approve a user at ANY position level, including `kepala_desa` — the unrestricted-actor bypass works even though `operator.position is None`.

Run: `pytest tests/test_user_management_service.py -v`
Expected: FAIL with `ModuleNotFoundError`/`ImportError` (the service doesn't exist yet) — confirms the tests target the right (not-yet-existing) module.

- [ ] **Step 3: Write `app/schemas/user_management.py`**

```python
"""Schemas for admin-driven user & position management (Bagian 8)."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.auth import _validate_email_format


class UserCreate(BaseModel):
    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    email: str
    position_id: UUID
    nik: str | None = Field(default=None, min_length=8, max_length=20)
    phone: str | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    resident_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validate_email_format(v)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=150)
    email: str | None = None
    phone: str | None = None
    password: str | None = Field(default=None, min_length=6)
    position_id: UUID | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str | None) -> str | None:
        return v if v is None else _validate_email_format(v)


class UserRead(BaseModel):
    id: UUID
    username: str | None = None
    nik: str | None = None
    full_name: str
    email: str | None = None
    phone: str | None = None
    is_active: bool
    pending_approval: bool
    role_id: UUID
    role_name: str
    position_id: UUID | None = None
    position_name: str | None = None
    position_level: int | None = None
    resident_id: UUID | None = None
    rt_id: UUID | None = None
    rw_id: UUID | None = None
    created_at: datetime
```

(`_validate_email_format` already exists in `app/schemas/auth.py` — import it rather than duplicating it, matching the "DRY" project rule.)

- [ ] **Step 4: Write `app/services/user_management.py`**

```python
"""User & Position management: admin-driven CRUD over accounts, with
position-authority hierarchy enforcement (rework Part 5, spec Bagian 8)."""
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.auth import Position, Role, User
from app.models.master import RT, RW
from app.repositories.base import BaseRepository

logger = get_logger("user_management")

# Position slug -> Role name assigned when a position is set through admin
# user-management. A fixed reference-data mapping (same pattern as
# AuthService._POSITION_CHOICE_MAP), not a runtime hardcoded branch --
# CLAUDE.md's "no hardcoded role/position checks" rule targets `if role ==
# "..."` authorization branches, not a static lookup table like this.
POSITION_ROLE_MAP: dict[str, str] = {
    "kepala_desa": "admin",
    "sekretaris_desa": "admin",
    "bendahara_desa": "staff",
    "staff_desa": "staff",
    "rw": "warga",
    "rt": "warga",
    "warga_desa": "warga",
}


class UserManagementService:
    """CRUD over User accounts with position-level hierarchy enforcement."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, User)

    async def _authorize_against_level(
        self, actor: User, actor_permissions: list[str], target_level: int
    ) -> None:
        """Enforce: actor may only act on a target whose position `level` is
        STRICTLY GREATER (lower authority) than the actor's own.

        `"*"` (administrator-it) bypasses this entirely. A target/actor with
        no position (`position is None`) is treated as level 0 -- the
        highest possible authority -- so only an unrestricted actor can
        manage a position-less account, and a position-less actor can never
        pass this check for anyone.
        """
        if "*" in actor_permissions:
            return
        if actor.position is None:
            raise ForbiddenError("Akun Anda tidak memiliki jabatan, tidak dapat mengelola user")
        if actor.position.level >= target_level:
            raise ForbiddenError("Anda tidak berwenang mengelola user dengan jabatan ini")

    async def _resolve_position(self, position_id: uuid.UUID) -> Position:
        position = await self.session.get(Position, position_id)
        if position is None:
            raise ValidationAppError("Posisi tidak ditemukan")
        return position

    async def _resolve_role_for_position(self, position: Position) -> Role:
        role_name = POSITION_ROLE_MAP[position.slug]
        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise ValidationAppError(f"Role '{role_name}' belum di-seed")
        return role

    async def get_or_404(self, id_: uuid.UUID) -> User:
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("User tidak ditemukan")
        return obj

    async def list(
        self, page: int, size: int, position_id: uuid.UUID | None,
        search: str | None, include_warga: bool,
    ) -> tuple[list[User], int]:
        """List users, sorted by position level then name, paginated.

        No hierarchy filtering here -- any actor with `user:manage` may see
        the full roster; the hierarchy rule only gates mutation (create/
        update/delete/approve/reject).
        """
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .outerjoin(Position, User.position_id == Position.id)
        )
        if position_id is not None:
            stmt = stmt.where(User.position_id == position_id)
        if not include_warga:
            stmt = stmt.where(or_(Position.slug.is_(None), Position.slug != "warga_desa"))
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(term), User.username.ilike(term), User.nik.ilike(term))
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = (
            stmt.order_by(Position.level.asc(), User.full_name.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def create(
        self, actor: User, actor_permissions: list[str], data: dict[str, Any]
    ) -> User:
        position = await self._resolve_position(data["position_id"])
        await self._authorize_against_level(actor, actor_permissions, position.level)

        username = data["username"].strip().lower()
        if await self.session.scalar(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        ):
            raise ConflictError("Username sudah digunakan")
        if await self.session.scalar(
            select(User).where(User.email == data["email"], User.deleted_at.is_(None))
        ):
            raise ConflictError("Email sudah digunakan")

        rt_id, rw_id = None, None
        if position.slug == "rt":
            if not data.get("rt_id"):
                raise ValidationAppError("rt_id wajib diisi untuk posisi RT")
            rt = await self.session.get(RT, data["rt_id"])
            if rt is None:
                raise ValidationAppError("RT tidak ditemukan")
            rt_id = rt.id
        elif position.slug == "rw":
            if not data.get("rw_id"):
                raise ValidationAppError("rw_id wajib diisi untuk posisi RW")
            rw = await self.session.get(RW, data["rw_id"])
            if rw is None:
                raise ValidationAppError("RW tidak ditemukan")
            rw_id = rw.id

        role = await self._resolve_role_for_position(position)
        user = User(
            username=username, nik=data.get("nik"), full_name=data["full_name"],
            hashed_password=hash_password(data["password"]), email=data["email"],
            phone=data.get("phone"), role_id=role.id, position_id=position.id,
            resident_id=data.get("resident_id"), rt_id=rt_id, rw_id=rw_id,
            is_active=True, pending_approval=False,
        )
        # See AuthService.register's identical comment: a freshly constructed
        # instance has unloaded lazy="selectin" relationships, so assign the
        # already-fetched ORM objects directly to avoid a MissingGreenlet on
        # the first synchronous `.role`/`.position` access after this returns.
        user.role = role
        user.position = position
        self.session.add(user)
        await self.session.commit()
        logger.info(
            "User created by admin actor_id=%s new_user_id=%s position=%s",
            actor.id, user.id, position.slug,
        )
        return user

    async def update(
        self, actor: User, actor_permissions: list[str],
        target_id: uuid.UUID, data: dict[str, Any],
    ) -> User:
        target = await self.get_or_404(target_id)
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)

        if "email" in data and data["email"] is not None:
            existing = await self.session.scalar(
                select(User).where(
                    User.email == data["email"], User.id != target.id,
                    User.deleted_at.is_(None),
                )
            )
            if existing:
                raise ConflictError("Email sudah digunakan")
            target.email = data["email"]
        if data.get("full_name") is not None:
            target.full_name = data["full_name"]
        if data.get("phone") is not None:
            target.phone = data["phone"]
        if data.get("password"):
            target.hashed_password = hash_password(data["password"])
        if data.get("is_active") is not None:
            target.is_active = data["is_active"]

        if data.get("position_id") is not None:
            new_position = await self._resolve_position(data["position_id"])
            await self._authorize_against_level(actor, actor_permissions, new_position.level)
            new_role = await self._resolve_role_for_position(new_position)
            target.position = new_position
            target.position_id = new_position.id
            target.role = new_role
            target.role_id = new_role.id

        if "rt_id" in data:
            target.rt_id = data["rt_id"]
        if "rw_id" in data:
            target.rw_id = data["rw_id"]

        await self.session.commit()
        logger.info("User updated by admin actor_id=%s target_id=%s", actor.id, target.id)
        return target

    async def delete(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> None:
        target = await self.get_or_404(target_id)
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("User soft-deleted by admin actor_id=%s target_id=%s", actor.id, target.id)

    async def approve(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> User:
        target = await self.get_or_404(target_id)
        if not target.pending_approval:
            raise ValidationAppError("User ini tidak sedang menunggu approval")
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.is_active = True
        target.pending_approval = False
        await self.session.commit()
        logger.info("Registration approved by actor_id=%s target_id=%s", actor.id, target.id)
        return target

    async def reject(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> None:
        target = await self.get_or_404(target_id)
        if not target.pending_approval:
            raise ValidationAppError("User ini tidak sedang menunggu approval")
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Registration rejected by actor_id=%s target_id=%s", actor.id, target.id)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/test_user_management_service.py -v`
Expected: PASS, all 13+ cases green.

Run the full suite to check nothing else broke: `pytest -v`
Expected: PASS.

- [ ] **Step 6: Ruff + commit**

Run: `ruff check app/services/user_management.py app/schemas/user_management.py app/permissions/registry.py tests/test_user_management_service.py`
Expected: no errors.

```bash
git add app/services/user_management.py app/schemas/user_management.py app/permissions/registry.py tests/test_user_management_service.py
git commit -m "feat(users): UserManagementService with position-hierarchy enforcement"
```

---

### Task 2: `/users` router — CRUD, filters, approve/reject endpoints

**Files:**
- Create: `app/api/v1/users.py`
- Modify: `app/api/v1/__init__.py`
- Create: `tests/test_users_api.py`

**Interfaces:**
- Consumes: Task 1's `UserManagementService`, `UserCreate`/`UserUpdate`/`UserRead`.
- Produces: `router` (APIRouter) registered into `api_router`, exposing:
  - `POST /users` (permission `user:manage`)
  - `GET /users?page=&size=&position_id=&search=&include_warga=&pending_approval=` (permission `user:manage`)
  - `GET /users/{item_id}` (permission `user:manage`)
  - `PUT /users/{item_id}` (permission `user:manage`)
  - `DELETE /users/{item_id}` (permission `user:manage`)
  - `POST /users/{item_id}/approve` (permission `user:manage`)
  - `POST /users/{item_id}/reject` (permission `user:manage`)

- [ ] **Step 1: Write the failing API tests first**

Create `tests/test_users_api.py`. Follow the house style in `tests/test_submission_api.py` / `tests/test_master_data.py`: a module-level `_token(client, username, password)` async helper that POSTs `/api/v1/auth/login` and returns the access token, then builds `{"Authorization": f"Bearer {tok}"}` headers.

Cover at minimum, as real `httpx.AsyncClient`-driven tests against the `client` fixture:
1. `POST /api/v1/users` as `kades` creating a new `bendahara_desa` user → 200, response `data.role_name == "staff"`, `data.position_name` set.
2. `POST /api/v1/users` as `sekdes` trying to create a `kepala_desa`-position user → 403.
3. `GET /api/v1/users` as `kades`, default params → 200, response does NOT include any `position_name == "Warga Desa"` row (the seeded `warga` demo account and `rt001`/`rw001` are `warga_desa`/`rt`/`rw` positions respectively — confirm the `warga_desa`-position one specifically is absent by default, and reappears with `include_warga=true`).
4. `GET /api/v1/users?search=kades` → 200, exactly the kades user in `data.items`.
5. `PUT /api/v1/users/{id}` as `kades` updating `sekdes`'s `full_name` → 200, persisted.
6. `PUT /api/v1/users/{id}` as `sekdes` updating `kades` → 403.
7. `DELETE /api/v1/users/{id}` as `kades` on the `bendahara` demo account → 200; subsequent `GET /api/v1/users/{id}` → 404.
8. `POST /api/v1/users/{id}/approve`: first register a new `staff`-choice account via `POST /api/v1/auth/register` (this leaves it `pending_approval=true`, per Part 3), then approve it as `kades` → 200, `data.pending_approval == False`; that account can now `POST /api/v1/auth/login` successfully (was previously rejected with "menunggu persetujuan").
9. `POST /api/v1/users/{id}/reject` on a second freshly self-registered `staff`-choice account, as `kades` → 200; a subsequent login attempt for that account now fails (account soft-deleted, `get_by_username`/`get_by_nik` in `UserRepository` already filter `deleted_at.is_(None)`, so it behaves like it never existed).
10. Any of the above without a bearer token, or with the `warga` demo account's token → 401/403 (no `user:manage` permission).

Run: `pytest tests/test_users_api.py -v`
Expected: FAIL with connection/404 errors (route doesn't exist yet) — confirms tests target the right not-yet-existing endpoints.

- [ ] **Step 2: Write `app/api/v1/users.py`**

```python
"""Admin-driven user & position management endpoints (Bagian 8)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.common import Page
from app.schemas.user_management import UserCreate, UserRead, UserUpdate
from app.services.user_management import UserManagementService

router = APIRouter(tags=["users"])


def _user_read(user: User) -> dict:
    """Build a UserRead-shaped dict, deriving role/position display fields
    from the already-loaded (lazy="selectin") relationships."""
    return UserRead(
        id=user.id, username=user.username, nik=user.nik, full_name=user.full_name,
        email=user.email, phone=user.phone, is_active=user.is_active,
        pending_approval=user.pending_approval, role_id=user.role_id,
        role_name=user.role.name, position_id=user.position_id,
        position_name=user.position.display_name if user.position else None,
        position_level=user.position.level if user.position else None,
        resident_id=user.resident_id, rt_id=user.rt_id, rw_id=user.rw_id,
        created_at=user.created_at,
    ).model_dump(mode="json")


async def _load_actor(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User ORM row (with .role/.position loaded) for the
    authenticated principal -- CurrentUser only carries id/role/permissions."""
    from app.repositories.auth import UserRepository
    actor = await UserRepository(session).get_by_id(UUID(current.id))
    return actor


@router.post("/users", response_model=Envelope[UserRead])
async def create_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Create a user account, assigning any Position (admin-only path)."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).create(
        actor, current.permissions, body.model_dump(exclude_unset=True)
    )
    return success_response(_user_read(obj), "Tersimpan")


@router.get("/users", response_model=Envelope[Page[UserRead]])
async def list_users(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    position_id: UUID | None = Query(None),
    search: str | None = Query(None),
    include_warga: bool = Query(False),
    _: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """List users, paginated, filtered by position/search, warga hidden by default."""
    items, total = await UserManagementService(session).list(
        p.page, p.size, position_id, search, include_warga
    )
    return success_response({
        "items": [_user_read(u) for u in items], "total": total, "page": p.page, "size": p.size,
    })


@router.get("/users/{item_id}", response_model=Envelope[UserRead])
async def get_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Get a single user by id."""
    obj = await UserManagementService(session).get_or_404(item_id)
    return success_response(_user_read(obj))


@router.put("/users/{item_id}", response_model=Envelope[UserRead])
async def update_user(
    item_id: UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Update a user, gated by the position-hierarchy rule."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).update(
        actor, current.permissions, item_id, body.model_dump(exclude_unset=True)
    )
    return success_response(_user_read(obj), "Diperbarui")


@router.delete("/users/{item_id}", response_model=Envelope[None])
async def delete_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Soft-delete a user, gated by the position-hierarchy rule."""
    actor = await _load_actor(session, current)
    await UserManagementService(session).delete(actor, current.permissions, item_id)
    return success_response(None, "Dihapus")


@router.post("/users/{item_id}/approve", response_model=Envelope[UserRead])
async def approve_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Approve a pending self-registration (staff/rt/rw)."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).approve(actor, current.permissions, item_id)
    return success_response(_user_read(obj), "Registrasi disetujui")


@router.post("/users/{item_id}/reject", response_model=Envelope[None])
async def reject_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Reject a pending self-registration (staff/rt/rw) -- soft-deletes it."""
    actor = await _load_actor(session, current)
    await UserManagementService(session).reject(actor, current.permissions, item_id)
    return success_response(None, "Registrasi ditolak")
```

Move the top-of-function `from app.repositories.auth import UserRepository` import in `_load_actor` to the top of the file with the other imports instead (written inline above only to keep this snippet's diff-context obvious — do NOT leave it as a local import in the final code; local imports mid-function are not this codebase's style, check any other service/router file for confirmation).

- [ ] **Step 3: Register the router**

In `app/api/v1/__init__.py`, add `users` to the import line and register it:

```python
"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import approval_config, auth, health, letter_template, master, submission, users

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
api_router.include_router(submission.router)
api_router.include_router(users.router)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/test_users_api.py -v`
Expected: PASS.

Run the full suite: `pytest -v`
Expected: PASS.

- [ ] **Step 5: Ruff + commit**

Run: `ruff check app/api/v1/users.py app/api/v1/__init__.py tests/test_users_api.py`
Expected: no errors.

```bash
git add app/api/v1/users.py app/api/v1/__init__.py tests/test_users_api.py
git commit -m "feat(users): /users CRUD + approve/reject API endpoints"
```

---

## Notes for the controller (not part of any task)

- `seed_rbac`'s demo-user create-or-update block (`app/seed/seed.py`) has a pre-existing comment flagging that matching by `username` alone becomes unsafe once self-registration exists (a real citizen could register with a username colliding with a `DEMO_ACCOUNTS` entry, and a reseed would silently overwrite their role/position). Self-registration shipped in Part 3. This is a real, currently-live gap — but it is a seed-hygiene issue orthogonal to this part's scope (user-management CRUD), so it is NOT fixed here. Flag it explicitly in the end-of-branch review.
- This part does not build a frontend-facing "who can approve whom" preview UI — that's a frontend concern, out of scope for this backend-only rework.
- Live-DB smoke verification and README updates for this part are deferred to the end-of-branch review, not done per-part (per the controller's current instructions).
