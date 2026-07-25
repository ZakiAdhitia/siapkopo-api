# Rework Part 3: Autentikasi — Login Unified, Registrasi, Lupa Password Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace NIK+OTP login with unified login (username-or-NIK + password), add
self-registration (with an approval gate for non-warga positions), and add
forgot/reset-password — removing `OtpService` entirely.

**Architecture:** `AuthService` gains `login()` (replacing `login_password`/
`login_otp`), `register()`, `forgot_password()`/`reset_password()`. A new
`PasswordResetService` (Redis-backed code, same TTL pattern the old `OtpService` used)
replaces `OtpService`. Registration account-approval itself (the admin-side
approve/reject action) is **out of scope for this part** — it's built in Part 5 (User &
Position management), which owns the "halaman user" this spec assigns it to. This part
only creates the `pending_approval` account; nothing approves it yet, so a `staff`/`rt`/
`rw` registrant cannot actually log in until Part 5 ships (acceptable, sequential
rework).

**Tech Stack:** Redis (existing `app.core.redis`), no new dependencies. Email format is
validated with a lightweight custom check, not the `pydantic[email]` extra, to avoid
adding a new dependency for this.

## Global Constraints

- No OTP anywhere. `app/services/otp.py`, `/auth/request-otp`, `/auth/verify-otp`,
  `Settings.otp_ttl_seconds`/`otp_length` are all deleted.
- Login: `POST /auth/login` takes `{"identifier": ..., "password": ...}` where
  `identifier` matches either `username` or `nik`. Every account type (warga included)
  logs in this same way now.
- Registration position choices are exactly `staff | rt | rw | warga` — `kepala_desa`/
  `sekretaris_desa`/`bendahara_desa` can never be self-registered (assigned later via
  Part 5's user-management page only).
- `position_choice` → stored `(role, position)` mapping (from the rework spec, do not
  deviate): `warga`→(`warga`,`warga_desa`), `rt`→(`warga`,`rt`), `rw`→(`warga`,`rw`),
  `staff`→(`staff`,`staff_desa`).
- `warga`/`rt`/`rw` registration requires `nik` and it MUST match an existing
  `Resident.nik` — these three positions represent actual citizens (RT/RW are elected
  from among residents), so identity is checked against master data and `resident_id`
  is set on the new `User`. `staff` registration's `nik` is optional and NOT checked
  against `Resident` (village office staff are not necessarily pre-existing residents
  in the system) — this asymmetry is intentional, not an oversight.
- `email` is **mandatory** for every registration, all positions (already decided in
  brainstorming) — used for password-reset delivery.
- `warga` registrants are immediately active (`is_active=True`, `pending_approval=False`).
  `staff`/`rt`/`rw` registrants are created inactive and pending
  (`is_active=False`, `pending_approval=True`) — login is rejected for them until a
  Part 5 admin action flips those flags (not built yet, that's fine, this part doesn't
  need to make that path work end-to-end).
- Forgot-password must not leak account existence: `POST /auth/forgot-password` always
  returns the same generic success response shape regardless of whether `identifier`
  matched a real account.
- Resetting a password must invalidate every one of that user's active refresh tokens
  (forces re-login everywhere).
- The password-reset code delivery is a simple, synchronous, log-only send (mirroring
  exactly how the OLD `OtpService` behaved in dev mode) — **not** the full pluggable
  `NotificationProvider`/ARQ-worker abstraction. That richer notification
  infrastructure is Part 7 (Notifikasi)'s job; Part 7 MAY later refactor this part's
  log-only send to go through its shared provider, but that refactor is not part of
  this plan and must not be anticipated here (YAGNI — don't build the abstraction
  before the part that needs it exists).
- The final test suite must pass 100% and `ruff check app tests` must be clean before
  this part is done.

---

### Task 1: Settings + `RefreshTokenRepository.revoke_all_for_user`

**Files:**
- Modify: `app/core/config.py`
- Modify: `app/repositories/auth.py`

**Interfaces:**
- Produces: `Settings.password_reset_ttl_seconds` (default 600),
  `Settings.password_reset_code_length` (default 6).
  `RefreshTokenRepository.revoke_all_for_user(user_id: uuid.UUID) -> None`.

- [ ] **Step 1: `app/core/config.py`**

Remove:
```python
    otp_ttl_seconds: int = 300
    otp_length: int = 6
```
Add in the same place:
```python
    password_reset_ttl_seconds: int = 600
    password_reset_code_length: int = 6
```

- [ ] **Step 2: `app/repositories/auth.py`**

Add to `RefreshTokenRepository`, after `revoke`:

```python
    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        """Revoke every active refresh token belonging to a user.

        Used after a password reset, so a stolen/old session can't outlive
        a credential change.
        """
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        tokens = (await self.session.scalars(stmt)).all()
        now = datetime.now(timezone.utc)
        for token in tokens:
            token.revoked_at = now
        await self.session.flush()
```

- [ ] **Step 3: Verify**

Run: `python -c "import app.core.config; import app.repositories.auth"`
Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py app/repositories/auth.py
git commit -m "feat(auth): password-reset settings + revoke_all_for_user"
```

---

### Task 2: `PasswordResetService`

**Files:**
- Create: `app/services/password_reset.py`
- Test: `tests/test_password_reset_service.py`

**Interfaces:**
- Produces: `PasswordResetService.request_reset(user: User) -> str` (returns the raw
  code, for dev-mode echoing), `PasswordResetService.verify_and_consume(user_id:
  uuid.UUID, code: str) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
import pytest

from app.services.password_reset import PasswordResetService


@pytest.mark.asyncio
async def test_request_reset_then_verify_succeeds(_fake_redis):
    from app.models.auth import User
    user = User(id="11111111-1111-1111-1111-111111111111", full_name="Test User")
    svc = PasswordResetService()
    code = await svc.request_reset(user)
    assert len(code) == svc.settings.password_reset_code_length
    assert await svc.verify_and_consume(user.id, code) is True


@pytest.mark.asyncio
async def test_verify_wrong_code_fails(_fake_redis):
    from app.models.auth import User
    user = User(id="22222222-2222-2222-2222-222222222222", full_name="Test User")
    svc = PasswordResetService()
    await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, "000000") is False


