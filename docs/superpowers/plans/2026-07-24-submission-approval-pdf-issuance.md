# Submission, Approval Workflow & PDF Issuance (Sub-project B2, Phase 5-7) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the submission lifecycle — citizens submit letter requests validated against B1's templates, staff approve/reject through a village-configurable step chain (no hardcoded roles), and the final approval automatically issues a real PDF with an allocated number, visual signature, and a scannable QR that resolves through a public, no-auth verification endpoint.

**Architecture:** Same Clean Architecture as Foundation/B1: `router → service → repository → model`. `TemplateRenderService` (B1) is extended, not duplicated, so the SSRF/DoS hardening from B1's final review protects both preview and real issuance. Approval turn-taking is enforced by comparing `ApprovalStepConfig.role_id` (data) against the acting user's `role_id` — never a role-name string literal.

**Tech Stack:** Adds `qrcode` (QR image generation, pure Python + Pillow — Pillow is already installed transitively via `xhtml2pdf`) to the existing stack. Uses local disk for attachment/PDF storage behind a small swappable `FileStorageService` (Cloudflare R2 later, per CLAUDE.md "Object Storage ready" — not built now).

## Global Constraints

- Python 3.13+; async everywhere; no synchronous DB access.
- Router has NO business logic; services hold logic; repositories/`BaseRepository` hold DB access (raw `select()` in a service is acceptable only where `BaseRepository` genuinely can't express the query — e.g. ordered/joined reads — matching the precedent already accepted in B1's `list_fields`).
- Every endpoint has `response_model=Envelope[...]` (or `Envelope[Page[...]]` for lists); the PDF-download and public-verify-redirect-style endpoints that return raw bytes are the only exceptions, matching B1's `/preview` precedent.
- RBAC is data-driven: guard with `require_permission("...")`; approval turn-taking compares `role_id` values (data), never `if role == "..."` string literals.
- Every table: UUID v4 PK (`GUID()`), `created_at`/`updated_at` (UTC tz-aware) via `TimestampMixin`, `deleted_at` via `SoftDeleteMixin` — **except** `SubmissionStatusHistory` and `LetterNumberCounter`, which deliberately omit `SoftDeleteMixin` (an audit trail and a counter are never soft-deleted; keeping the mixin would be misleading dead capability, not a missing requirement).
- `village_id` FK on tenant-scoped tables (`ApprovalStepConfig`, `Submission`).
- Response envelope — Success: `{"success": true, "message": "...", "data": {...}}`; Error: `{"success": false, "message": "...", "error_code": "...", "data": null}`.
- Pagination response shape: `{"items": [...], "total": int, "page": int, "size": int}` via the existing `build_page()` helper (`app/schemas/common.py`).
- Reject is terminal (no submission-edit/resubmit path exists or is planned in this plan).
- **`TemplateRenderService`'s xhtml2pdf hardening (`link_callback` blocking external resources + socket timeout) must be preserved and reused, not reimplemented**, when adding `render_issued`.
- Type hints + docstrings + logger in every service module. Custom exceptions only; never leak a traceback.
- Commit frequently, one logical change per task.

---

## File Structure

```
sipades-kopo-api/
  pyproject.toml                      # + qrcode
  app/
    core/
      config.py                       # + public_verify_base_url, max_upload_size_bytes, upload_storage_dir
    models/
      submission.py                   # ApprovalStepConfig, Submission, SubmissionStatusHistory,
                                       #   SubmissionAttachment, LetterNumberCounter, enums
    schemas/
      submission.py                   # Submission/Attachment/History/ApprovalStep schemas
    services/
      file_storage.py                 # FileStorageService (local disk)
      qr.py                           # generate_qr_data_uri()
      template_render.py              # MODIFIED: shared _render_document core + render_issued
      letter_number.py                # LetterNumberService (atomic allocation)
      approval_config.py              # ApprovalStepConfigService
      submission.py                   # SubmissionService (create/attach/approve/reject/_issue)
      notification.py                 # notify_status_change() stub (Phase 8 integration point)
    api/v1/
      approval_config.py              # /approval-steps router
      submission.py                   # /submissions router
      public.py                       # /public/verify/{code} router, no auth
      __init__.py                     # + include new routers
    permissions/
      registry.py                     # + submission:*, submission:read_all, approval_config:manage
    seed/
      seed.py                         # + seed_approval_steps, seed_link_demo_resident
  tests/
    test_qr_smoke.py
    test_permissions_registry.py      # extended
    test_submission_models.py
    test_file_storage.py
    test_template_render.py           # extended (render_issued)
    test_letter_number.py
    test_approval_config_service.py
    test_approval_config_api.py
    test_submission_service.py
    test_submission_api.py
    test_public_verify_api.py
    test_seed_submission.py
```

---

### Task 1: `qrcode` dependency — isolated smoke test

Mirrors B1's Task 1 pattern (surface image-library risk early, alone) even though `qrcode` +
Pillow is pure Python with no known native-lib issues on Windows (unlike WeasyPrint) — cheap
insurance before ten more tasks build on it.

**Files:**
- Modify: `pyproject.toml`
- Test: `tests/test_qr_smoke.py`

**Interfaces:**
- Produces: `qrcode` importable and able to render a PNG in-memory.

- [ ] **Step 1: Add dependency**

In `pyproject.toml`'s `[project] dependencies`, add:
```toml
  "qrcode>=7.4",
```

- [ ] **Step 2: Install**

```bash
source .venv/Scripts/activate
pip install -e ".[dev]"
```

- [ ] **Step 3: Write the smoke test** `tests/test_qr_smoke.py`

```python
"""Smoke test: qrcode can render a QR PNG on this machine."""
import io

import qrcode


def test_qrcode_renders_png():
    img = qrcode.make("https://example.test/verify/ABC-2026-123456")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert buf.getvalue()[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 4: Run it**

Run: `pytest tests/test_qr_smoke.py -v`

Expected: PASS. (If it fails, report `BLOCKED` with the full error — do not substitute a
different QR library without asking, same policy as B1's PDF-library decision point.)

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml tests/test_qr_smoke.py
git commit -m "chore: add qrcode dependency, verify QR PNG rendering"
```

---

### Task 2: Permission registry + settings extensions

**Files:**
- Modify: `app/permissions/registry.py`
- Modify: `app/core/config.py`
- Test: `tests/test_permissions_registry.py`

**Interfaces:**
- Produces: new permission codes `submission:create`, `submission:read`, `submission:read_all`,
  `submission:approve`, `submission:reject`, `submission:download`, `approval_config:manage`
  added to `PERMISSIONS`; role mappings updated. New `Settings` fields:
  `public_verify_base_url: str`, `max_upload_size_bytes: int`, `upload_storage_dir: str`.

- [ ] **Step 1: Write failing test** — append to `tests/test_permissions_registry.py`

```python
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
    for role in ("staf", "sekretaris", "kades"):
        for code in (
            "submission:read", "submission:read_all", "submission:approve",
            "submission:reject", "submission:download",
        ):
            assert code in ROLE_PERMISSIONS[role]
```

(Add `PERMISSIONS`, `ROLE_PERMISSIONS` to the existing import at the top of the file if not
already imported — they already are, from Task 2 of the B1 plan.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_permissions_registry.py -v` → FAIL

- [ ] **Step 3: Update `app/permissions/registry.py`**

Change `PERMISSIONS`:
```python
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
```

Change `ROLE_PERMISSIONS`:
```python
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me", "submission:create", "submission:read", "submission:download"],
    "staf": ["auth:me", "resident:read", "resident:create", "resident:update",
             "resident:import", "resident:export", "template:read",
             "submission:read", "submission:read_all", "submission:approve",
             "submission:reject", "submission:download"],
    "sekretaris": ["auth:me", "resident:read", "resident:update",
                   "village:manage", "dusun:manage", "rw:manage", "rt:manage",
                   "family_card:manage", "template:read",
                   "submission:read", "submission:read_all", "submission:approve",
                   "submission:reject", "submission:download"],
    "kades": ["auth:me", "resident:read", "template:read",
              "submission:read", "submission:read_all", "submission:approve",
              "submission:reject", "submission:download"],
    "administrator": ["*"],
}
```

Note: `submission:read_all` distinguishes "sees every submission" (staff tiers) from
`submission:read` alone (warga — service scopes the query to their own rows). This is the
data-driven mechanism `SubmissionService` uses instead of checking a role name (Task 10).

- [ ] **Step 4: Add settings to `app/core/config.py`**

Add these fields to the `Settings` class (after `cors_origins`):
```python
    public_verify_base_url: str = "http://localhost:5173/verify"
    max_upload_size_bytes: int = 5 * 1024 * 1024  # 5 MB, matches FormSurat.jsx's stated limit
    upload_storage_dir: str = "storage"
```

Add the same three lines (with the same defaults, adjusted if you want) to `.env.example`:
```dotenv
PUBLIC_VERIFY_BASE_URL=http://localhost:5173/verify
MAX_UPLOAD_SIZE_BYTES=5242880
UPLOAD_STORAGE_DIR=storage
```

- [ ] **Step 5: Add `storage/` to `.gitignore`**

Append to `.gitignore`:
```gitignore
/storage/
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_permissions_registry.py -v` → PASS

- [ ] **Step 7: Commit**

```bash
git add app/permissions/registry.py app/core/config.py .env.example .gitignore tests/test_permissions_registry.py
git commit -m "feat(submissions): register submission/approval-config permissions + settings"
```

---

### Task 3: Submission domain models + migration

**Files:**
- Create: `app/models/submission.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_submission_models.py`

**Interfaces:**
- Produces:
  - `SubmissionStatus(str, enum.Enum)`: `PENDING = "pending"`, `REJECTED = "rejected"`,
    `ISSUED = "issued"`.
  - `HistoryAction(str, enum.Enum)`: `SUBMITTED = "submitted"`, `APPROVED = "approved"`,
    `REJECTED = "rejected"`, `ISSUED = "issued"`.
  - `ApprovalStepConfig(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base)`, table
    `approval_step_configs`: `village_id, order_index, role_id`. Unique `(village_id, order_index)`.
  - `Submission(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base)`, table `submissions`:
    `village_id, template_id, submitted_by_user_id, answers (JSON), status, current_step_index,
    letter_number, verification_code (unique), pdf_storage_path, rejection_reason,
    rejected_by_user_id, rejected_at, issued_at`.
  - `SubmissionStatusHistory(UUIDMixin, TimestampMixin, Base)` (no soft-delete), table
    `submission_status_history`: `submission_id, step_index, action, actor_user_id, note`.
  - `SubmissionAttachment(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base)`, table
    `submission_attachments`: `submission_id, document_label, original_filename,
    stored_filename, content_type, size_bytes, storage_path`.
  - `LetterNumberCounter(UUIDMixin, TimestampMixin, Base)` (no soft-delete), table
    `letter_number_counters`: `template_id, year, last_seq`. Unique `(template_id, year)`.

- [ ] **Step 1: Write failing test** `tests/test_submission_models.py`

```python
from app.models.submission import (
    ApprovalStepConfig, HistoryAction, LetterNumberCounter, Submission,
    SubmissionAttachment, SubmissionStatus, SubmissionStatusHistory,
)


def test_submission_tables():
    assert ApprovalStepConfig.__tablename__ == "approval_step_configs"
    assert Submission.__tablename__ == "submissions"
    assert SubmissionStatusHistory.__tablename__ == "submission_status_history"
    assert SubmissionAttachment.__tablename__ == "submission_attachments"
    assert LetterNumberCounter.__tablename__ == "letter_number_counters"
    assert SubmissionStatus.PENDING == "pending"
    assert HistoryAction.ISSUED == "issued"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/models/submission.py`**

```python
"""Submission domain models: approval step config, submissions, status
history, attachments, and per-template/year letter-number counters."""
import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class SubmissionStatus(str, enum.Enum):
    """Lifecycle status of a Submission."""

    PENDING = "pending"
    REJECTED = "rejected"
    ISSUED = "issued"


class HistoryAction(str, enum.Enum):
    """Kind of event recorded in SubmissionStatusHistory."""

    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    ISSUED = "issued"


def _values_callable(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum VALUES ("pending"), not member NAMES ("PENDING")."""
    return [member.value for member in enum_cls]


class ApprovalStepConfig(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One ordered step in a village's configurable approval chain."""

    __tablename__ = "approval_step_configs"
    __table_args__ = (
        UniqueConstraint("village_id", "order_index", name="uq_approval_step_village_order"),
    )

    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    order_index: Mapped[int] = mapped_column()
    role_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("roles.id"))


class Submission(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A citizen's letter request, tracked through approval to issuance."""

    __tablename__ = "submissions"

    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("users.id"), index=True
    )
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, native_enum=False, length=20, values_callable=_values_callable),
        default=SubmissionStatus.PENDING,
    )
    current_step_index: Mapped[int | None] = mapped_column(nullable=True, default=0)
    letter_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    verification_code: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True
    )
    pdf_storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejected_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    issued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SubmissionStatusHistory(UUIDMixin, TimestampMixin, Base):
    """Append-only audit trail entry for a Submission's lifecycle."""

    __tablename__ = "submission_status_history"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("submissions.id"), index=True
    )
    step_index: Mapped[int | None] = mapped_column(nullable=True)
    action: Mapped[HistoryAction] = mapped_column(
        SAEnum(HistoryAction, native_enum=False, length=20, values_callable=_values_callable)
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)


class SubmissionAttachment(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """An uploaded supporting document attached to a Submission."""

    __tablename__ = "submission_attachments"

    submission_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("submissions.id"), index=True
    )
    document_label: Mapped[str] = mapped_column(String(150))
    original_filename: Mapped[str] = mapped_column(String(255))
    stored_filename: Mapped[str] = mapped_column(String(255))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column()
    storage_path: Mapped[str] = mapped_column(String(500))


class LetterNumberCounter(UUIDMixin, TimestampMixin, Base):
    """Tracks the last allocated sequence number per (template, year)."""

    __tablename__ = "letter_number_counters"
    __table_args__ = (
        UniqueConstraint("template_id", "year", name="uq_letter_number_counter_template_year"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    year: Mapped[int] = mapped_column()
    last_seq: Mapped[int] = mapped_column(default=0)
```

- [ ] **Step 4: Wire into `app/models/__init__.py`**

```python
from app.models import auth, letter_template, master, submission  # noqa: F401
```

- [ ] **Step 5: Run** — `pytest tests/test_submission_models.py -v` → PASS

- [ ] **Step 6: Generate + apply migration against live `db_kopo`**

```bash
alembic revision --autogenerate -m "submission approval and issuance tables"
alembic upgrade head
```

Verify the 5 new tables exist in `db_kopo`. If the migration references `GUID` and needs an
import, use `import app.db.base` (mirror the existing pattern — do NOT leave an unused bare
`from app.db.base import GUID` import, confirm `ruff` stays clean).

- [ ] **Step 7: Commit**

```bash
git add app/models/submission.py app/models/__init__.py alembic/versions tests/test_submission_models.py
git commit -m "feat(submissions): approval/submission/attachment/counter models and migration"
```

---

### Task 4: `FileStorageService` (local disk)

**Files:**
- Create: `app/services/file_storage.py`
- Test: `tests/test_file_storage.py`

**Interfaces:**
- Produces `FileStorageService()`:
  - `async save(content: bytes, original_filename: str, subdir: str) -> str` — validates
    nothing itself (caller validates size/mime before calling); renames to a UUID-based
    filename preserving the original extension; writes under
    `{settings.upload_storage_dir}/{subdir}/`; returns the **relative** storage path (str)
    to persist in the DB.
  - `async read(storage_path: str) -> bytes` — reads back a previously-saved file.
  - `validate_upload(content: bytes, content_type: str) -> None` — raises
    `ValidationAppError` if `len(content) > settings.max_upload_size_bytes` or
    `content_type` isn't one of `{"image/jpeg", "image/png", "application/pdf"}`.

- [ ] **Step 1: Write failing test** `tests/test_file_storage.py`

```python
import pytest
from app.core.exceptions import ValidationAppError
from app.services.file_storage import FileStorageService


@pytest.mark.asyncio
async def test_save_and_read_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 100})(),
    )
    svc = FileStorageService()
    path = await svc.save(b"hello world", "photo.JPG", subdir="attachments")
    assert path.endswith(".jpg")
    assert await svc.read(path) == b"hello world"


def test_validate_upload_rejects_oversized(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 10, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    with pytest.raises(ValidationAppError):
        svc.validate_upload(b"x" * 11, "image/png")


def test_validate_upload_rejects_bad_mime(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    with pytest.raises(ValidationAppError):
        svc.validate_upload(b"x", "application/zip")


def test_validate_upload_accepts_allowed_mimes(monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {"max_upload_size_bytes": 100, "upload_storage_dir": "x"})(),
    )
    svc = FileStorageService()
    for mime in ("image/jpeg", "image/png", "application/pdf"):
        svc.validate_upload(b"x", mime)  # must not raise
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/file_storage.py`**

```python
"""Local-disk file storage, behind an interface swappable for object storage
(Cloudflare R2) later without touching any caller."""
import uuid
from pathlib import Path

import aiofiles

from app.core.config import get_settings
from app.core.exceptions import ValidationAppError
from app.core.logging import get_logger

logger = get_logger("file_storage")

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}


class FileStorageService:
    """Saves/reads files on local disk under a configurable base directory."""

    def validate_upload(self, content: bytes, content_type: str) -> None:
        """Raise ValidationAppError if the upload violates size/mime rules."""
        settings = get_settings()
        if len(content) > settings.max_upload_size_bytes:
            raise ValidationAppError(
                f"Ukuran file melebihi batas {settings.max_upload_size_bytes // (1024 * 1024)}MB"
            )
        if content_type not in _ALLOWED_CONTENT_TYPES:
            raise ValidationAppError(
                f"Tipe file tidak didukung: {content_type}. "
                "Gunakan JPG, PNG, atau PDF."
            )

    async def save(self, content: bytes, original_filename: str, subdir: str) -> str:
        """Save content under a UUID filename, return the relative storage path."""
        settings = get_settings()
        suffix = Path(original_filename).suffix.lower() or ""
        filename = f"{uuid.uuid4()}{suffix}"
        base = Path(settings.upload_storage_dir) / subdir
        base.mkdir(parents=True, exist_ok=True)
        full_path = base / filename
        async with aiofiles.open(full_path, "wb") as f:
            await f.write(content)
        relative = str(Path(subdir) / filename)
        logger.info("File saved subdir=%s filename=%s size=%d", subdir, filename, len(content))
        return relative

    async def read(self, storage_path: str) -> bytes:
        """Read back a previously-saved file by its relative storage path."""
        settings = get_settings()
        full_path = Path(settings.upload_storage_dir) / storage_path
        async with aiofiles.open(full_path, "rb") as f:
            return await f.read()
```

- [ ] **Step 4: Add `aiofiles` dependency**

Add to `pyproject.toml`'s `[project] dependencies`:
```toml
  "aiofiles>=24.1",
```
Run `pip install -e ".[dev]"`.

- [ ] **Step 5: Run** — `pytest tests/test_file_storage.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/file_storage.py pyproject.toml tests/test_file_storage.py
git commit -m "feat(submissions): local-disk FileStorageService with upload validation"
```

---

### Task 5: QR code helper

**Files:**
- Create: `app/services/qr.py`
- Test: covered by Task 3's Step 1 pattern — add `tests/test_qr_helper.py`

**Interfaces:**
- Produces `generate_qr_data_uri(data: str) -> str` — returns a `data:image/png;base64,...`
  URI (chosen specifically because `TemplateRenderService`'s `link_callback` already treats
  `data:` URIs as safe/inert — no changes needed to the B1 security hardening to embed this).

- [ ] **Step 1: Write failing test** `tests/test_qr_helper.py`

```python
import base64
from app.services.qr import generate_qr_data_uri


def test_generate_qr_data_uri_returns_valid_png_data_uri():
    uri = generate_qr_data_uri("https://example.test/verify/ABC-2026-123456")
    assert uri.startswith("data:image/png;base64,")
    raw = base64.b64decode(uri.split(",", 1)[1])
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/qr.py`**

```python
"""QR code generation for letter verification codes."""
import base64
import io

import qrcode


def generate_qr_data_uri(data: str) -> str:
    """Render `data` as a QR PNG and return it as a data: URI.

    A data: URI (not a file path or external URL) so it can be embedded
    directly in TemplateRenderService's rendered HTML without touching the
    xhtml2pdf link_callback hardening — that callback already treats
    data: URIs as safe/inert (see app/services/template_render.py).
    """
    img = qrcode.make(data)
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"
```

- [ ] **Step 4: Run** — `pytest tests/test_qr_helper.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/qr.py tests/test_qr_helper.py
git commit -m "feat(submissions): QR data-URI generation helper"
```

---

### Task 6: Extend `TemplateRenderService` for real issuance

**Files:**
- Modify: `app/services/template_render.py`
- Modify: `tests/test_template_render.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: a shared private `_render_document(...)` core (extracted from the existing
  `render_preview` body-wrapping logic, security hardening untouched) plus a new
  `render_issued(*, template, fields, village, answers, applicant, nomor, tanggal,
  signer_name, qr_data_uri) -> bytes` that renders **real** submission data instead of
  sample data, with a QR code embedded in the letterhead.

- [ ] **Step 1: Write failing test** — append to `tests/test_template_render.py`