@pytest.mark.asyncio
async def test_verify_consumes_code(_fake_redis):
    """A code can only be used once."""
    from app.models.auth import User
    user = User(id="33333333-3333-3333-3333-333333333333", full_name="Test User")
    svc = PasswordResetService()
    code = await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, code) is True
    assert await svc.verify_and_consume(user.id, code) is False
```

Note: `_fake_redis` is the autouse fixture already in `tests/conftest.py` (swaps
`app.core.redis`'s module-singleton client for `fakeredis`) — it applies automatically
to every test in the suite, no explicit fixture parameter is actually required for it
to take effect, but naming it as a parameter here documents the dependency; if pytest
complains about an unknown fixture name, remove the parameter (the autouse fixture
still applies without being named).

- [ ] **Step 2: Run, confirm failure**

Run: `pytest tests/test_password_reset_service.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.password_reset'`.

- [ ] **Step 3: Implement**

```python
"""Password-reset code generation/verification backed by Redis.

Same generate/store/verify/consume pattern the old OtpService used for
login OTPs -- OTP login itself is gone (see the rework spec), but the
underlying Redis-TTL-code mechanism is still the right tool for a
short-lived, single-use password-reset code.
"""
import secrets
import uuid

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.auth import User

logger = get_logger("password_reset")


class PasswordResetService:
    """Generate and verify one-time password-reset codes stored in Redis."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = get_redis()

    def _key(self, user_id: uuid.UUID) -> str:
        return f"pwreset:{user_id}"

    async def request_reset(self, user: User) -> str:
        """Generate a reset code, store with TTL, return it (dev delivery)."""
        code = "".join(
            secrets.choice("0123456789") for _ in range(self.settings.password_reset_code_length)
        )
        await self.redis.set(self._key(user.id), code, ex=self.settings.password_reset_ttl_seconds)
        if self.settings.app_env != "production":
            logger.info("Password reset code for user_id=%s: %s (dev)", user.id, code)
        else:
            logger.info("Password reset code generated for user_id=%s", user.id)
        return code

    async def verify_and_consume(self, user_id: uuid.UUID, code: str) -> bool:
        """Verify and consume a reset code."""
        stored = await self.redis.get(self._key(user_id))
        if stored and stored == code:
            await self.redis.delete(self._key(user_id))
            return True
        return False
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/test_password_reset_service.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/password_reset.py tests/test_password_reset_service.py
git commit -m "feat(auth): PasswordResetService (Redis-backed reset codes)"
```