```python
def test_render_issued_embeds_real_answers_and_qr():
    template = _template()
    fields = _fields(template.id)
    village = _village()
    pdf_bytes = TemplateRenderService().render_issued(
        template=template, fields=fields, village=village,
        answers={"alamat_tinggal_saat_ini": "Jl. Nyata No. 1", "lama_tinggal": "3 tahun"},
        applicant={"nama": "Budi Nyata", "nik": "1234567890123456",
                   "alamat": "Jl. Nyata No. 1", "no_kk": "9876543210123456"},
        nomor="470/1/Ds.Kopo/2026",
        tanggal="24 Juli 2026",
        signer_name="Wiwin Wildan",
        qr_data_uri="data:image/png;base64,iVBORw0KGgo=",
    )
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_preview_still_works_after_refactor():
    template = _template()
    pdf_bytes = TemplateRenderService().render_preview(template, _fields(template.id), _village())
    assert pdf_bytes[:5] == b"%PDF-"
```

- [ ] **Step 2: Run** — FAIL (`render_issued` doesn't exist)

- [ ] **Step 3: Refactor `app/services/template_render.py`**

Update `_LETTERHEAD` to add an optional QR block (insert right after the `.judul` div, before
`.body`):
```python
  <div class="qr">
    {% if qr_data_uri %}<img src="{{ qr_data_uri }}" width="80" height="80"/>{% endif %}
  </div>
```
Also add a `.qr { text-align: center; margin-bottom: 10px; }` rule to the `<style>` block.

Replace the `TemplateRenderService` class body with:
```python
class TemplateRenderService:
    """Renders a LetterTemplate's body into a full letter PDF document."""

    def __init__(self) -> None:
        self._env = SandboxedEnvironment(autoescape=True)

    def _sample_value(self, field: TemplateField) -> str:
        """Return a placeholder sample value for a template field, by type."""
        if field.field_type == FieldType.SELECT and field.options:
            return field.options[0]
        if field.field_type == FieldType.NUMBER:
            return "1"
        if field.field_type == FieldType.DATE:
            return date.today().isoformat()
        return f"{field.label} (Contoh)"

    def _sample_data(self, fields: list[TemplateField]) -> dict:
        """Build the full sample-data dict: applicant defaults + one entry per field."""
        data = dict(_SAMPLE_APPLICANT)
        for field in fields:
            data[field.field_key] = self._sample_value(field)
        return data

    def _preview_number(self, template: LetterTemplate) -> str:
        """Render the numbering pattern with seq=1 and the current year."""
        return template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=1, year=date.today().year
        )

    def _render_document(
        self, *, template: LetterTemplate, village: Village, data: dict,
        nomor: str, tanggal: str, signer_name: str, qr_data_uri: str | None = None,
    ) -> bytes:
        """Shared core: interpolate the body, wrap in the letterhead, render to PDF.

        Both render_preview and render_issued funnel through this single
        method so the xhtml2pdf security hardening (link_callback blocking
        external resources + socket timeout) is defined and applied in
        exactly one place.
        """
        body_tpl = self._env.from_string(template.pdf_body_template)
        body_html = body_tpl.render(**data)

        letterhead_tpl = self._env.from_string(_LETTERHEAD)
        full_html = letterhead_tpl.render(
            kabupaten=village.kabupaten or "-",
            kecamatan=village.kecamatan or "-",
            village_name=village.name,
            letter_title=template.name.upper(),
            nomor=nomor,
            body=body_html,
            tanggal=tanggal,
            signer_name=signer_name,
            qr_data_uri=qr_data_uri or "",
        )
        buffer = io.BytesIO()
        previous_timeout = socket.getdefaulttimeout()
        try:
            socket.setdefaulttimeout(_RENDER_SOCKET_TIMEOUT_SECONDS)
            result = pisa.CreatePDF(
                full_html, dest=buffer, link_callback=_block_external_resources
            )
        finally:
            socket.setdefaulttimeout(previous_timeout)
        if result.err:
            raise AppException("Gagal merender PDF surat", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()

    def render_preview(
        self, template: LetterTemplate, fields: list[TemplateField], village: Village
    ) -> bytes:
        """Render a PDF preview of a template using auto-generated sample data."""
        return self._render_document(
            template=template, village=village, data=self._sample_data(fields),
            nomor=self._preview_number(template),
            tanggal=date.today().strftime("%d %B %Y"),
            signer_name="(Contoh Tanda Tangan)",
        )

    def render_issued(
        self, *, template: LetterTemplate, fields: list[TemplateField], village: Village,
        answers: dict, applicant: dict, nomor: str, tanggal: str, signer_name: str,
        qr_data_uri: str,
    ) -> bytes:
        """Render the real issued letter using actual submission answers.

        ``fields`` is accepted (matching render_preview's signature shape)
        but not used to derive data here — real answers/applicant data are
        passed in directly by the caller (SubmissionService), which already
        validated them against the template's fields at submission time.
        """
        data = {**applicant, **answers}
        return self._render_document(
            template=template, village=village, data=data, nomor=nomor,
            tanggal=tanggal, signer_name=signer_name, qr_data_uri=qr_data_uri,
        )
```

Note: `fields` stays an explicit parameter on `render_issued` even though this implementation
doesn't consume it, to keep the two render entry points' signatures visually parallel and
because a future caller (e.g. a richer field-type-aware formatter) is a natural extension
point — not a currently-unused parameter that should be removed; `ruff` will not flag it since
it's a normal function parameter, not an unused local variable.

- [ ] **Step 4: Run** — `pytest tests/test_template_render.py -v` → PASS (all tests, old and new)

- [ ] **Step 5: Also run the full existing template-engine test suite to confirm no regression**

Run: `pytest tests/test_letter_template_api.py -v` → PASS (Bundle E's preview endpoint test
must still pass unchanged).

- [ ] **Step 6: Commit**

```bash
git add app/services/template_render.py tests/test_template_render.py
git commit -m "refactor(templates): extract shared render core, add render_issued for real letters"
```

---

### Task 7: Submission domain schemas

**Files:**
- Create: `app/schemas/submission.py`

**Interfaces:**
- Produces:
  - `ApprovalStepConfigRead` (`id, village_id, order_index, role_id`), `ApprovalStepReplaceItem`
    (`role_id: UUID`), `ApprovalStepsReplaceRequest` (`steps: list[ApprovalStepReplaceItem]`).
  - `SubmissionCreate` (`template_id: UUID, answers: dict`), `SubmissionRead` (all `Submission`
    columns), `SubmissionRejectRequest` (`reason: str`), `SubmissionApproveRequest`
    (`note: str | None`).
  - `SubmissionStatusHistoryRead` (`id, step_index, action, actor_user_id, note, created_at`).
  - `SubmissionAttachmentRead` (`id, document_label, original_filename, content_type,
    size_bytes, uploaded_at` — aliased from `created_at`).

- [ ] **Step 1: Implement `app/schemas/submission.py`**

```python
"""Schemas for approval-step config, submissions, history, and attachments."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.submission import HistoryAction, SubmissionStatus


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class ApprovalStepConfigRead(_Read):
    village_id: UUID
    order_index: int
    role_id: UUID


class ApprovalStepReplaceItem(BaseModel):
    role_id: UUID


class ApprovalStepsReplaceRequest(BaseModel):
    steps: list[ApprovalStepReplaceItem] = Field(min_length=1)


class SubmissionCreate(BaseModel):
    template_id: UUID
    answers: dict = Field(default_factory=dict)


class SubmissionRejectRequest(BaseModel):
    reason: str = Field(min_length=1)


class SubmissionApproveRequest(BaseModel):
    note: str | None = None


class SubmissionRead(_Read):
    village_id: UUID
    template_id: UUID
    submitted_by_user_id: UUID
    answers: dict
    status: SubmissionStatus
    current_step_index: int | None = None
    letter_number: str | None = None
    verification_code: str | None = None
    rejection_reason: str | None = None
    rejected_by_user_id: UUID | None = None
    rejected_at: datetime | None = None
    issued_at: datetime | None = None
    created_at: datetime


class SubmissionStatusHistoryRead(_Read):
    step_index: int | None = None
    action: HistoryAction
    actor_user_id: UUID | None = None
    note: str | None = None
    created_at: datetime


class SubmissionAttachmentRead(_Read):
    document_label: str
    original_filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class PublicVerifyRead(BaseModel):
    """Public-safe view of an issued letter — no PII beyond the applicant's own name."""

    letter_number: str
    template_name: str
    applicant_name: str
    issued_at: datetime
    signed_by: str
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from app.schemas.submission import SubmissionRead, PublicVerifyRead, ApprovalStepsReplaceRequest"`

Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/submission.py
git commit -m "feat(submissions): approval-config/submission/history/attachment schemas"
```

---

### Task 8: `ApprovalStepConfigService` + API router

**Files:**
- Create: `app/services/approval_config.py`
- Create: `app/api/v1/approval_config.py`
- Modify: `app/api/v1/__init__.py`
- Test: `tests/test_approval_config_service.py`, `tests/test_approval_config_api.py`

**Interfaces:**
- Produces `ApprovalStepConfigService(session)`:
  - `async list_steps(village_id: UUID) -> list[ApprovalStepConfig]` — ordered by `order_index`.
  - `async replace_all(village_id: UUID, role_ids: list[UUID]) -> list[ApprovalStepConfig]` —
    raises `ValidationAppError` (409-mapped by the existing `IntegrityError` handler is NOT
    what's used here — raise a dedicated `ConflictError`, already in `app/core/exceptions.py`)
    if any `Submission` with `status=PENDING` exists for the village. Deletes all existing
    steps and creates the new ordered list in one transaction.
- Routes: `GET /approval-steps?village_id=...` (`template:read`), `PUT /approval-steps`
  (`approval_config:manage`, body includes `village_id` + `steps`).

- [ ] **Step 1: Write failing test** `tests/test_approval_config_service.py`

```python
import pytest
from app.core.exceptions import ConflictError
from app.models.auth import Role
from app.models.submission import Submission, SubmissionStatus
from app.services.approval_config import ApprovalStepConfigService
from app.services.master import VillageService
from sqlalchemy import select


@pytest.mark.asyncio
async def test_replace_all_then_list(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    roles = {
        r.name: r for r in (await seeded_session.scalars(select(Role))).all()
    }
    svc = ApprovalStepConfigService(seeded_session)
    steps = await svc.replace_all(
        village.id, [roles["staf"].id, roles["sekretaris"].id, roles["kades"].id]
    )
    assert [s.order_index for s in steps] == [0, 1, 2]
    listed = await svc.list_steps(village.id)
    assert [s.role_id for s in listed] == [roles["staf"].id, roles["sekretaris"].id, roles["kades"].id]


@pytest.mark.asyncio
async def test_replace_all_rejected_when_pending_submission_exists(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    roles = {r.name: r for r in (await seeded_session.scalars(select(Role))).all()}
    svc = ApprovalStepConfigService(seeded_session)
    await svc.replace_all(village.id, [roles["staf"].id])
    seeded_session.add(Submission(
        village_id=village.id,
        template_id="00000000-0000-0000-0000-000000000000",
        submitted_by_user_id="00000000-0000-0000-0000-000000000000",
        answers={}, status=SubmissionStatus.PENDING, current_step_index=0,
    ))
    await seeded_session.commit()
    with pytest.raises(ConflictError):
        await svc.replace_all(village.id, [roles["kades"].id])
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/approval_config.py`**

```python
"""Approval workflow configuration service: village-scoped ordered steps."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.models.submission import ApprovalStepConfig, Submission, SubmissionStatus

logger = get_logger("approval_config")


class ApprovalStepConfigService:
    """Manages a village's ordered approval-step chain."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_steps(self, village_id: uuid.UUID) -> list[ApprovalStepConfig]:
        """Return a village's approval steps, ordered."""
        stmt = (
            select(ApprovalStepConfig)
            .where(
                ApprovalStepConfig.village_id == village_id,
                ApprovalStepConfig.deleted_at.is_(None),
            )
            .order_by(ApprovalStepConfig.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    async def replace_all(
        self, village_id: uuid.UUID, role_ids: list[uuid.UUID]
    ) -> list[ApprovalStepConfig]:
        """Replace a village's entire approval-step chain atomically.

        Rejected with ConflictError if any Submission for the village is
        currently PENDING — reconfiguring mid-flight would leave those
        submissions' current_step_index pointing at a step that may no
        longer exist. Reconfiguration is expected to be a rare admin
        action, not a routine one, so this simple guard is sufficient.
        """
        pending_count = await self.session.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.village_id == village_id,
                Submission.status == SubmissionStatus.PENDING,
            )
        )
        if pending_count:
            raise ConflictError(
                "Tidak dapat mengubah alur persetujuan selagi ada pengajuan yang masih berjalan"
            )

        existing = await self.list_steps(village_id)
        for step in existing:
            await self.session.delete(step)
        await self.session.flush()

        new_steps = [
            ApprovalStepConfig(village_id=village_id, order_index=index, role_id=role_id)
            for index, role_id in enumerate(role_ids)
        ]
        self.session.add_all(new_steps)
        await self.session.commit()
        logger.info("Approval steps replaced village_id=%s count=%d", village_id, len(new_steps))
        return await self.list_steps(village_id)
```

- [ ] **Step 4: Verify `ConflictError` exists**

Run: `python -c "from app.core.exceptions import ConflictError; ConflictError('x')"`

Expected: no error (this class already exists from Foundation — `app/core/exceptions.py`).

- [ ] **Step 5: Run** — `pytest tests/test_approval_config_service.py -v` → PASS

- [ ] **Step 6: Write failing API test** `tests/test_approval_config_api.py`

```python
import pytest


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_replace_and_list_approval_steps(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    village_id = village.json()["data"]["id"]

    roles = await client.get("/api/v1/templates", headers=h)  # warm-up call, ensures auth ok
    assert roles.status_code == 200

    # Fetch role ids via a direct DB-agnostic approach: log in as each demo
    # account and read /auth/me is NOT sufficient (no role id in payload),
    # so use the seeded role names through a small lookup helper instead.
    from app.models.auth import Role
    from sqlalchemy import select

    put_resp = None  # placeholder to keep structure; replaced by real ids below


@pytest.mark.asyncio
async def test_replace_requires_manage_permission(client):
    tok = await _token(client, "kades", "kades123")
    resp = await client.put(
        "/api/v1/approval-steps",
        json={"village_id": "00000000-0000-0000-0000-000000000000", "steps": []},
        headers={"Authorization": f"Bearer {tok}"},
    )
    assert resp.status_code == 403
```

Note for the implementer: `test_replace_and_list_approval_steps` as drafted above needs real
role UUIDs, which aren't obtainable through the HTTP API alone (no `/roles` listing endpoint
exists in this plan). Rewrite that test to query role ids directly from the test DB session —
the `client` fixture's underlying test engine is reachable via a new `db_session`-style
fixture parameter, OR simpler: query roles through a raw SQL statement using the same
`_engine`/sessionmaker pattern already used elsewhere in `tests/conftest.py`. Use this
concrete version instead of the placeholder above:

```python
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
            "steps": [{"role_id": roles["staf"]}, {"role_id": roles["kades"]}],
        },
        headers=h,
    )
    assert put_resp.status_code == 200
    assert len(put_resp.json()["data"]) == 2

    get_resp = await client.get(f"/api/v1/approval-steps?village_id={village_id}", headers=h)
    assert get_resp.status_code == 200
    assert len(get_resp.json()["data"]) == 2
```

This relies on `db_session` and `client` sharing the same underlying test database — confirm
this is true for the existing `tests/conftest.py` fixtures (both `db_session` and `client` are
built from the same `_engine` fixture, so they do share state) before relying on it; if for
any reason they don't share state in practice, have `client`'s dependency-injected DB session
be the one used to query roles instead (e.g., by adding a small authenticated `GET` that
returns role list, or by having the test create roles it can reference — pick whichever is
simpler once you see the fixtures behave).

- [ ] **Step 7: Run** — FAIL (no router yet)

- [ ] **Step 8: Implement `app/api/v1/approval_config.py`**

```python
"""Village approval-step configuration endpoints."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.schemas.submission import ApprovalStepConfigRead, ApprovalStepsReplaceRequest
from app.services.approval_config import ApprovalStepConfigService

router = APIRouter(tags=["approval-config"])


@router.get("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def list_approval_steps(
    village_id: UUID = Query(...),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List a village's ordered approval steps."""
    steps = await ApprovalStepConfigService(session).list_steps(village_id)
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps]
    )


class _ReplaceBody(ApprovalStepsReplaceRequest):
    village_id: UUID


@router.put("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def replace_approval_steps(
    body: _ReplaceBody,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("approval_config:manage")),
) -> dict:
    """Replace a village's entire approval-step chain."""
    steps = await ApprovalStepConfigService(session).replace_all(
        body.village_id, [item.role_id for item in body.steps]
    )
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps],
        "Alur persetujuan diperbarui",
    )
```

- [ ] **Step 9: Register router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import approval_config, auth, health, letter_template, master

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
```

- [ ] **Step 10: Run** — `pytest tests/test_approval_config_api.py -v` → PASS

- [ ] **Step 11: Commit**

```bash
git add app/services/approval_config.py app/api/v1/approval_config.py app/api/v1/__init__.py tests/test_approval_config_service.py tests/test_approval_config_api.py
git commit -m "feat(submissions): approval-step config service + API"
```

---

### Task 9: `LetterNumberService` — atomic allocation

**Files:**
- Create: `app/services/letter_number.py`
- Test: `tests/test_letter_number.py`

**Interfaces:**
- Produces `LetterNumberService(session)`:
  - `async allocate(template_id: UUID, year: int) -> int` — atomically returns the next
    sequence number for `(template_id, year)`, starting at 1.

- [ ] **Step 1: Write failing test** `tests/test_letter_number.py`

```python
import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.services.letter_number import LetterNumberService


@pytest.mark.asyncio
async def test_allocate_sequential(db_session):
    template_id = uuid.uuid4()
    svc = LetterNumberService(db_session)
    assert await svc.allocate(template_id, 2026) == 1
    assert await svc.allocate(template_id, 2026) == 2
    assert await svc.allocate(template_id, 2026) == 3
    # a different year restarts the sequence
    assert await svc.allocate(template_id, 2027) == 1


@pytest.mark.asyncio
async def test_allocate_concurrent_no_duplicates(_engine):
    """N concurrent allocations for the same (template_id, year) must return
    N distinct sequence numbers {1..N} with no duplicates and no gaps."""
    template_id = uuid.uuid4()
    maker = async_sessionmaker(_engine, expire_on_commit=False)
    n = 10

    async def _allocate_one() -> int:
        async with maker() as session:
            return await LetterNumberService(session).allocate(template_id, 2026)

    results = await asyncio.gather(*[_allocate_one() for _ in range(n)])
    assert sorted(results) == list(range(1, n + 1))
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/letter_number.py`**

```python
"""Atomic per-(template, year) letter-number sequence allocation."""
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.submission import LetterNumberCounter

logger = get_logger("letter_number")


class LetterNumberService:
    """Allocates letter sequence numbers without a SELECT-then-UPDATE race window."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def allocate(self, template_id: uuid.UUID, year: int) -> int:
        """Atomically allocate and return the next sequence number.

        Uses a single INSERT ... ON CONFLICT DO UPDATE ... RETURNING
        statement (dialect-appropriate: Postgres in production, SQLite in
        tests — both support this) so concurrent allocations for the same
        (template_id, year) can never observe or return the same number.
        No explicit row locking or application-level retry loop is needed;
        the database enforces atomicity via the unique constraint.
        """
        insert_fn = pg_insert if self.session.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = (
            insert_fn(LetterNumberCounter)
            .values(template_id=template_id, year=year, last_seq=1)
            .on_conflict_do_update(
                index_elements=["template_id", "year"],
                set_={"last_seq": LetterNumberCounter.__table__.c.last_seq + 1},
            )
            .returning(LetterNumberCounter.last_seq)
        )
        result = await self.session.execute(stmt)
        seq = result.scalar_one()
        await self.session.commit()
        logger.info("Letter number allocated template_id=%s year=%d seq=%d", template_id, year, seq)
        return seq
```

- [ ] **Step 4: Run** — `pytest tests/test_letter_number.py -v` → PASS

The concurrent test is the important one — if it's flaky or fails with duplicate numbers, the
`on_conflict_do_update` statement is not achieving atomicity on this SQLite version; re-check
the dialect branch and the exact upsert syntax before proceeding, do not weaken the test.

- [ ] **Step 5: Commit**

```bash
git add app/services/letter_number.py tests/test_letter_number.py
git commit -m "feat(submissions): atomic letter-number allocation, race-condition tested"
```

---

### Task 10: `SubmissionService` — creation + validation

**Files:**
- Create: `app/services/notification.py`
- Create: `app/services/submission.py`
- Test: `tests/test_submission_service.py`

**Interfaces:**
- Produces `notify_status_change(submission: Submission, event: str) -> None` (sync, just logs
  — the Phase 8 integration point).
- Produces `SubmissionService(session)`:
  - `async create(user: User, template_id: UUID, answers: dict) -> Submission`
  - `async get_or_404(id_: UUID) -> Submission`
  - `async list(user: User, page: int, size: int) -> tuple[list[Submission], int]` — if
    `"submission:read_all" in user_permissions or "*" in user_permissions`: all rows for the
    village; else: only rows where `submitted_by_user_id == user.id`. (This method takes the
    resolved permission list, not just the `User` row — see Task 13's router for how it's
    called; keep the signature `list(self, actor_permissions: list[str], actor_user_id: UUID,
    page: int, size: int)` so the service has everything it needs without importing the auth
    dependency module.)

- [ ] **Step 1: Write failing test** `tests/test_submission_service.py`