---

### Task 3: `AuthService.login()` — unified login

**Files:**
- Modify: `app/services/auth.py`
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Removes: `AuthService.login_password`, `AuthService.login_otp`, `self.otp`
  (`OtpService` instance).
- Produces: `AuthService.login(identifier: str, password: str) -> dict`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_auth_service.py` (these REPLACE the existing
`test_login_password_success`/`test_login_password_wrong` tests — rename/adapt them):

```python
@pytest.mark.asyncio
async def test_login_by_username_success(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login("staf", "staf123")
    assert pair["access_token"]
    assert pair["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_by_nik_success(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login("3516064588020003", "warga123")
    assert pair["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(seeded_session):
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login("staf", "wrong")


@pytest.mark.asyncio
async def test_login_pending_approval_rejected(seeded_session):
    """A pending_approval=True account cannot log in even with the right password."""
    from app.core.security import hash_password
    from app.models.auth import User
    user = await AuthService(seeded_session).users.get_by_username("staf")
    pending = User(
        username="pendingstaff", full_name="Pending Staff",
        hashed_password=hash_password("pending123"), role_id=user.role_id,
        is_active=False, pending_approval=True,
    )
    seeded_session.add(pending)
    await seeded_session.commit()
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login("pendingstaff", "pending123")
```

Every OTHER existing test in this file that called `svc.login_password(...)` must be
updated to call `svc.login(...)` instead (same two positional args, just the method
name changes) — search the file for `login_password` and `login_otp` and update each
call site; there is no behavior change needed in those tests beyond the rename.

- [ ] **Step 2: Run, confirm the new tests fail**

Run: `pytest tests/test_auth_service.py -v`
Expected: FAIL — `AttributeError: 'AuthService' object has no attribute 'login'`.

- [ ] **Step 3: Implement**

In `app/services/auth.py`, remove the `from app.services.otp import OtpService`
import and the `self.otp = OtpService()` line from `__init__`. Replace
`login_password` and `login_otp` with a single method:

```python
    async def login(self, identifier: str, password: str) -> dict:
        """Authenticate by username OR NIK, both matched against `password`."""
        clean = identifier.strip()
        user = await self.users.get_by_username(clean.lower())
        if user is None:
            user = await self.users.get_by_nik(clean)
        if not user or not user.hashed_password or not verify_password(password, user.hashed_password):
            logger.warning("Login gagal untuk identifier=%s", clean)
            raise UnauthorizedError("Identitas atau kata sandi salah")
        if not user.is_active:
            if user.pending_approval:
                logger.warning("Login ditolak (menunggu approval) untuk identifier=%s", clean)
                raise UnauthorizedError("Akun Anda masih menunggu persetujuan")
            logger.warning("Login ditolak (akun tidak aktif) untuk identifier=%s", clean)
            raise UnauthorizedError("Akun tidak aktif")
        result = await self._issue(user)
        logger.info("Login sukses user_id=%s role=%s", user.id, user.role.name)
        return result
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/test_auth_service.py -v`
Expected: all pass (do not worry yet about failures elsewhere in the suite from other
files still calling the old method names or `/request-otp` — those are fixed in
Task 8).

- [ ] **Step 5: Commit**

```bash
git add app/services/auth.py tests/test_auth_service.py
git commit -m "feat(auth): unified login(identifier, password), remove OTP login"
```

---

### Task 4: `AuthService.register()`

**Files:**
- Modify: `app/services/auth.py`
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Produces: `AuthService.register(data: dict) -> tuple[User, bool]` — returns the
  created `User` and a `bool` for "is immediately active" (so the API layer can build
  the right response message without re-deriving the position_choice logic).
  `data` keys: `full_name, username, password, email, position_choice, nik, rt_id, rw_id`
  (the last three optional/`None`).

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_register_warga_matches_resident_is_active(seeded_session):
    """Registering as warga with a NIK that matches a seeded Resident activates immediately.

    Uses Ahmad Fauzi's resident NIK (seed suffix "0011" -> "3516" +
    "0011".zfill(12) -> "3516000000000011", per seed_master's nik formula).
    Deliberately NOT the demo "warga" account's own nik ("3516064588020003",
    an arbitrary DEMO_ACCOUNTS value unrelated to any Resident row) and NOT
    "Siti Rohmah" (already linked to the demo "warga" user by
    seed_link_demo_resident, which would make this a ConflictError case
    instead of the success case this test wants).
    """
    from app.seed.seed import seed_master
    await seed_master(seeded_session)
    svc = AuthService(seeded_session)
    user, is_active = await svc.register({
        "full_name": "Ahmad Fauzi Baru", "username": "ahmadfauzi2",
        "password": "password123", "email": "ahmadfauzi2@example.test",
        "position_choice": "warga", "nik": "3516000000000011",
        "rt_id": None, "rw_id": None,
    })
    assert is_active is True
    assert user.is_active is True
    assert user.pending_approval is False
    assert user.resident_id is not None
    assert user.role.name == "warga"
    assert user.position.slug == "warga_desa"


@pytest.mark.asyncio
async def test_register_warga_unknown_nik_rejected(seeded_session):
    from app.core.exceptions import ValidationAppError
    svc = AuthService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.register({
            "full_name": "Orang Asing", "username": "orangasing",
            "password": "password123", "email": "asing@example.test",
            "position_choice": "warga", "nik": "9999999999999999",
            "rt_id": None, "rw_id": None,
        })


@pytest.mark.asyncio
async def test_register_staff_is_pending(seeded_session):
    svc = AuthService(seeded_session)
    user, is_active = await svc.register({
        "full_name": "Staf Baru", "username": "stafbaru",
        "password": "password123", "email": "stafbaru@example.test",
        "position_choice": "staff", "nik": None, "rt_id": None, "rw_id": None,
    })
    assert is_active is False
    assert user.is_active is False
    assert user.pending_approval is True
    assert user.role.name == "staff"
    assert user.position.slug == "staff_desa"


@pytest.mark.asyncio
async def test_register_duplicate_username_rejected(seeded_session):
    from app.core.exceptions import ConflictError
    svc = AuthService(seeded_session)
    with pytest.raises(ConflictError):
        await svc.register({
            "full_name": "Duplikat", "username": "staf",  # already a demo account
            "password": "password123", "email": "dup@example.test",
            "position_choice": "staff", "nik": None, "rt_id": None, "rw_id": None,
        })
```

- [ ] **Step 2: Run, confirm failure**

Run: `pytest tests/test_auth_service.py -v -k register`
Expected: FAIL — `AttributeError: 'AuthService' object has no attribute 'register'`.

- [ ] **Step 3: Implement**

Add to `app/services/auth.py` (needs new imports — add `from app.core.exceptions
import ConflictError, UnauthorizedError, ValidationAppError` (extending the existing
exceptions import), `from app.core.security import hash_password` (extending the
existing security import), `from sqlalchemy import select`, and
`from app.models.auth import Position, Role, User` (extending the existing
`from app.models.auth import User` to also pull `Position, Role`), and
`from app.models.master import RT, RW, Resident`):

```python
    _POSITION_CHOICE_MAP: dict[str, tuple[str, str]] = {
        "warga": ("warga", "warga_desa"),
        "rt": ("warga", "rt"),
        "rw": ("warga", "rw"),
        "staff": ("staff", "staff_desa"),
    }

    async def register(self, data: dict) -> tuple[User, bool]:
        """Self-register a new account. Returns (user, is_immediately_active).

        warga/rt/rw require a nik matching an existing Resident (identity
        check against master data); staff's nik is optional and unchecked.
        warga is active immediately; staff/rt/rw are created pending
        approval (is_active=False) -- approving them is a later rework
        part's (Part 5) responsibility, not this method's.
        """
        position_choice = data["position_choice"]
        role_name, position_slug = self._POSITION_CHOICE_MAP[position_choice]

        if await self.users.get_by_username(data["username"].strip().lower()):
            raise ConflictError("Username sudah digunakan")
        existing_email = await self.session.scalar(
            select(User).where(User.email == data["email"], User.deleted_at.is_(None))
        )
        if existing_email:
            raise ConflictError("Email sudah digunakan")

        resident_id = None
        nik = data.get("nik")
        if position_choice in ("warga", "rt", "rw"):
            if not nik:
                raise ValidationAppError("NIK wajib diisi untuk pendaftaran ini")
            resident = await self.session.scalar(
                select(Resident).where(Resident.nik == nik, Resident.deleted_at.is_(None))
            )
            if resident is None:
                raise ValidationAppError(
                    "NIK tidak ditemukan pada data kependudukan, silakan hubungi kantor desa"
                )
            already_linked = await self.session.scalar(
                select(User).where(User.resident_id == resident.id, User.deleted_at.is_(None))
            )
            if already_linked:
                raise ConflictError("NIK ini sudah terdaftar")
            resident_id = resident.id
            full_name = resident.full_name
        else:
            full_name = data["full_name"]

        rt_id, rw_id = None, None
        if position_choice == "rt":
            if not data.get("rt_id"):
                raise ValidationAppError("rt_id wajib diisi untuk pendaftaran posisi RT")
            rt = await self.session.get(RT, data["rt_id"])
            if rt is None:
                raise ValidationAppError("RT tidak ditemukan")
            rt_id = rt.id
        elif position_choice == "rw":
            if not data.get("rw_id"):
                raise ValidationAppError("rw_id wajib diisi untuk pendaftaran posisi RW")
            rw = await self.session.get(RW, data["rw_id"])
            if rw is None:
                raise ValidationAppError("RW tidak ditemukan")
            rw_id = rw.id

        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        position = await self.session.scalar(select(Position).where(Position.slug == position_slug))

        is_active = position_choice == "warga"
        user = User(
            username=data["username"].strip().lower(), nik=nik, full_name=full_name,
            hashed_password=hash_password(data["password"]), email=data["email"],
            role_id=role.id, position_id=position.id, resident_id=resident_id,
            rt_id=rt_id, rw_id=rw_id, is_active=is_active, pending_approval=not is_active,
        )
        self.session.add(user)
        await self.session.commit()
        logger.info(
            "User registered id=%s username=%s position=%s active=%s",
            user.id, user.username, position_slug, is_active,
        )
        return user, is_active
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/test_auth_service.py -v -k register`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/auth.py tests/test_auth_service.py
git commit -m "feat(auth): self-registration with position_choice, resident-identity check, approval gate"
```

---

### Task 5: `AuthService.forgot_password()` / `reset_password()`

**Files:**
- Modify: `app/services/auth.py`
- Test: `tests/test_auth_service.py`

**Interfaces:**
- Consumes: `PasswordResetService` (Task 2), `RefreshTokenRepository.revoke_all_for_user`
  (Task 1).
- Produces: `AuthService.forgot_password(identifier: str) -> str | None` (returns the
  dev-mode code if a user matched and non-production, else `None` — the API layer
  decides whether to include it in the response), `AuthService.reset_password(identifier:
  str, code: str, new_password: str) -> None`.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.asyncio
async def test_forgot_password_known_identifier_returns_dev_code(seeded_session):
    svc = AuthService(seeded_session)
    code = await svc.forgot_password("staf")
    assert code is not None
    assert len(code) == svc.password_reset.settings.password_reset_code_length


@pytest.mark.asyncio
async def test_forgot_password_unknown_identifier_returns_none_silently(seeded_session):
    svc = AuthService(seeded_session)
    code = await svc.forgot_password("nosuchuser")
    assert code is None  # no exception raised -- must not leak existence


@pytest.mark.asyncio
async def test_reset_password_success_changes_password_and_revokes_tokens(seeded_session):
    svc = AuthService(seeded_session)
    old_pair = await svc.login("staf", "staf123")
    code = await svc.forgot_password("staf")
    await svc.reset_password("staf", code, "newpassword456")

    # Old refresh token must now be revoked.
    with pytest.raises(UnauthorizedError):
        await svc.refresh(old_pair["refresh_token"])

    # New password works.
    new_pair = await svc.login("staf", "newpassword456")
    assert new_pair["access_token"]
    # Old password no longer works.
    with pytest.raises(UnauthorizedError):
        await svc.login("staf", "staf123")


@pytest.mark.asyncio
async def test_reset_password_wrong_code_rejected(seeded_session):
    svc = AuthService(seeded_session)
    await svc.forgot_password("staf")
    with pytest.raises(UnauthorizedError):
        await svc.reset_password("staf", "000000", "newpassword456")
```

- [ ] **Step 2: Run, confirm failure**

Run: `pytest tests/test_auth_service.py -v -k "forgot_password or reset_password"`
Expected: FAIL — `AttributeError`.

- [ ] **Step 3: Implement**

Add `self.password_reset = PasswordResetService()` to `AuthService.__init__` (add
`from app.services.password_reset import PasswordResetService` to the imports).

Add:

```python
    async def _resolve_by_identifier(self, identifier: str) -> User | None:
        clean = identifier.strip()
        user = await self.users.get_by_username(clean.lower())
        if user is None:
            user = await self.users.get_by_nik(clean)
        return user

    async def forgot_password(self, identifier: str) -> str | None:
        """Generate a reset code for the matching account, if any.

        Returns the raw code only for dev-mode convenience (None in
        production or if no account matched) -- the caller must not use a
        non-None/None distinction to reveal whether an account exists;
        both cases return the same API response shape.
        """
        user = await self._resolve_by_identifier(identifier)
        if user is None:
            return None
        code = await self.password_reset.request_reset(user)
        return code if self.settings.app_env != "production" else None

    async def reset_password(self, identifier: str, code: str, new_password: str) -> None:
        """Verify a reset code and set a new password, revoking all sessions."""
        user = await self._resolve_by_identifier(identifier)
        if user is None or not await self.password_reset.verify_and_consume(user.id, code):
            raise UnauthorizedError("Kode reset tidak valid atau kedaluwarsa")
        user.hashed_password = hash_password(new_password)
        await self.refresh_tokens.revoke_all_for_user(user.id)
        await self.session.commit()
        logger.info("Password reset sukses user_id=%s", user.id)
```

- [ ] **Step 4: Run, confirm pass**

Run: `pytest tests/test_auth_service.py -v -k "forgot_password or reset_password"`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/auth.py tests/test_auth_service.py
git commit -m "feat(auth): forgot-password/reset-password (no account enumeration, revokes sessions)"
```

---

### Task 6: `schemas/auth.py` rewrite

**Files:**
- Modify: `app/schemas/auth.py`

**Interfaces:**
- Removes: `RequestOtpRequest`, `VerifyOtpRequest`, `OtpRequestedData`.
- Produces: `RegisterRequest`, `RegisterResponse`, `ForgotPasswordRequest`,
  `ForgotPasswordResponse`, `ResetPasswordRequest`. `LoginRequest` changes from
  `username` to `identifier`.

- [ ] **Step 1: Replace the file content**

```python
"""Auth request/response schemas."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


def _validate_email_format(value: str) -> str:
    """Lightweight email-shape check (no pydantic[email] dependency)."""
    if "@" not in value or "." not in value.split("@")[-1] or value.startswith("@") or value.endswith("@"):
        raise ValueError("Format email tidak valid")
    return value


class LoginRequest(BaseModel):
    """Login credentials: identifier matches username OR nik."""

    identifier: str = Field(min_length=1)
    password: str


class RegisterRequest(BaseModel):
    """Self-registration request."""

    full_name: str = Field(min_length=1, max_length=150)
    username: str = Field(min_length=3, max_length=50)
    password: str = Field(min_length=6)
    email: str
    position_choice: Literal["staff", "rt", "rw", "warga"]
    nik: str | None = Field(default=None, min_length=8, max_length=20)
    rt_id: UUID | None = None
    rw_id: UUID | None = None

    @field_validator("email")
    @classmethod
    def _check_email(cls, v: str) -> str:
        return _validate_email_format(v)


class RegisterResponse(BaseModel):
    """Outcome of a registration request."""

    status: Literal["active", "pending_approval"]
    message: str


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)


class ForgotPasswordResponse(BaseModel):
    """Always the same shape regardless of whether identifier matched an account."""

    message: str
    # dev only: code echoed back so the frontend/test can proceed without a real
    # email provider. None in production, and None if no account matched --
    # do not use presence/absence of this field to infer account existence.
    dev_code: str | None = None


class ResetPasswordRequest(BaseModel):
    identifier: str = Field(min_length=1)
    code: str = Field(min_length=1)
    new_password: str = Field(min_length=6)


class RefreshRequest(BaseModel):
    """Raw refresh token submitted for rotation."""

    refresh_token: str


class LogoutRequest(BaseModel):
    """Optional refresh token to revoke on logout."""

    refresh_token: str | None = None


class TokenData(BaseModel):
    """Issued access/refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class MeData(BaseModel):
    """Current authenticated identity."""

    id: str
    role: str
    permissions: list[str]
```

- [ ] **Step 2: Verify**

Run: `python -c "import app.schemas.auth"`
Expected: exit code 0.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/auth.py
git commit -m "feat(auth): schemas for unified login, registration, forgot/reset password"
```

---

### Task 7: `api/v1/auth.py` rewrite + delete `app/services/otp.py`

**Files:**
- Modify: `app/api/v1/auth.py`
- Delete: `app/services/otp.py`

**Interfaces:**
- Removes: `POST /auth/request-otp`, `POST /auth/verify-otp`.
- Produces: `POST /auth/register`, `POST /auth/forgot-password`,
  `POST /auth/reset-password`. `POST /auth/login` now takes `LoginRequest` (with
  `identifier`).

- [ ] **Step 1: Replace the file content**

```python
"""Authentication endpoints."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.core.security import decode_token
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.schemas.auth import (
    ForgotPasswordRequest, ForgotPasswordResponse, LoginRequest, LogoutRequest,
    MeData, RefreshRequest, RegisterRequest, RegisterResponse, ResetPasswordRequest,
    TokenData,
)
from app.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Envelope[RegisterResponse])
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Self-register a new account."""
    _user, is_active = await AuthService(session).register(body.model_dump())
    if is_active:
        data = RegisterResponse(status="active", message="Registrasi berhasil, silakan masuk")
    else:
        data = RegisterResponse(
            status="pending_approval",
            message="Registrasi berhasil, menunggu persetujuan admin sebelum dapat masuk",
        )
    return success_response(data.model_dump(), data.message)


@router.post("/login", response_model=Envelope[TokenData])
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Login with username or NIK + password."""
    pair = await AuthService(session).login(body.identifier, body.password)
    return success_response(pair, "Login berhasil")


@router.post("/forgot-password", response_model=Envelope[ForgotPasswordResponse])
async def forgot_password(
    body: ForgotPasswordRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Request a password-reset code. Response shape never reveals account existence."""
    code = await AuthService(session).forgot_password(body.identifier)
    data = ForgotPasswordResponse(
        message="Jika akun ditemukan, kode reset telah dikirim ke email terdaftar",
        dev_code=code,
    )
    return success_response(data.model_dump())


@router.post("/reset-password", response_model=Envelope[None])
async def reset_password(
    body: ResetPasswordRequest, session: AsyncSession = Depends(get_db)
) -> dict:
    """Reset a password using a code from /forgot-password."""
    await AuthService(session).reset_password(body.identifier, body.code, body.new_password)
    return success_response(None, "Kata sandi berhasil diubah")


@router.post("/refresh", response_model=Envelope[TokenData])
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> dict:
    """Rotate the refresh token."""
    pair = await AuthService(session).refresh(body.refresh_token)
    return success_response(pair, "Token diperbarui")


@router.post("/logout", response_model=Envelope[None])
async def logout(
    body: LogoutRequest, request: Request, session: AsyncSession = Depends(get_db),
    user: CurrentUser = Depends(require_permission("auth:me")),
) -> dict:
    """Blacklist the current access token and revoke refresh."""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()
    payload = decode_token(token)
    await AuthService(session).logout(payload, body.refresh_token)
    return success_response(None, "Logout berhasil")


@router.get("/me", response_model=Envelope[MeData])
async def me(user: CurrentUser = Depends(require_permission("auth:me"))) -> dict:
    """Return the current identity and permissions."""
    return success_response(
        {"id": user.id, "role": user.role, "permissions": user.permissions}
    )
```

- [ ] **Step 2: Delete `app/services/otp.py`**

```bash
git rm app/services/otp.py
```

- [ ] **Step 3: Verify**

Run: `python -c "import app.api.v1.auth"`
Expected: exit code 0 (this file's own imports succeed; the rest of the package may
still be broken from unrelated stale references elsewhere in the codebase — not this
task's concern, Task 8 fixes the whole suite).

- [ ] **Step 4: Commit**

```bash
git add app/api/v1/auth.py
git commit -m "feat(auth): register/login/forgot-password/reset-password endpoints, remove OTP endpoints"
```

---

### Task 8: Fix every test broken by the auth rework

**Files:**
- Modify (as needed, discover via running the suite): `tests/test_auth.py`,
  `tests/test_auth_repo.py`, `tests/test_auth_models.py`, `tests/conftest.py`, and any
  other file that logs in via the old `login_password`/`login_otp` methods, posts to
  `/auth/request-otp`/`/auth/verify-otp`, or asserts on the old `LoginRequest.username`
  field shape.

- [ ] **Step 1: Run the full suite**

Run: `pytest -v 2>&1 | tail -150`

- [ ] **Step 2: Fix each failure**

Patterns to expect:
- `tests/test_auth.py` (API-level): replace `/auth/request-otp`/`/auth/verify-otp`
  flows with `/auth/register` + `/auth/login`; replace `{"username": ...}` login
  request bodies with `{"identifier": ..., "password": ...}`.
- Any test client helper that logs in as `warga` via OTP must switch to
  `POST /auth/login` with `{"identifier": "warga", "password": "warga123"}` (the demo
  `warga` account already has a password set, from Part 1's seeding).
- `tests/test_auth_repo.py`: verify `UserRepository`/`RefreshTokenRepository` tests
  still make sense; add coverage for `revoke_all_for_user` if none exists yet (a
  minimal test: create two active tokens for one user, call
  `revoke_all_for_user`, assert `get_active_by_hash` returns None for both).
- Any fixture or helper function using `svc.login_password(...)`/`svc.login_otp(...)`
  — rename to `svc.login(...)`.

Do not weaken any test's actual intent while fixing it — if a test was checking "OTP
login rejects a wrong code," the closest surviving equivalent is "login rejects a wrong
password" (via the new unified method) — keep checking an analogous real behavior, not
delete the check entirely, unless the specific behavior truly has no equivalent anymore
(e.g. a test asserting the OTP *request* endpoint's dev_code echo shape has a direct
equivalent in the new forgot-password dev_code echo — adapt it there, don't just
delete it).

- [ ] **Step 3: Confirm everything passes**

Run: `pytest -v`
Expected: 100% pass, 0 failures.

Run: `ruff check app tests`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(auth): fix tests broken by OTP removal + unified login/registration"
```

---

### Task 9: Live verification against `db_kopo` + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Manual smoke test against live `db_kopo`**

Start the app (`uvicorn app.main:app --reload` in one terminal — or run these checks
with a short-lived TestClient-style script if starting a live server isn't practical in
this environment; either is fine as long as it exercises the real `db_kopo` connection
string from `.env`, not the test suite's in-memory SQLite):

```bash
python -c "
import asyncio
from app.services.auth import AuthService
from app.db.session import AsyncSessionLocal

async def main():
    async with AsyncSessionLocal() as s:
        svc = AuthService(s)
        pair = await svc.login('staf', 'staf123')
        print('login by username OK:', bool(pair['access_token']))

    async with AsyncSessionLocal() as s:
        svc = AuthService(s)
        pair = await svc.login('3516064588020003', 'warga123')
        print('login by nik OK:', bool(pair['access_token']))

asyncio.run(main())
"
```
Expected: both lines print `True`. (Adjust the session-maker import if
`AsyncSessionLocal` isn't the actual exported name in `app/db/session.py`.)

- [ ] **Step 2: Update README**

In `README.md`:
- Under "## Demo Accounts", remove the sentence about `warga` authenticating via OTP
  (`request-otp`/`verify-otp`) — every account now logs in identically via
  `POST /api/v1/auth/login` with `{"identifier": ..., "password": ...}`, where
  `identifier` is the username for staff-tier accounts or the NIK for `warga`.
- Under "## API surface (current)", replace the `POST /api/v1/auth/login,
  /request-otp, /verify-otp, /refresh, /logout, GET /me` line with:
  `POST /api/v1/auth/register, /login, /forgot-password, /reset-password, /refresh,
  /logout, GET /me`.
- Add a short note (near wherever this fits best in the existing structure) that
  self-registration exists for `staff`/`rt`/`rw`/`warga`, that `warga` activates
  immediately (NIK checked against Resident master data) while the other three require
  admin approval (not yet actionable in the API until Part 5 ships), and that
  `/forgot-password` never reveals whether an account exists.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: update README for unified login + registration (OTP removed)"
```