```python
import pytest
from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.auth import Role, User
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService
from app.services.submission import SubmissionService


async def _make_template_with_fields(session, village_id):
    svc = LetterTemplateService(session)
    template = await svc.create({
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ alamat_tinggal_saat_ini }}</p>",
    })
    await svc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat Tinggal Saat Ini",
        "field_type": "text", "is_required": True,
    })
    await svc.add_field(template.id, {
        "field_key": "keperluan", "label": "Keperluan", "field_type": "select",
        "options": ["Bank", "Sekolah"], "is_required": True,
    })
    return template


async def _make_warga_user(session, username: str) -> User:
    """Create a warga-role User for a test, using the seeded 'warga' Role row."""
    role = (await session.scalars(select(Role).where(Role.name == "warga"))).first()
    user = User(username=username, full_name="Warga Test", hashed_password="x", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_create_validates_required_fields(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {"alamat_tinggal_saat_ini": ""})  # missing keperluan


@pytest.mark.asyncio
async def test_create_validates_select_options(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test2")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {
            "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "NotAnOption",
        })


@pytest.mark.asyncio
async def test_create_succeeds_with_valid_answers(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test3")

    svc = SubmissionService(seeded_session)
    obj = await svc.create(user, template.id, {
        "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank",
    })
    assert obj.status.value == "pending"
    assert obj.current_step_index == 0

    got = await svc.get_or_404(obj.id)
    assert got.answers["keperluan"] == "Bank"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/notification.py`**

```python
"""Notification hook stub — the Phase 8 integration point.

Real WhatsApp/Email dispatch through an ARQ queue is out of scope here;
this function only logs, so status-transition call sites (SubmissionService)
already have a clean place to call into once Phase 8 builds the real sender.
"""
from app.core.logging import get_logger
from app.models.submission import Submission

logger = get_logger("notification")


def notify_status_change(submission: Submission, event: str) -> None:
    """Log a submission status-change event (stub for future dispatch)."""
    logger.info(
        "Notification stub: submission_id=%s event=%s status=%s",
        submission.id, event, submission.status.value,
    )
```

- [ ] **Step 4: Implement `app/services/submission.py`**

```python
"""Submission service: creation with answer validation against TemplateField."""
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.models.auth import User
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import FamilyCard, Resident
from app.models.submission import Submission, SubmissionStatus, SubmissionStatusHistory, HistoryAction
from app.repositories.base import BaseRepository
from app.services.notification import notify_status_change

logger = get_logger("submission")


class SubmissionService:
    """Business logic for the submission lifecycle: creation and querying.

    Approval/reject/issuance are added to this same class in Task 12.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, Submission)
        self.template_repo = BaseRepository(session, LetterTemplate)

    async def _list_template_fields(self, template_id: uuid.UUID) -> list[TemplateField]:
        stmt = (
            select(TemplateField)
            .where(TemplateField.template_id == template_id, TemplateField.deleted_at.is_(None))
            .order_by(TemplateField.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    def _validate_answers(self, fields: list[TemplateField], answers: dict) -> None:
        """Validate submitted answers against the template's field definitions.

        Collects ALL errors before raising (not just the first) so the
        client can fix everything in one round-trip.
        """
        errors: list[str] = []
        for field in fields:
            value = answers.get(field.field_key)
            is_empty = value is None or value == ""
            if field.is_required and is_empty:
                errors.append(f"{field.label} wajib diisi")
                continue
            if is_empty:
                continue
            if field.field_type == FieldType.SELECT and field.options and value not in field.options:
                errors.append(f"{field.label}: pilihan tidak valid")
            if field.field_type == FieldType.NUMBER:
                try:
                    float(value)
                except (TypeError, ValueError):
                    errors.append(f"{field.label} harus berupa angka")
        if errors:
            raise ValidationAppError("; ".join(errors))

    async def resolve_applicant_data(self, user: User) -> dict:
        """Build {nama, nik, alamat, no_kk} for auto-fill and PDF placeholders.

        Falls back to User fields if the user has no linked Resident (should
        not happen for the seeded demo warga account after Task 15's seed
        link, but keeps this from hard-failing if it ever does).
        """
        fallback = {"nama": user.full_name, "nik": user.nik or "-", "alamat": "-", "no_kk": "-"}
        if user.resident_id is None:
            return fallback
        resident = await self.session.get(Resident, user.resident_id)
        if resident is None:
            return fallback
        kk_number = "-"
        if resident.family_card_id is not None:
            fc = await self.session.get(FamilyCard, resident.family_card_id)
            if fc is not None:
                kk_number = fc.kk_number
        return {
            "nama": resident.full_name, "nik": resident.nik,
            "alamat": resident.address or "-", "no_kk": kk_number,
        }

    async def create(self, user: User, template_id: uuid.UUID, answers: dict[str, Any]) -> Submission:
        """Create a new submission after validating answers against the template."""
        template = await self.template_repo.get(template_id)
        if template is None or not template.is_active:
            raise NotFoundError("Template surat tidak ditemukan atau tidak aktif")
        fields = await self._list_template_fields(template_id)
        self._validate_answers(fields, answers)

        obj = Submission(
            village_id=template.village_id, template_id=template_id,
            submitted_by_user_id=user.id, answers=answers,
            status=SubmissionStatus.PENDING, current_step_index=0,
        )
        self.session.add(obj)
        await self.session.flush()
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=0, action=HistoryAction.SUBMITTED,
            actor_user_id=user.id, note=None,
        ))
        await self.session.commit()
        logger.info("Submission created id=%s template_id=%s user_id=%s", obj.id, template_id, user.id)
        notify_status_change(obj, "submitted")
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> Submission:
        """Return the submission with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("Pengajuan tidak ditemukan")
        return obj

    async def list(
        self, actor_permissions: list[str], actor_user_id: uuid.UUID,
        page: int = 1, size: int = 20,
    ) -> tuple[list[Submission], int]:
        """List submissions: all rows for staff (submission:read_all/"*"), else own only."""
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        filters = {} if can_read_all else {"submitted_by_user_id": actor_user_id}
        return await self.repo.list(page=page, size=size, filters=filters)
```

- [ ] **Step 5: Run** — `pytest tests/test_submission_service.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/services/notification.py app/services/submission.py tests/test_submission_service.py
git commit -m "feat(submissions): SubmissionService creation with answer validation"
```

---

### Task 11: `SubmissionService` — attachment upload

**Files:**
- Modify: `app/services/submission.py`
- Modify: `tests/test_submission_service.py`

**Interfaces:**
- Consumes: `FileStorageService` (Task 4).
- Produces (added to `SubmissionService`):
  - `async add_attachment(submission_id: UUID, document_label: str, filename: str,
    content: bytes, content_type: str) -> SubmissionAttachment` — validates via
    `FileStorageService.validate_upload`, validates `document_label` is one of the
    submission's template's `required_documents`, saves the file, persists the row.

- [ ] **Step 1: Write failing test** — append to `tests/test_submission_service.py`

```python
@pytest.mark.asyncio
async def test_add_attachment_validates_document_label(seeded_session, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
        })(),
    )
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    tsvc = LetterTemplateService(seeded_session)
    template = await tsvc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p></p>", "required_documents": ["KTP"],
    })
    user = await _make_warga_user(seeded_session, "warga_att")

    svc = SubmissionService(seeded_session)
    submission = await svc.create(user, template.id, {})

    with pytest.raises(ValidationAppError):
        await svc.add_attachment(submission.id, "Bukan Dokumen Wajib", "x.png", b"abc", "image/png")

    att = await svc.add_attachment(submission.id, "KTP", "ktp.png", b"abc", "image/png")
    assert att.document_label == "KTP"
    assert att.original_filename == "ktp.png"
```

(`test_create_validates_required_fields`'s template didn't set `required_documents`; this new
test's template DOES, via `"required_documents": ["KTP"]` in the create payload — confirm
`LetterTemplateService.create` / `LetterTemplateCreate` schema already accept that field, which
they do, from B1.)

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Add to `app/services/submission.py`**

Add imports:
```python
from app.models.submission import SubmissionAttachment
from app.services.file_storage import FileStorageService
```

Append this method to `SubmissionService`:
```python
    async def add_attachment(
        self, submission_id: uuid.UUID, document_label: str, filename: str,
        content: bytes, content_type: str,
    ) -> SubmissionAttachment:
        """Validate and store an uploaded attachment for a submission."""
        submission = await self.get_or_404(submission_id)
        template = await self.template_repo.get(submission.template_id)
        if template is None or document_label not in template.required_documents:
            raise ValidationAppError(
                f"'{document_label}' bukan lampiran yang diperlukan untuk surat ini"
            )
        storage = FileStorageService()
        storage.validate_upload(content, content_type)
        storage_path = await storage.save(content, filename, subdir="attachments")

        attachment = SubmissionAttachment(
            submission_id=submission_id, document_label=document_label,
            original_filename=filename, stored_filename=storage_path.rsplit("/", 1)[-1],
            content_type=content_type, size_bytes=len(content), storage_path=storage_path,
        )
        self.session.add(attachment)
        await self.session.commit()
        logger.info("Attachment added submission_id=%s label=%s", submission_id, document_label)
        return attachment
```

- [ ] **Step 4: Run** — `pytest tests/test_submission_service.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/submission.py tests/test_submission_service.py
git commit -m "feat(submissions): attachment upload with document-label + file validation"
```

---

### Task 12: `SubmissionService` — approve, reject, and PDF issuance

This is the core of the sub-project: turn-taking enforcement, terminal reject, and automatic
issuance on final approval.

**Files:**
- Modify: `app/services/submission.py`
- Modify: `tests/test_submission_service.py`

**Interfaces:**
- Consumes: `ApprovalStepConfigService` (Task 8), `LetterNumberService` (Task 9),
  `TemplateRenderService.render_issued` (Task 6), `FileStorageService` (Task 4),
  `generate_qr_data_uri` (Task 5).
- Produces (added to `SubmissionService`):
  - `async approve(submission_id: UUID, actor: User, note: str | None) -> Submission`
  - `async reject(submission_id: UUID, actor: User, reason: str) -> Submission`
  - `async list_history(submission_id: UUID) -> list[SubmissionStatusHistory]`
  - `async download_pdf(submission_id: UUID, actor_user_id: UUID, actor_permissions: list[str])
    -> bytes` — enforces ownership (own submission or `submission:download`+`read_all`-tier),
    raises `ValidationAppError` if not yet `ISSUED`.

- [ ] **Step 1: Write failing test** — append to `tests/test_submission_service.py`

```python
from app.core.exceptions import ForbiddenError
from app.models.auth import Role
from app.services.approval_config import ApprovalStepConfigService
from sqlalchemy import select


async def _setup_pending_submission(session):
    """Village + 3-step workflow (staf, sekretaris, kades) + one PENDING submission."""
    village = await VillageService(session).create({"name": "Desa Kopo"})
    tsvc = LetterTemplateService(session)
    template = await tsvc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>",
    })
    await tsvc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    })
    roles = {r.name: r for r in (await session.scalars(select(Role))).all()}
    await ApprovalStepConfigService(session).replace_all(
        village.id, [roles["staf"].id, roles["sekretaris"].id, roles["kades"].id]
    )
    warga = User(username="warga_flow", full_name="Warga Flow", hashed_password="x",
                 role_id=roles["warga"].id)
    staf = User(username="staf_flow", full_name="Staf Flow", hashed_password="x",
                role_id=roles["staf"].id)
    sekdes = User(username="sekdes_flow", full_name="Sekdes Flow", hashed_password="x",
                  role_id=roles["sekretaris"].id)
    kades = User(username="kades_flow", full_name="Kades Flow", hashed_password="x",
                 role_id=roles["kades"].id)
    session.add_all([warga, staf, sekdes, kades])
    await session.flush()

    svc = SubmissionService(session)
    submission = await svc.create(warga, template.id, {"alamat_tinggal_saat_ini": "Jl. Uji 1"})
    return svc, submission, {"warga": warga, "staf": staf, "sekdes": sekdes, "kades": kades}


@pytest.mark.asyncio
async def test_approve_wrong_turn_rejected(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    with pytest.raises(ForbiddenError):
        await svc.approve(submission.id, users["sekdes"], None)  # staf's turn, not sekdes


@pytest.mark.asyncio
async def test_approve_full_chain_issues_pdf(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)

    s1 = await svc.approve(submission.id, users["staf"], "ok")
    assert s1.current_step_index == 1
    assert s1.status.value == "pending"

    s2 = await svc.approve(submission.id, users["sekdes"], "ok")
    assert s2.current_step_index == 2

    s3 = await svc.approve(submission.id, users["kades"], "signed")
    assert s3.status.value == "issued"
    assert s3.letter_number is not None
    assert s3.verification_code is not None
    assert s3.pdf_storage_path is not None
    assert s3.issued_at is not None

    pdf_bytes = await svc.download_pdf(submission.id, users["warga"].id, ["submission:download"])
    assert pdf_bytes[:5] == b"%PDF-"

    history = await svc.list_history(submission.id)
    actions = [h.action.value for h in history]
    assert actions == ["submitted", "approved", "approved", "issued"]


@pytest.mark.asyncio
async def test_reject_is_terminal(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    rejected = await svc.reject(submission.id, users["staf"], "Berkas tidak lengkap")
    assert rejected.status.value == "rejected"
    assert rejected.rejection_reason == "Berkas tidak lengkap"
    with pytest.raises(ValidationAppError):
        await svc.approve(submission.id, users["staf"], None)


@pytest.mark.asyncio
async def test_download_pdf_rejects_non_owner_without_read_all(seeded_session):
    svc, submission, users = await _setup_pending_submission(seeded_session)
    await svc.approve(submission.id, users["staf"], None)
    await svc.approve(submission.id, users["sekdes"], None)
    await svc.approve(submission.id, users["kades"], None)
    with pytest.raises(ForbiddenError):
        await svc.download_pdf(submission.id, users["staf"].id, ["submission:download"])
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Add to `app/services/submission.py`**

Add imports (`FileStorageService` is already imported from Task 11 — do not import it again,
just reuse that existing import):
```python
import secrets
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.exceptions import ForbiddenError
from app.models.master import Village
from app.services.approval_config import ApprovalStepConfigService
from app.services.letter_number import LetterNumberService
from app.services.qr import generate_qr_data_uri
from app.services.template_render import TemplateRenderService
```

Append these methods to `SubmissionService`:
```python
    async def list_history(self, submission_id: uuid.UUID) -> list[SubmissionStatusHistory]:
        """Return a submission's status history, oldest first."""
        await self.get_or_404(submission_id)
        stmt = (
            select(SubmissionStatusHistory)
            .where(SubmissionStatusHistory.submission_id == submission_id)
            .order_by(SubmissionStatusHistory.created_at)
        )
        return list((await self.session.scalars(stmt)).all())

    async def _resolve_signer_name(self) -> str:
        """Return the Kepala Desa's display name for the signature block.

        Single-village MVP: looks up the (single) user with role 'kades'.
        A multi-village deployment would need this scoped by village_id —
        a known, explicitly out-of-scope limitation while only one village
        exists in the system.
        """
        from app.models.auth import Role as _Role
        stmt = (
            select(User)
            .join(_Role, User.role_id == _Role.id)
            .where(_Role.name == "kades", User.deleted_at.is_(None))
            .limit(1)
        )
        kades = await self.session.scalar(stmt)
        return kades.full_name if kades else "Kepala Desa"

    def _generate_verification_code(self, village: Village, year: int) -> str:
        """Generate a unique, human-typeable verification code."""
        prefix = "".join(ch for ch in village.name.upper() if ch.isalpha())[:4] or "DESA"
        suffix = secrets.token_hex(3).upper()
        return f"{prefix}-{year}-{suffix}"

    async def _issue(self, submission: Submission, actor: User) -> None:
        """Allocate a real number, render the final PDF, and mark ISSUED."""
        template = await self.template_repo.get(submission.template_id)
        fields = await self._list_template_fields(submission.template_id)
        village = await self.session.get(Village, submission.village_id)
        submitter = await self.session.get(User, submission.submitted_by_user_id)
        applicant = await self.resolve_applicant_data(submitter)

        year = datetime.now(timezone.utc).year
        seq = await LetterNumberService(self.session).allocate(submission.template_id, year)
        letter_number = template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=seq, year=year
        )
        verification_code = self._generate_verification_code(village, year)

        base_url = get_settings().public_verify_base_url.rstrip("/")
        qr_data_uri = generate_qr_data_uri(f"{base_url}/{verification_code}")
        signer_name = await self._resolve_signer_name()
        tanggal = datetime.now(timezone.utc).strftime("%d %B %Y")

        pdf_bytes = TemplateRenderService().render_issued(
            template=template, fields=fields, village=village,
            answers=submission.answers, applicant=applicant, nomor=letter_number,
            tanggal=tanggal, signer_name=signer_name, qr_data_uri=qr_data_uri,
        )
        storage_path = await FileStorageService().save(
            pdf_bytes, f"{submission.id}.pdf", subdir="issued"
        )

        submission.status = SubmissionStatus.ISSUED
        submission.letter_number = letter_number
        submission.verification_code = verification_code
        submission.pdf_storage_path = storage_path
        submission.issued_at = datetime.now(timezone.utc)
        self.session.add(SubmissionStatusHistory(
            submission_id=submission.id, step_index=submission.current_step_index,
            action=HistoryAction.ISSUED, actor_user_id=actor.id, note=None,
        ))
        logger.info(
            "Submission issued id=%s letter_number=%s code=%s",
            submission.id, letter_number, verification_code,
        )

    async def approve(
        self, submission_id: uuid.UUID, actor: User, note: str | None
    ) -> Submission:
        """Advance a submission one step, or issue it if this was the final step."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")
        steps = await ApprovalStepConfigService(self.session).list_steps(obj.village_id)
        if not steps:
            raise ValidationAppError("Alur persetujuan desa belum dikonfigurasi")
        current_step = steps[obj.current_step_index]
        if current_step.role_id != actor.role_id:
            raise ForbiddenError("Bukan giliran Anda untuk memproses pengajuan ini")

        is_last_step = obj.current_step_index == len(steps) - 1
        if is_last_step:
            await self._issue(obj, actor)
        else:
            obj.current_step_index += 1
            self.session.add(SubmissionStatusHistory(
                submission_id=obj.id, step_index=obj.current_step_index,
                action=HistoryAction.APPROVED, actor_user_id=actor.id, note=note,
            ))
        await self.session.commit()
        logger.info("Submission approve processed id=%s by=%s", obj.id, actor.id)
        notify_status_change(obj, "issued" if is_last_step else "approved")
        return obj

    async def reject(self, submission_id: uuid.UUID, actor: User, reason: str) -> Submission:
        """Reject a submission (terminal) with a mandatory reason."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.PENDING:
            raise ValidationAppError("Pengajuan ini sudah tidak dalam status menunggu proses")
        steps = await ApprovalStepConfigService(self.session).list_steps(obj.village_id)
        if not steps:
            raise ValidationAppError("Alur persetujuan desa belum dikonfigurasi")
        current_step = steps[obj.current_step_index]
        if current_step.role_id != actor.role_id:
            raise ForbiddenError("Bukan giliran Anda untuk memproses pengajuan ini")

        obj.status = SubmissionStatus.REJECTED
        obj.rejection_reason = reason
        obj.rejected_by_user_id = actor.id
        obj.rejected_at = datetime.now(timezone.utc)
        self.session.add(SubmissionStatusHistory(
            submission_id=obj.id, step_index=obj.current_step_index,
            action=HistoryAction.REJECTED, actor_user_id=actor.id, note=reason,
        ))
        await self.session.commit()
        logger.info("Submission rejected id=%s by=%s", obj.id, actor.id)
        notify_status_change(obj, "rejected")
        return obj

    async def download_pdf(
        self, submission_id: uuid.UUID, actor_user_id: uuid.UUID, actor_permissions: list[str]
    ) -> bytes:
        """Return the issued PDF's bytes, enforcing ownership or read_all."""
        obj = await self.get_or_404(submission_id)
        if obj.status != SubmissionStatus.ISSUED or obj.pdf_storage_path is None:
            raise ValidationAppError("Surat belum terbit")
        can_read_all = "*" in actor_permissions or "submission:read_all" in actor_permissions
        if not can_read_all and obj.submitted_by_user_id != actor_user_id:
            raise ForbiddenError("Anda tidak berhak mengunduh surat ini")
        return await FileStorageService().read(obj.pdf_storage_path)
```

- [ ] **Step 4: Run** — `pytest tests/test_submission_service.py -v` → PASS (all tests, including
  the full approve-chain-issues-PDF test — this is the most important test in the whole plan;
  if it fails, debug thoroughly before moving on, do not skip or weaken it)

- [ ] **Step 5: Run the full suite to confirm no regression**

Run: `pytest -q` → all PASS.

- [ ] **Step 6: Commit**

```bash
git add app/services/submission.py tests/test_submission_service.py
git commit -m "feat(submissions): approve/reject with turn enforcement, automatic PDF issuance"
```

---

### Task 13: Submission API router

**Files:**
- Create: `app/api/v1/submission.py`
- Modify: `app/api/v1/__init__.py`
- Test: `tests/test_submission_api.py`

**Interfaces:**
- Consumes: `SubmissionService`, `require_permission`, `get_current_user` (for the list/ownership
  scoping — the router needs `CurrentUser.permissions` and the underlying `User` row).
- Routes: `POST /submissions`, `GET /submissions`, `GET /submissions/{id}`,
  `POST /submissions/{id}/attachments`, `POST /submissions/{id}/approve`,
  `POST /submissions/{id}/reject`, `GET /submissions/{id}/history`,
  `GET /submissions/{id}/pdf`.

- [ ] **Step 1: Write failing test** `tests/test_submission_api.py`

```python
import pytest
from sqlalchemy import select

from app.models.auth import Role


async def _token(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


async def _setup_village_template_workflow(client, db_session):
    admin_tok = await _token(client, "operator", "operator123")
    h = {"Authorization": f"Bearer {admin_tok}"}
    village = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    village_id = village.json()["data"]["id"]

    template = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }} - {{ alamat_tinggal_saat_ini }}</p>",
        "required_documents": ["KTP"],
    }, headers=h)
    template_id = template.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat", "field_type": "text",
        "is_required": True,
    }, headers=h)

    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}
    await client.put("/api/v1/approval-steps", json={
        "village_id": village_id,
        "steps": [{"role_id": roles["staf"]}, {"role_id": roles["kades"]}],
    }, headers=h)
    return village_id, template_id


@pytest.mark.asyncio
async def test_full_submission_lifecycle_via_api(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
            "public_verify_base_url": "http://localhost:5173/verify",
        })(),
    )
    village_id, template_id = await _setup_village_template_workflow(client, db_session)

    warga_tok = await _token(client, "warga", "warga123")
    wh = {"Authorization": f"Bearer {warga_tok}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji 99"},
    }, headers=wh)
    assert created.status_code == 200
    submission_id = created.json()["data"]["id"]

    mine = await client.get("/api/v1/submissions", headers=wh)
    assert mine.json()["data"]["total"] == 1

    staf_tok = await _token(client, "staf", "staf123")
    sh = {"Authorization": f"Bearer {staf_tok}"}
    approve1 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "ok"}, headers=sh
    )
    assert approve1.status_code == 200
    assert approve1.json()["data"]["status"] == "pending"

    kades_tok = await _token(client, "kades", "kades123")
    kh = {"Authorization": f"Bearer {kades_tok}"}
    approve2 = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "signed"}, headers=kh
    )
    assert approve2.status_code == 200
    body = approve2.json()["data"]
    assert body["status"] == "issued"
    assert body["letter_number"]
    assert body["verification_code"]

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=wh)
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"

    history = await client.get(f"/api/v1/submissions/{submission_id}/history", headers=wh)
    assert [h["action"] for h in history.json()["data"]] == ["submitted", "approved", "issued"]


@pytest.mark.asyncio
async def test_approve_wrong_turn_returns_403(client, db_session):
    village_id, template_id = await _setup_village_template_workflow(client, db_session)
    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {"alamat_tinggal_saat_ini": "Jl. Uji"},
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    kades_tok = await _token(client, "kades", "kades123")  # staf's turn, not kades
    resp = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={},
        headers={"Authorization": f"Bearer {kades_tok}"},
    )
    assert resp.status_code == 403
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/api/v1/submission.py`**

```python
"""Submission lifecycle endpoints: create, list, attach, approve, reject, download."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import User
from app.schemas.common import Page, build_page
from app.schemas.submission import (
    SubmissionApproveRequest, SubmissionAttachmentRead, SubmissionCreate, SubmissionRead,
    SubmissionRejectRequest, SubmissionStatusHistoryRead,
)
from app.services.submission import SubmissionService

router = APIRouter(tags=["submissions"])


async def _load_user(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User row for the authenticated principal."""
    from uuid import UUID as _UUID
    user = await session.get(User, _UUID(current.id))
    return user


@router.post("/submissions", response_model=Envelope[SubmissionRead])
async def create_submission(
    body: SubmissionCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Create a new letter submission."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).create(user, body.template_id, body.answers)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/submissions", response_model=Envelope[Page[SubmissionRead]])
async def list_submissions(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """List submissions: own only, unless the caller has submission:read_all."""
    from uuid import UUID as _UUID
    items, total = await SubmissionService(session).list(
        current.permissions, _UUID(current.id), p.page, p.size
    )
    return success_response(build_page(items, total, p.page, p.size, SubmissionRead))


@router.get("/submissions/{submission_id}", response_model=Envelope[SubmissionRead])
async def get_submission(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """Get a single submission by id."""
    obj = await SubmissionService(session).get_or_404(submission_id)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"))


@router.post("/submissions/{submission_id}/attachments", response_model=Envelope[SubmissionAttachmentRead])
async def upload_attachment(
    submission_id: UUID,
    document_label: str = Form(...),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:create")),
) -> dict:
    """Upload a supporting document for a submission."""
    content = await file.read()
    obj = await SubmissionService(session).add_attachment(
        submission_id, document_label, file.filename or "upload",
        content, file.content_type or "application/octet-stream",
    )
    return success_response(
        SubmissionAttachmentRead.model_validate(obj).model_dump(mode="json"), "Lampiran tersimpan"
    )


@router.post("/submissions/{submission_id}/approve", response_model=Envelope[SubmissionRead])
async def approve_submission(
    submission_id: UUID,
    body: SubmissionApproveRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:approve")),
) -> dict:
    """Approve a submission at its current step (or issue it if this was the final step)."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).approve(submission_id, user, body.note)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Diproses")


@router.post("/submissions/{submission_id}/reject", response_model=Envelope[SubmissionRead])
async def reject_submission(
    submission_id: UUID,
    body: SubmissionRejectRequest,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:reject")),
) -> dict:
    """Reject a submission with a mandatory reason (terminal)."""
    user = await _load_user(session, current)
    obj = await SubmissionService(session).reject(submission_id, user, body.reason)
    return success_response(SubmissionRead.model_validate(obj).model_dump(mode="json"), "Ditolak")


@router.get("/submissions/{submission_id}/history", response_model=Envelope[list[SubmissionStatusHistoryRead]])
async def get_submission_history(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    _current: CurrentUser = Depends(require_permission("submission:read")),
) -> dict:
    """Return a submission's status history, oldest first."""
    history = await SubmissionService(session).list_history(submission_id)
    return success_response(
        [SubmissionStatusHistoryRead.model_validate(h).model_dump(mode="json") for h in history]
    )


@router.get("/submissions/{submission_id}/pdf")
async def download_submission_pdf(
    submission_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("submission:download")),
) -> StreamingResponse:
    """Download the issued PDF for a submission."""
    from uuid import UUID as _UUID
    pdf_bytes = await SubmissionService(session).download_pdf(
        submission_id, _UUID(current.id), current.permissions
    )
    return StreamingResponse(
        io.BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="surat-{submission_id}.pdf"'},
    )
```

`approve_submission` takes `body: SubmissionApproveRequest` (from Task 7) as a JSON request
body — consistent with `reject_submission`'s style, and matches what the test in Step 1 sends
(`json={"note": "ok"}`).

- [ ] **Step 4: Register router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import approval_config, auth, health, letter_template, master, submission

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
api_router.include_router(submission.router)
```

- [ ] **Step 5: Run** — `pytest tests/test_submission_api.py -v` → PASS

- [ ] **Step 6: Run full suite**

Run: `pytest -q` → all PASS.

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/submission.py app/api/v1/__init__.py app/schemas/submission.py tests/test_submission_api.py
git commit -m "feat(submissions): submission lifecycle API (create/list/attach/approve/reject/pdf)"
```

---

### Task 14: Public verification endpoint

**Files:**
- Create: `app/api/v1/public.py`
- Modify: `app/api/v1/__init__.py`
- Test: `tests/test_public_verify_api.py`

**Interfaces:**
- Route: `GET /public/verify/{code}` — **no auth dependency at all** (not even
  `get_current_user`). Returns `PublicVerifyRead` on a matching `ISSUED` submission; 404
  (uniform message, no format-vs-not-found distinction) otherwise.

- [ ] **Step 1: Write failing test** `tests/test_public_verify_api.py`

```python
import pytest
from sqlalchemy import select

from app.models.auth import Role


async def _token(client, username, password):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_public_verify_returns_letter_details_for_issued_code(client, db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.services.file_storage.get_settings",
        lambda: type("S", (), {
            "upload_storage_dir": str(tmp_path), "max_upload_size_bytes": 1024 * 1024,
            "public_verify_base_url": "http://localhost:5173/verify",
        })(),
    )
    admin_tok = await _token(client, "operator", "operator123")
    h = {"Authorization": f"Bearer {admin_tok}"}
    village = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    village_id = village.json()["data"]["id"]
    template = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    template_id = template.json()["data"]["id"]
    roles = {r.name: str(r.id) for r in (await db_session.scalars(select(Role))).all()}
    await client.put("/api/v1/approval-steps", json={
        "village_id": village_id, "steps": [{"role_id": roles["staf"]}],
    }, headers=h)

    warga_tok = await _token(client, "warga", "warga123")
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id, "answers": {},
    }, headers={"Authorization": f"Bearer {warga_tok}"})
    submission_id = created.json()["data"]["id"]

    staf_tok = await _token(client, "staf", "staf123")
    approved = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={},
        headers={"Authorization": f"Bearer {staf_tok}"},
    )
    code = approved.json()["data"]["verification_code"]

    # No Authorization header at all — must work unauthenticated.
    resp = await client.get(f"/api/v1/public/verify/{code}")
    assert resp.status_code == 200
    body = resp.json()["data"]
    assert body["letter_number"] == approved.json()["data"]["letter_number"]
    assert body["template_name"] == "Surat Domisili"


@pytest.mark.asyncio
async def test_public_verify_unknown_code_returns_404(client):
    resp = await client.get("/api/v1/public/verify/NOPE-2026-000000")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/api/v1/public.py`**

```python
"""Public, no-auth letter verification endpoint."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.models.auth import User
from app.models.letter_template import LetterTemplate
from app.models.submission import Submission, SubmissionStatus
from app.schemas.submission import PublicVerifyRead
from app.services.submission import SubmissionService

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/verify/{code}", response_model=Envelope[PublicVerifyRead])
async def verify_letter(code: str, session: AsyncSession = Depends(get_db)) -> dict:
    """Publicly verify an issued letter by its verification code. No auth required."""
    submission = await session.scalar(
        select(Submission).where(
            Submission.verification_code == code,
            Submission.status == SubmissionStatus.ISSUED,
        )
    )
    if submission is None:
        raise NotFoundError("Kode verifikasi tidak ditemukan")

    template = await session.get(LetterTemplate, submission.template_id)
    applicant = await SubmissionService(session).resolve_applicant_data(
        await session.get(User, submission.submitted_by_user_id)
    )
    signer_name = await SubmissionService(session)._resolve_signer_name()  # noqa: SLF001

    return success_response(PublicVerifyRead(
        letter_number=submission.letter_number or "",
        template_name=template.name if template else "",
        applicant_name=applicant["nama"],
        issued_at=submission.issued_at,
        signed_by=signer_name,
    ).model_dump(mode="json"))
```

Note: calling `SubmissionService(session)._resolve_signer_name()` reaches into a
name-mangled-looking-but-not-actually-private method (single leading underscore, Python
convention for "internal", not enforced). This is acceptable pragmatically here (it's the
exact same lookup `_issue` uses), but if a linter flags it (`ruff`'s `SLF001` private-member-
access rule), either add the inline `# noqa: SLF001` shown above, or promote
`_resolve_signer_name` to a public method (drop the leading underscore) on `SubmissionService`
since it's now called from two places (Task 12's `_issue` and here) — **prefer promoting it to
public** (rename to `resolve_signer_name`, update both call sites) since a method called from
outside its own class is by definition not actually private; do this rename instead of adding
a noqa comment.

- [ ] **Step 4: Rename `_resolve_signer_name` to `resolve_signer_name`**

In `app/services/submission.py`, rename the method (drop the leading underscore) and update
its one internal call site inside `_issue`. In `app/api/v1/public.py`, call
`SubmissionService(session).resolve_signer_name()` (no underscore, no noqa needed).

- [ ] **Step 5: Register router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import approval_config, auth, health, letter_template, master, public, submission

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
api_router.include_router(submission.router)
api_router.include_router(public.router)
```

- [ ] **Step 6: Run** — `pytest tests/test_public_verify_api.py -v` → PASS

- [ ] **Step 7: Commit**

```bash
git add app/api/v1/public.py app/api/v1/__init__.py app/services/submission.py tests/test_public_verify_api.py
git commit -m "feat(submissions): public no-auth letter verification endpoint"
```

---

### Task 15: Seed default approval steps + link demo warga to Resident

**Files:**
- Modify: `app/seed/seed.py`
- Test: `tests/test_seed_submission.py`

**Interfaces:**
- Produces:
  - `async seed_link_demo_resident(session)` — links the `warga` demo user's `resident_id` to
    the seeded "Siti Rohmah" Resident row (same person, currently unlinked — see rationale
    below). Idempotent (no-op if already linked or either side is missing).
  - `async seed_approval_steps(session)` — creates the default 3-step chain
    (staf → sekretaris → kades) for the seeded village, matching mockData's
    `SETTINGS.approvalMode='3'`. Idempotent (skips if the village already has any steps).
  - `seed_all` extended to call both, in order, after `seed_letter_templates`.

**Why the resident link matters:** `seed_rbac` creates the `warga` demo user without setting
`resident_id`; `seed_master` creates a "Siti Rohmah" Resident with a synthetic NIK distinct
from the demo user's NIK (`3516064588020003`). Without linking them,
`SubmissionService.resolve_applicant_data` falls back to sparse `User`-only data for the demo
account used in every manual/API test of this feature. Since both rows represent the same
person, linking them closes this gap for the exact account developers will actually use to
exercise the flow.

- [ ] **Step 1: Write failing test** `tests/test_seed_submission.py`

```python
import pytest
from sqlalchemy import select

from app.models.auth import User
from app.models.master import Resident, Village
from app.models.submission import ApprovalStepConfig
from app.seed.data import VILLAGE
from app.seed.seed import (
    seed_approval_steps, seed_link_demo_resident, seed_master, seed_rbac,
)


@pytest.mark.asyncio
async def test_seed_link_demo_resident_links_matching_person(db_session):
    await seed_rbac(db_session)
    await seed_master(db_session)
    await seed_link_demo_resident(db_session)

    user = await db_session.scalar(select(User).where(User.username == "warga"))
    assert user.resident_id is not None
    resident = await db_session.scalar(select(Resident).where(Resident.id == user.resident_id))
    assert resident.full_name == "Siti Rohmah"

    # idempotent
    await seed_link_demo_resident(db_session)
    user_again = await db_session.scalar(select(User).where(User.username == "warga"))
    assert user_again.resident_id == user.resident_id


@pytest.mark.asyncio
async def test_seed_approval_steps_default_three_step_chain(db_session):
    await seed_rbac(db_session)
    await seed_master(db_session)
    await seed_approval_steps(db_session)

    village = await db_session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    steps = list((await db_session.scalars(
        select(ApprovalStepConfig)
        .where(ApprovalStepConfig.village_id == village.id)
        .order_by(ApprovalStepConfig.order_index)
    )).all())
    assert len(steps) == 3

    from app.models.auth import Role
    role_names = []
    for step in steps:
        role = await db_session.scalar(select(Role).where(Role.id == step.role_id))
        role_names.append(role.name)
    assert role_names == ["staf", "sekretaris", "kades"]

    # idempotent
    await seed_approval_steps(db_session)
    steps_again = list((await db_session.scalars(
        select(ApprovalStepConfig).where(ApprovalStepConfig.village_id == village.id)
    )).all())
    assert len(steps_again) == 3
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Add to `app/seed/seed.py`**

Add imports:
```python
from app.models.submission import ApprovalStepConfig
```

Append these functions:
```python
async def seed_link_demo_resident(session: AsyncSession) -> None:
    """Link the demo 'warga' user to its matching Resident row.

    Both represent Siti Rohmah but currently exist as unlinked rows (see
    the plan's Task 15 rationale). Idempotent: no-op if already linked or
    if either side is missing.
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


async def seed_approval_steps(session: AsyncSession) -> None:
    """Seed the default 3-step approval chain (staf, sekretaris, kades)
    for the seeded village, matching mockData's SETTINGS.approvalMode='3'.

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
    for index, role_name in enumerate(("staf", "sekretaris", "kades")):
        session.add(ApprovalStepConfig(
            village_id=village.id, order_index=index, role_id=roles[role_name].id
        ))
    await session.commit()
    logger.info("seed_approval_steps: seeded 3-step chain for village_id=%s", village.id)
```

Add `from sqlalchemy import func, select` — check the existing top-of-file import; it likely
already has `from sqlalchemy import select` (extend it to `from sqlalchemy import func, select`
if `func` isn't already imported).

Update `seed_all`:
```python
async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: RBAC/demo-users, village hierarchy+residents,
    letter templates, demo-resident link, default approval steps."""
    await seed_rbac(session)
    await seed_master(session)
    await seed_letter_templates(session)
    await seed_link_demo_resident(session)
    await seed_approval_steps(session)
```

- [ ] **Step 4: Run** — `pytest tests/test_seed_submission.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/seed/seed.py tests/test_seed_submission.py
git commit -m "feat(submissions): seed default approval chain + link demo warga to Resident"
```

---

### Task 16: Full verification

**Files:**
- Modify: `README.md`

**Interfaces:** none (verification + docs gate).

- [ ] **Step 1: Run the whole test suite**

Run: `pytest -q`

Expected: all tests PASS (Foundation + B1 + all of B2's new tests).

- [ ] **Step 2: Lint**

Run: `ruff check app tests`

Expected: all checks passed.

- [ ] **Step 3: Live verification against `db_kopo`**

```bash
alembic upgrade head
python -m app.seed
```

Confirm the log output reports: `seed_link_demo_resident` linked (or already-linked on a
re-run), `seed_approval_steps` seeded 3 steps for the village (or skipped on a re-run).
Run `python -m app.seed` a second time to confirm both are idempotent.

Query `db_kopo` directly to confirm: the `warga` user's `resident_id` is non-null and points
at "Siti Rohmah"; `approval_step_configs` has exactly 3 rows for the seeded village in
`staf → sekretaris → kades` order.

- [ ] **Step 4: Manual end-to-end smoke via `/docs`**

```bash
uvicorn app.main:app --reload
```
In `/docs`: log in as `warga/warga123`, `POST /submissions` against one of the 11 seeded
templates with valid answers for its fields. Log in as `staf/staf123`, approve it. Log in as
`sekdes/sekdes123`, approve it. Log in as `kades/kades123`, approve it — confirm the response
shows `status: "issued"`, a `letter_number`, and a `verification_code`. Call
`GET /public/verify/{code}` **without** an Authorization header — confirm it works and returns
the letter's public details. Download the PDF via `GET /submissions/{id}/pdf` and open it —
confirm it shows the real submitted answers, a visual signature block, and a scannable QR
code that (if you have a phone handy) resolves to the configured
`public_verify_base_url`/code.

- [ ] **Step 5: Update `README.md`**

Add a "Pengajuan, Approval & Penerbitan Surat" section documenting: the new endpoints
(`/submissions/*`, `/approval-steps`, `/public/verify/{code}`), the approval-turn enforcement
model (data-driven via `ApprovalStepConfig.role_id`, not hardcoded), that reject is terminal,
that attachments/PDFs are stored on local disk under `storage/` (object-storage-ready
abstraction, not yet wired to R2), and that notification dispatch is a stub pending Phase 8.
Update the Roadmap note: Phase 4-7 (B1+B2) done; next is Sub-project C (Fase 8-11: Notifikasi,
Dashboard, Portal Desa, Pengaduan).

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: submission/approval/issuance run guide + Phase 5-7 verification"
```

---

## Self-Review

**1. Spec coverage:**
- Model data (ApprovalStepConfig, Submission, SubmissionStatusHistory, SubmissionAttachment,
  LetterNumberCounter) → Task 3. ✓
- Approval workflow engine (configurable steps, data-driven turn enforcement, auto-issuance on
  final approve, terminal reject) → Tasks 8, 12. ✓
- Upload lampiran (size/mime validation, UUID rename, local-disk-now/R2-ready abstraction) →
  Tasks 4, 11. ✓
- PDF issuance (real numbering allocation, verification code, QR, visual signature/stamp,
  reuse of B1's hardened render pipeline) → Tasks 5, 6, 9, 12. ✓
- Public verification (no auth, uniform 404) → Task 14. ✓
- Notification hook stub → Task 10 (`notify_status_change`). ✓
- Approval config admin API + pending-submission guard (409) → Task 8, addressing the gap
  caught in the design spec's own self-review. ✓
- Permission model incl. `submission:read_all` refinement over the spec's simpler table →
  Task 2, with rationale documented (needed because `submission:read` alone can't distinguish
  "own" vs "all" callers without a role-name check, which the plan avoids). ✓
- DoD race-condition-safe numbering → Task 9's concurrent-allocation test. ✓

**2. Placeholder scan:** No TBD/TODO in any step's code. An earlier draft of Task 13 had the
`approve` endpoint read `note` as a query parameter while its own test sent it as a JSON body —
caught in this self-review and fixed at the source (`SubmissionApproveRequest` added to Task 7's
schemas, `approve_submission` takes it as a body from its first appearance in Task 13 Step 3, no
later "fix it" step needed). Task 14's private-method-access note similarly converges on one
resolution (promote `_resolve_signer_name` to public `resolve_signer_name`) rather than leaving
both options open.

**3. Type consistency:** `SubmissionService` method signatures are used identically across
Tasks 10-14 (`create`, `get_or_404`, `list`, `add_attachment`, `approve`, `reject`,
`list_history`, `download_pdf`, `resolve_applicant_data`, `resolve_signer_name` — the last
renamed from `_resolve_signer_name` in Task 14 Step 4, with the one call site inside `_issue`
from Task 12 explicitly updated in that same step so no stale private-name reference survives).
`TemplateRenderService.render_issued`'s keyword-only signature (Task 6) matches exactly how
Task 12's `_issue` calls it. `LetterNumberService.allocate(template_id, year) -> int` is used
identically in Task 9's own test and Task 12's `_issue`. `ApprovalStepConfigService.list_steps`/
`replace_all` signatures match between Task 8 (definition) and Task 12 (`approve`/`reject`
consumption).
