# Letter Template Engine (Sub-project B1, Phase 4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the dynamic letter-template engine — template + field CRUD, PDF preview via xhtml2pdf, numbering-format definition, seeded with the 11 letter types from the frontend's `mockData.js` plus generic drafted letter bodies.

**Architecture:** Same Clean Architecture as Foundation: `router → service → repository → model`. `LetterTemplate`/`TemplateField` are new models composed via the existing generic `BaseRepository`; no ORM relationship between them (Phase 3's master-data models set that precedent — services compose via explicit queries instead). PDF rendering is a dedicated `TemplateRenderService` using sandboxed Jinja2 + xhtml2pdf, reused later by Sub-project B2 for real letter issuance.

**Tech Stack:** Adds `xhtml2pdf` (PDF rendering) and `jinja2` (sandboxed template interpolation) to the existing FastAPI/SQLAlchemy-async/Alembic/Postgres stack.

> **Deviation note (2026-07-24):** The design spec and CLAUDE.md's tech-stack list both name WeasyPrint for PDF generation. Task 1's smoke test failed on this Windows machine — WeasyPrint requires native GTK3/Pango/cairo runtime libraries (`OSError: cannot load library 'libgobject-2.0-0'`) that aren't installed and have no pip-installable Windows wheel. The user was asked and explicitly chose to switch to **xhtml2pdf** (pure Python, built on `reportlab`, no native dependency) rather than install the GTK3 runtime or defer PDF work. All PDF-related steps below reflect xhtml2pdf, not WeasyPrint. Task 1 has already been executed with this substitution (commit `18e987f` on `feat/letter-templates`) — its steps are left below for reference/audit trail, not for re-execution.

## Global Constraints

- Python 3.13+; async everywhere; **no synchronous DB access**.
- Router contains **no business logic**; services hold logic; repositories hold all DB access (seed scripts are the one established exception, per Foundation precedent).
- Every endpoint has a `response_model` using the existing `Envelope[T]` / `Page[T]` generics.
- **RBAC is data-driven** — guard with `require_permission("...")`; **never** `if role == "..."`.
- Every table: UUID v4 PK (`GUID()` type), `created_at`/`updated_at` (UTC tz-aware), `deleted_at` soft-delete — via the existing `UUIDMixin`/`TimestampMixin`/`SoftDeleteMixin`.
- `village_id` FK on tenant-scoped tables.
- Response envelope — Success: `{"success": true, "message": "...", "data": {...}}`; Error: `{"success": false, "message": "...", "error_code": "...", "data": null}`.
- Pagination response shape: `{"items": [...], "total": int, "page": int, "size": int}`.
- Type hints + docstrings + logger in every service module. Custom exceptions only; never leak a traceback.
- Base API path: `/api/v1`. All new routes live under the existing `master-data`-sibling router aggregation in `app/api/v1/__init__.py`.
- **`TemplateField.field_key` is immutable after creation** (not present in the Update schema) — it is referenced by future submission data (B2) and by `{{ field_key }}` placeholders inside `pdf_body_template`; allowing it to change later would silently break those references.
- **Field reordering has no DB-level uniqueness constraint on `order_index`** — enforced only by the service requiring the reorder endpoint's input to be the complete, exact set of a template's field ids. This avoids transient unique-constraint collisions when two fields swap positions within one transaction.
- Commit frequently, one logical change per task.

---

## File Structure

```
sipades-kopo-api/
  pyproject.toml                          # + xhtml2pdf, jinja2
  app/
    models/
      letter_template.py                  # LetterTemplate, TemplateField, FieldType enum
    schemas/
      common.py                           # + build_page() shared helper (extracted from master.py)
      letter_template.py                  # Create/Update/Read schemas + ReorderFieldsRequest
    repositories/                         # (no new file — reuses BaseRepository)
    services/
      letter_template.py                  # LetterTemplateService: template + field CRUD, reorder
      template_render.py                  # TemplateRenderService: sandboxed Jinja2 + xhtml2pdf
    permissions/
      registry.py                         # + template:manage, template:read
    api/v1/
      letter_template.py                  # router: template CRUD, field CRUD/reorder, preview
      __init__.py                         # + include letter_template.router
      master.py                           # refactored to use shared build_page()
    seed/
      letter_template_data.py             # SURAT_TEMPLATES: 11 templates + fields + PDF bodies
      seed.py                             # + seed_letter_templates(), seed_all() extended
  tests/
    test_pdf_smoke.py
    test_permissions_registry.py          # extended
    test_letter_template_models.py
    test_letter_template_service.py
    test_template_render.py
    test_letter_template_api.py
    test_seed_letter_templates.py
```

---

### Task 1: PDF + Jinja2 dependencies — isolated smoke test — ✅ ALREADY EXECUTED

This ran FIRST and alone because PDF rendering has a real risk of native-library issues on
Windows. It surfaced exactly that: **WeasyPrint failed** (`OSError: cannot load library
'libgobject-2.0-0'` — missing native GTK3/Pango/cairo runtime). The user was asked and chose
to switch to **xhtml2pdf** (pure Python, built on `reportlab`). This has already been done —
commit `18e987f` on `feat/letter-templates` — with `pyproject.toml` adding
`xhtml2pdf>=0.2.16` + `jinja2>=3.1`, and `tests/test_pdf_smoke.py` passing:

```python
"""Smoke test: xhtml2pdf can render HTML to a valid PDF on this machine."""
import io

from xhtml2pdf import pisa


def test_xhtml2pdf_renders_minimal_pdf():
    buffer = io.BytesIO()
    result = pisa.CreatePDF("<html><body><h1>Halo</h1></body></html>", dest=buffer)
    assert result.err == 0
    assert buffer.getvalue()[:5] == b"%PDF-"
```

**No action needed for this task.** It is recorded here only so a fresh implementer reading
this plan understands the dependency is xhtml2pdf, not WeasyPrint, and doesn't re-attempt the
original (blocked) approach. Proceed directly to Task 2.

---

### Task 2: Extend permission registry

**Files:**
- Modify: `app/permissions/registry.py`
- Test: `tests/test_permissions_registry.py`

**Interfaces:**
- Produces: `"template:manage"`, `"template:read"` added to `PERMISSIONS`; `"template:read"` added to `staf`, `sekretaris`, `kades` in `ROLE_PERMISSIONS` (`administrator` already covers `template:manage` via `"*"`; `warga` gets neither — templates are an admin/staff concern, not citizen-facing in this API).

- [ ] **Step 1: Write failing test** — append to `tests/test_permissions_registry.py`

```python
def test_template_permissions_registered():
    assert "template:manage" in PERMISSIONS
    assert "template:read" in PERMISSIONS
    for role in ("staf", "sekretaris", "kades"):
        assert "template:read" in ROLE_PERMISSIONS[role]
```

(Add `PERMISSIONS` to the existing top-of-file import from `app.permissions.registry` if not already imported.)

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_permissions_registry.py -v` → FAIL

- [ ] **Step 3: Update `app/permissions/registry.py`**

Change the `PERMISSIONS` list to add two entries:
```python
PERMISSIONS: list[str] = [
    "auth:me",
    "resident:create", "resident:read", "resident:update", "resident:delete",
    "resident:import", "resident:export",
    "village:manage", "dusun:manage", "rw:manage", "rt:manage", "family_card:manage",
    "template:manage", "template:read",
]
```

Change `ROLE_PERMISSIONS` entries for `staf`, `sekretaris`, `kades` to append `"template:read"`:
```python
ROLE_PERMISSIONS: dict[str, list[str]] = {
    "warga": ["auth:me"],
    "staf": ["auth:me", "resident:read", "resident:create", "resident:update",
             "resident:import", "resident:export", "template:read"],
    "sekretaris": ["auth:me", "resident:read", "resident:update",
                   "village:manage", "dusun:manage", "rw:manage", "rt:manage",
                   "family_card:manage", "template:read"],
    "kades": ["auth:me", "resident:read", "template:read"],
    "administrator": ["*"],
}
```

- [ ] **Step 4: Run tests** — `pytest tests/test_permissions_registry.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/permissions/registry.py tests/test_permissions_registry.py
git commit -m "feat(templates): register template:manage/template:read permissions"
```

---

### Task 3: LetterTemplate + TemplateField models + migration

**Files:**
- Create: `app/models/letter_template.py`
- Modify: `app/models/__init__.py`
- Test: `tests/test_letter_template_models.py`

**Interfaces:**
- Produces:
  - `FieldType(str, enum.Enum)`: `TEXT = "text"`, `NUMBER = "number"`, `SELECT = "select"`, `DATE = "date"`, `TEXTAREA = "textarea"`.
  - `LetterTemplate(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base)`, table `letter_templates`: `village_id, code, name, description, icon, color_bg, color_fg, is_active, required_documents (JSON list[str]), numbering_prefix, numbering_pattern, pdf_body_template`. Unique constraint `(village_id, code)`.
  - `TemplateField(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base)`, table `template_fields`: `template_id (FK), order_index, field_key, label, field_type, options (JSON list[str]|None), placeholder, is_required, validation_rules (JSON dict|None)`. Unique constraint `(template_id, field_key)`.

- [ ] **Step 1: Write failing test** `tests/test_letter_template_models.py`

```python
from app.models.letter_template import FieldType, LetterTemplate, TemplateField


def test_letter_template_tables():
    assert LetterTemplate.__tablename__ == "letter_templates"
    assert TemplateField.__tablename__ == "template_fields"
    assert FieldType.SELECT == "select"
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/models/letter_template.py`**

```python
"""Letter template models: dynamic template + field definitions."""
import enum
import uuid

from sqlalchemy import JSON, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class FieldType(str, enum.Enum):
    """Supported dynamic form field types for a letter template."""

    TEXT = "text"
    NUMBER = "number"
    SELECT = "select"
    DATE = "date"
    TEXTAREA = "textarea"


class LetterTemplate(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A letter type's metadata, dynamic-form definition, and PDF body template."""

    __tablename__ = "letter_templates"
    __table_args__ = (
        UniqueConstraint("village_id", "code", name="uq_letter_templates_village_code"),
    )

    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    icon: Mapped[str] = mapped_column(String(50))
    color_bg: Mapped[str] = mapped_column(String(20))
    color_fg: Mapped[str] = mapped_column(String(20))
    is_active: Mapped[bool] = mapped_column(default=True)
    required_documents: Mapped[list[str]] = mapped_column(JSON, default=list)
    numbering_prefix: Mapped[str] = mapped_column(String(20))
    numbering_pattern: Mapped[str] = mapped_column(String(100))
    pdf_body_template: Mapped[str] = mapped_column(Text)


class TemplateField(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A single dynamic form field belonging to a letter template."""

    __tablename__ = "template_fields"
    __table_args__ = (
        UniqueConstraint("template_id", "field_key", name="uq_template_fields_template_key"),
    )

    template_id: Mapped[uuid.UUID] = mapped_column(
        GUID(), ForeignKey("letter_templates.id"), index=True
    )
    order_index: Mapped[int] = mapped_column(default=0)
    field_key: Mapped[str] = mapped_column(String(50))
    label: Mapped[str] = mapped_column(String(150))
    field_type: Mapped[FieldType] = mapped_column(SAEnum(FieldType, native_enum=False, length=20))
    options: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    placeholder: Mapped[str | None] = mapped_column(String(150), nullable=True)
    is_required: Mapped[bool] = mapped_column(default=True)
    validation_rules: Mapped[dict | None] = mapped_column(JSON, nullable=True)
```

- [ ] **Step 4: Wire into `app/models/__init__.py`**

Add `letter_template` to the import line so Alembic autogenerate and `Base.metadata` see it:
```python
from app.models import auth, letter_template, master  # noqa: F401
```

- [ ] **Step 5: Run** — `pytest tests/test_letter_template_models.py -v` → PASS

- [ ] **Step 6: Generate + apply migration against live `db_kopo`**

```bash
alembic revision --autogenerate -m "letter template tables"
alembic upgrade head
```

Verify the migration is importable and applied: confirm via a quick SQLAlchemy query (or `alembic current`) that `letter_templates` and `template_fields` exist in `db_kopo`. If the autogenerated file references `GUID` and needs an explicit import, add `import app.db.base` and use `app.db.base.GUID()` (mirror the pattern already used in `alembic/versions/*master_data_tables.py`); remove any unused bare `from app.db.base import GUID` import so `ruff` stays clean (this exact mistake happened once in Foundation's auth migration and was cleaned up — don't repeat it).

- [ ] **Step 7: Commit**

```bash
git add app/models/letter_template.py app/models/__init__.py alembic/versions tests/test_letter_template_models.py
git commit -m "feat(templates): letter template + field models and migration"
```

---

### Task 4: Letter template schemas

**Files:**
- Create: `app/schemas/letter_template.py`

**Interfaces:**
- Produces: `TemplateFieldCreate`, `TemplateFieldUpdate` (no `field_key` — immutable), `TemplateFieldRead`, `LetterTemplateCreate`, `LetterTemplateUpdate`, `LetterTemplateRead`, `ReorderFieldsRequest` (`field_ids: list[UUID]`).

- [ ] **Step 1: Implement `app/schemas/letter_template.py`**

```python
"""Letter template schemas: template + field Create/Update/Read, reorder request."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.letter_template import FieldType


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class TemplateFieldCreate(BaseModel):
    field_key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool = True
    validation_rules: dict | None = None


class TemplateFieldUpdate(BaseModel):
    """Note: field_key is intentionally absent — immutable after creation."""

    label: str | None = None
    field_type: FieldType | None = None
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool | None = None
    validation_rules: dict | None = None


class TemplateFieldRead(_Read):
    template_id: UUID
    order_index: int
    field_key: str
    label: str
    field_type: FieldType
    options: list[str] | None = None
    placeholder: str | None = None
    is_required: bool
    validation_rules: dict | None = None


class LetterTemplateCreate(BaseModel):
    village_id: UUID
    code: str
    name: str
    description: str | None = None
    icon: str
    color_bg: str
    color_fg: str
    is_active: bool = True
    required_documents: list[str] = Field(default_factory=list)
    numbering_prefix: str
    numbering_pattern: str
    pdf_body_template: str


class LetterTemplateUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    icon: str | None = None
    color_bg: str | None = None
    color_fg: str | None = None
    is_active: bool | None = None
    required_documents: list[str] | None = None
    numbering_prefix: str | None = None
    numbering_pattern: str | None = None
    pdf_body_template: str | None = None


class LetterTemplateRead(_Read):
    village_id: UUID
    code: str
    name: str
    description: str | None = None
    icon: str
    color_bg: str
    color_fg: str
    is_active: bool
    required_documents: list[str]
    numbering_prefix: str
    numbering_pattern: str
    pdf_body_template: str


class ReorderFieldsRequest(BaseModel):
    field_ids: list[UUID]
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from app.schemas.letter_template import LetterTemplateRead, TemplateFieldRead, ReorderFieldsRequest"`

Expected: no error.

- [ ] **Step 3: Commit**

```bash
git add app/schemas/letter_template.py
git commit -m "feat(templates): letter template + field schemas"
```

---

### Task 5: `LetterTemplateService` — template CRUD

**Files:**
- Create: `app/services/letter_template.py`
- Test: `tests/test_letter_template_service.py`

**Interfaces:**
- Consumes: `BaseRepository`, `NotFoundError`, `get_logger`.
- Produces `LetterTemplateService(session)`:
  - `async create(data: dict) -> LetterTemplate`
  - `async get_or_404(id_: UUID) -> LetterTemplate`
  - `async list(page=1, size=20, is_active: bool|None=None, search: str|None=None) -> tuple[list[LetterTemplate], int]`
  - `async update(id_: UUID, data: dict) -> LetterTemplate`
  - `async delete(id_: UUID) -> None`

(Field-related methods are added in Task 6 on the same class.)

- [ ] **Step 1: Write failing test** `tests/test_letter_template_service.py`

```python
import pytest
from app.core.exceptions import NotFoundError
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService


@pytest.mark.asyncio
async def test_template_crud(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    svc = LetterTemplateService(db_session)
    obj = await svc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    assert obj.code == "domisili"

    got = await svc.get_or_404(obj.id)
    assert got.name == "Surat Domisili"

    await svc.update(obj.id, {"name": "Surat Domisili (Updated)"})
    items, total = await svc.list(search="Domisili")
    assert total == 1
    assert items[0].name == "Surat Domisili (Updated)"

    await svc.delete(obj.id)
    with pytest.raises(NotFoundError):
        await svc.get_or_404(obj.id)
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/letter_template.py`** (template-CRUD portion; field methods added in Task 6)

```python
"""Letter template service: template CRUD, field CRUD, and reordering."""
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.letter_template import LetterTemplate, TemplateField
from app.repositories.base import BaseRepository

logger = get_logger("letter_template")


class LetterTemplateService:
    """CRUD orchestration for LetterTemplate and its TemplateField rows."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, LetterTemplate)
        self.field_repo = BaseRepository(session, TemplateField)

    async def create(self, data: dict[str, Any]) -> LetterTemplate:
        """Create a new letter template (no fields yet)."""
        obj = await self.repo.create(**data)
        await self.session.commit()
        logger.info("LetterTemplate created id=%s code=%s", obj.id, obj.code)
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> LetterTemplate:
        """Return the template with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("Template surat tidak ditemukan")
        return obj

    async def list(
        self, page: int = 1, size: int = 20,
        is_active: bool | None = None, search: str | None = None,
    ) -> tuple[list[LetterTemplate], int]:
        """Return a page of templates, optionally filtered by active flag and name search."""
        search_tuple = ([LetterTemplate.name], search) if search else None
        return await self.repo.list(
            page=page, size=size, filters={"is_active": is_active}, search=search_tuple
        )

    async def update(self, id_: uuid.UUID, data: dict[str, Any]) -> LetterTemplate:
        """Update a template's metadata."""
        obj = await self.get_or_404(id_)
        obj = await self.repo.update(obj, **data)
        await self.session.commit()
        logger.info("LetterTemplate updated id=%s", id_)
        return obj

    async def delete(self, id_: uuid.UUID) -> None:
        """Soft-delete a template."""
        obj = await self.get_or_404(id_)
        await self.repo.soft_delete(obj)
        await self.session.commit()
        logger.info("LetterTemplate deleted id=%s", id_)
```

- [ ] **Step 4: Run** — `pytest tests/test_letter_template_service.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/letter_template.py tests/test_letter_template_service.py
git commit -m "feat(templates): LetterTemplateService template CRUD"
```

---

### Task 6: `LetterTemplateService` — field CRUD + reorder

**Files:**
- Modify: `app/services/letter_template.py`
- Modify: `tests/test_letter_template_service.py`

**Interfaces:**
- Consumes: `Task 5`'s `LetterTemplateService`.
- Produces (added to the same class):
  - `async list_fields(template_id: UUID) -> list[TemplateField]`
  - `async add_field(template_id: UUID, data: dict) -> TemplateField`
  - `async get_field_or_404(template_id: UUID, field_id: UUID) -> TemplateField`
  - `async update_field(template_id: UUID, field_id: UUID, data: dict) -> TemplateField`
  - `async delete_field(template_id: UUID, field_id: UUID) -> None`
  - `async reorder_fields(template_id: UUID, field_ids: list[UUID]) -> list[TemplateField]` — raises `ValidationAppError` if `field_ids` isn't exactly the template's current field-id set.

- [ ] **Step 1: Write failing test** — append to `tests/test_letter_template_service.py`

```python
from app.core.exceptions import ValidationAppError


@pytest.mark.asyncio
async def test_field_crud_and_reorder(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    svc = LetterTemplateService(db_session)
    template = await svc.create({
        "village_id": village.id, "code": "sktm", "name": "SKTM",
        "icon": "volunteer_activism", "color_bg": "#F3EAFB", "color_fg": "#7B4BC0",
        "numbering_prefix": "460", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ keperluan }}</p>",
    })

    f1 = await svc.add_field(template.id, {
        "field_key": "keperluan", "label": "Keperluan", "field_type": "select",
        "options": ["Beasiswa", "Kesehatan"], "is_required": True,
    })
    f2 = await svc.add_field(template.id, {
        "field_key": "penghasilan", "label": "Penghasilan", "field_type": "text",
        "is_required": True,
    })
    assert f1.order_index == 0
    assert f2.order_index == 1

    fields = await svc.list_fields(template.id)
    assert [f.id for f in fields] == [f1.id, f2.id]

    await svc.update_field(template.id, f2.id, {"label": "Penghasilan / Bulan"})
    updated = await svc.get_field_or_404(template.id, f2.id)
    assert updated.label == "Penghasilan / Bulan"

    reordered = await svc.reorder_fields(template.id, [f2.id, f1.id])
    assert [f.id for f in reordered] == [f2.id, f1.id]
    assert reordered[0].order_index == 0
    assert reordered[1].order_index == 1

    with pytest.raises(ValidationAppError):
        await svc.reorder_fields(template.id, [f1.id])  # missing f2.id

    await svc.delete_field(template.id, f1.id)
    remaining = await svc.list_fields(template.id)
    assert [f.id for f in remaining] == [f2.id]
```

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Add field methods to `app/services/letter_template.py`**

Add these imports at the top:
```python
from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationAppError
```
(Replace the existing `from app.core.exceptions import NotFoundError` line with the combined import above.)

Append these methods to the `LetterTemplateService` class:
```python
    async def list_fields(self, template_id: uuid.UUID) -> list[TemplateField]:
        """Return all non-deleted fields of a template, ordered by order_index."""
        await self.get_or_404(template_id)
        stmt = (
            select(TemplateField)
            .where(TemplateField.template_id == template_id, TemplateField.deleted_at.is_(None))
            .order_by(TemplateField.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    async def add_field(self, template_id: uuid.UUID, data: dict[str, Any]) -> TemplateField:
        """Add a new field to a template, appended at the end of the order."""
        await self.get_or_404(template_id)
        existing = await self.list_fields(template_id)
        next_order = max((f.order_index for f in existing), default=-1) + 1
        obj = await self.field_repo.create(template_id=template_id, order_index=next_order, **data)
        await self.session.commit()
        logger.info("TemplateField created id=%s template_id=%s", obj.id, template_id)
        return obj

    async def get_field_or_404(self, template_id: uuid.UUID, field_id: uuid.UUID) -> TemplateField:
        """Return a field scoped to its template, or raise NotFoundError."""
        obj = await self.field_repo.get(field_id)
        if obj is None or obj.template_id != template_id:
            raise NotFoundError("Field template tidak ditemukan")
        return obj

    async def update_field(
        self, template_id: uuid.UUID, field_id: uuid.UUID, data: dict[str, Any]
    ) -> TemplateField:
        """Update a single field's metadata."""
        obj = await self.get_field_or_404(template_id, field_id)
        obj = await self.field_repo.update(obj, **data)
        await self.session.commit()
        logger.info("TemplateField updated id=%s", field_id)
        return obj

    async def delete_field(self, template_id: uuid.UUID, field_id: uuid.UUID) -> None:
        """Soft-delete a single field."""
        obj = await self.get_field_or_404(template_id, field_id)
        await self.field_repo.soft_delete(obj)
        await self.session.commit()
        logger.info("TemplateField deleted id=%s", field_id)

    async def reorder_fields(
        self, template_id: uuid.UUID, field_ids: list[uuid.UUID]
    ) -> list[TemplateField]:
        """Rewrite order_index for all of a template's fields from a full ordered id list.

        ``field_ids`` must exactly match the set of the template's current
        non-deleted field ids (no missing, no extra, no duplicates) — this
        keeps ordering consistent without a DB-level unique constraint on
        order_index, which would risk transient collisions when two fields
        swap positions within the same transaction.
        """
        await self.get_or_404(template_id)
        existing = await self.list_fields(template_id)
        existing_ids = {f.id for f in existing}
        given_ids = set(field_ids)
        if given_ids != existing_ids or len(field_ids) != len(existing_ids):
            raise ValidationAppError(
                "Daftar field harus memuat seluruh field template ini tanpa duplikat"
            )
        by_id = {f.id: f for f in existing}
        for index, fid in enumerate(field_ids):
            by_id[fid].order_index = index
        await self.session.commit()
        logger.info("TemplateField reordered template_id=%s", template_id)
        return await self.list_fields(template_id)
```

- [ ] **Step 4: Run** — `pytest tests/test_letter_template_service.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/letter_template.py tests/test_letter_template_service.py
git commit -m "feat(templates): field CRUD + reorder on LetterTemplateService"
```

---

### Task 7: `TemplateRenderService` — PDF rendering

**Files:**
- Create: `app/services/template_render.py`
- Test: `tests/test_template_render.py`

**Interfaces:**
- Consumes: `LetterTemplate`, `TemplateField`, `FieldType` (Task 3), `app.models.master.Village`.
- Produces `TemplateRenderService()`:
  - `render_preview(template: LetterTemplate, fields: list[TemplateField], village: Village) -> bytes` — returns PDF bytes.

- [ ] **Step 1: Write failing test** `tests/test_template_render.py`

```python
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village
from app.services.template_render import TemplateRenderService
import uuid


def _village():
    return Village(
        id=uuid.uuid4(), name="Desa Kopo", kecamatan="Cisarua", kabupaten="Bogor", provinsi="Jawa Barat"
    )


def _template():
    return LetterTemplate(
        id=uuid.uuid4(), village_id=uuid.uuid4(), code="domisili", name="Surat Domisili",
        icon="home_pin", color_bg="#EAF6FF", color_fg="#2B76C9", is_active=True,
        required_documents=["KTP", "KK"], numbering_prefix="470",
        numbering_pattern="{prefix}/{seq}/Ds.Kopo/{year}",
        pdf_body_template=(
            "<p>Nama: {{ nama }}, NIK: {{ nik }}</p>"
            "<p>Tinggal di {{ alamat_tinggal_saat_ini }} selama {{ lama_tinggal }}.</p>"
        ),
    )


def _fields(template_id):
    return [
        TemplateField(
            id=uuid.uuid4(), template_id=template_id, order_index=0,
            field_key="alamat_tinggal_saat_ini", label="Alamat Tinggal Saat Ini",
            field_type=FieldType.TEXT, is_required=True,
        ),
        TemplateField(
            id=uuid.uuid4(), template_id=template_id, order_index=1,
            field_key="lama_tinggal", label="Lama Tinggal", field_type=FieldType.TEXT,
            is_required=True,
        ),
    ]


def test_render_preview_returns_valid_pdf():
    template = _template()
    pdf_bytes = TemplateRenderService().render_preview(template, _fields(template.id), _village())
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_preview_number_uses_pattern():
    svc = TemplateRenderService()
    template = _template()
    assert svc._preview_number(template) is not None
    number = svc._preview_number(template)
    assert number.startswith("470/1/Ds.Kopo/")


def test_render_preview_select_field_uses_first_option():
    template = _template()
    template.pdf_body_template = "<p>{{ keperluan }}</p>"
    field = TemplateField(
        id=uuid.uuid4(), template_id=template.id, order_index=0, field_key="keperluan",
        label="Keperluan", field_type=FieldType.SELECT, options=["Beasiswa", "Kesehatan"],
        is_required=True,
    )
    svc = TemplateRenderService()
    assert svc._sample_data([field])["keperluan"] == "Beasiswa"
```

Note: `_sample_data` is introduced as a small internal helper in Step 3 below (kept as an instance method, not a module function, so the test above can call `svc._sample_data(...)` directly without duplicating the applicant-defaults dict).

- [ ] **Step 2: Run** — FAIL

- [ ] **Step 3: Implement `app/services/template_render.py`**

Uses **xhtml2pdf** (not WeasyPrint — see the deviation note at the top of this plan). Its
`pisa.CreatePDF(html, dest=buffer)` writes into a binary buffer and returns a status object
with `.err` (0 = success) instead of returning bytes directly, so the render call is wrapped
accordingly and a render failure is surfaced as an `AppException`, never a raw exception.

```python
"""Render letter templates to PDF using sandboxed Jinja2 + xhtml2pdf."""
import io
from datetime import date

from jinja2.sandbox import SandboxedEnvironment
from xhtml2pdf import pisa

from app.core.exceptions import AppException
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village

_LETTERHEAD = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page { size: A4; margin: 2.5cm 2cm; }
  body { font-family: Helvetica, sans-serif; font-size: 12pt; color: #182420; }
  .kop { text-align: center; border-bottom: 3px solid #182420; padding-bottom: 10px; margin-bottom: 20px; }
  .kop .instansi { font-size: 11pt; font-weight: bold; letter-spacing: 1px; }
  .kop .desa { font-size: 13pt; font-weight: bold; }
  .judul { text-align: center; margin: 20px 0; }
  .judul .title { font-size: 13pt; font-weight: bold; text-decoration: underline; }
  .judul .nomor { font-size: 11pt; margin-top: 4px; }
  .body { text-align: justify; line-height: 1.6; margin-bottom: 40px; }
  .ttd { text-align: right; margin-top: 40px; }
  .ttd .tempat-tanggal { margin-bottom: 60px; }
  .ttd .nama { font-weight: bold; text-decoration: underline; }
</style>
</head>
<body>
  <div class="kop">
    <div class="instansi">PEMERINTAH KABUPATEN {{ kabupaten }}<br/>KECAMATAN {{ kecamatan }}</div>
    <div class="desa">DESA {{ village_name }}</div>
  </div>
  <div class="judul">
    <div class="title">{{ letter_title }}</div>
    <div class="nomor">Nomor: {{ nomor }}</div>
  </div>
  <div class="body">{{ body|safe }}</div>
  <div class="ttd">
    <div class="tempat-tanggal">{{ village_name }}, {{ tanggal }}</div>
    <div>Kepala Desa {{ village_name }}</div>
    <div class="nama">{{ signer_name }}</div>
  </div>
</body>
</html>
"""

_SAMPLE_APPLICANT = {
    "nama": "Nama Pemohon (Contoh)",
    "nik": "3516000000000000",
    "alamat": "Dusun Contoh, RT 000/RW 000",
    "no_kk": "3516000000000000",
}


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

    def render_preview(
        self, template: LetterTemplate, fields: list[TemplateField], village: Village
    ) -> bytes:
        """Render a PDF preview of a template using auto-generated sample data."""
        data = self._sample_data(fields)
        body_tpl = self._env.from_string(template.pdf_body_template)
        body_html = body_tpl.render(**data)

        letterhead_tpl = self._env.from_string(_LETTERHEAD)
        full_html = letterhead_tpl.render(
            kabupaten=village.kabupaten or "-",
            kecamatan=village.kecamatan or "-",
            village_name=village.name,
            letter_title=template.name.upper(),
            nomor=self._preview_number(template),
            body=body_html,
            tanggal=date.today().strftime("%d %B %Y"),
            signer_name="(Contoh Tanda Tangan)",
        )
        buffer = io.BytesIO()
        result = pisa.CreatePDF(full_html, dest=buffer)
        if result.err:
            raise AppException("Gagal merender PDF template", "PDF_RENDER_ERROR", 500)
        return buffer.getvalue()
```

- [ ] **Step 4: Run** — `pytest tests/test_template_render.py -v` → PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/template_render.py tests/test_template_render.py
git commit -m "feat(templates): TemplateRenderService (sandboxed Jinja2 + xhtml2pdf)"
```

---

### Task 8: API router + shared pagination helper

**Files:**
- Create: `app/api/v1/letter_template.py`
- Modify: `app/schemas/common.py` (add `build_page`)
- Modify: `app/api/v1/master.py` (use the shared helper instead of its private one)
- Modify: `app/api/v1/__init__.py`
- Test: `tests/test_letter_template_api.py`

**Interfaces:**
- Consumes: `LetterTemplateService`, `TemplateRenderService`, `VillageService`, `require_permission`, `pagination_params`.
- Produces: `build_page(items, total, page, size, schema) -> dict` in `app/schemas/common.py`; router with all template/field/preview endpoints registered under `/api/v1`.

- [ ] **Step 1: Extract shared `build_page` into `app/schemas/common.py`**

Replace the file's contents with:
```python
"""Shared schemas: pagination page and query params."""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


def build_page(
    items: list[Any], total: int, page: int, size: int, schema: type[BaseModel]
) -> dict:
    """Build a Page-shaped dict from ORM rows for the response envelope."""
    return {
        "items": [schema.model_validate(i).model_dump(mode="json") for i in items],
        "total": total, "page": page, "size": size,
    }
```

- [ ] **Step 2: Refactor `app/api/v1/master.py` to use the shared helper**

Remove the local `_page` function definition:
```python
def _page(items: list, total: int, p: PaginationParams, schema: type) -> dict:
    """Build a Page-shaped dict from ORM rows for the response envelope."""
    return {
        "items": [schema.model_validate(i).model_dump(mode="json") for i in items],
        "total": total,
        "page": p.page,
        "size": p.size,
    }
```
Add `build_page` to the existing `from app.schemas.common import Page` import line:
```python
from app.schemas.common import Page, build_page
```
Replace every call site `_page(items, total, p, XxxRead)` with `build_page(items, total, p.page, p.size, XxxRead)` (there are 6: villages, dusun, rw, rt, family-cards, residents list endpoints).

- [ ] **Step 3: Run master-data tests to confirm the refactor is safe**

Run: `pytest tests/test_master_data.py -v`

Expected: all still PASS (pure rename/signature-inline refactor, no behavior change).

- [ ] **Step 4: Write failing API test** `tests/test_letter_template_api.py`

```python
import pytest


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


async def _village(client, token):
    r = await client.post("/api/v1/villages", json={"name": "Desa Kopo"},
                          headers={"Authorization": f"Bearer {token}"})
    return r.json()["data"]["id"]


@pytest.mark.asyncio
async def test_template_and_field_crud_flow(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village_id = await _village(client, tok)

    created = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    assert created.status_code == 200
    template_id = created.json()["data"]["id"]

    listed = await client.get("/api/v1/templates", headers=h)
    assert listed.json()["data"]["total"] >= 1

    field = await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "lama_tinggal", "label": "Lama Tinggal", "field_type": "text",
    }, headers=h)
    assert field.status_code == 200
    field_id = field.json()["data"]["id"]
    assert field.json()["data"]["order_index"] == 0

    fields = await client.get(f"/api/v1/templates/{template_id}/fields", headers=h)
    assert len(fields.json()["data"]) == 1

    field2 = await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "tujuan", "label": "Tujuan", "field_type": "text",
    }, headers=h)
    field2_id = field2.json()["data"]["id"]

    reordered = await client.put(
        f"/api/v1/templates/{template_id}/fields/reorder",
        json={"field_ids": [field2_id, field_id]}, headers=h,
    )
    assert reordered.status_code == 200
    assert reordered.json()["data"][0]["id"] == field2_id


@pytest.mark.asyncio
async def test_template_manage_requires_permission(client):
    # kades has only template:read — creating must 403.
    admin_tok = await _token(client)
    village_id = await _village(client, admin_tok)
    kades_tok = await _token(client, "kades", "kades123")
    resp = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "x", "name": "X", "icon": "i",
        "color_bg": "#fff", "color_fg": "#000", "numbering_prefix": "1",
        "numbering_pattern": "{prefix}/{seq}/{year}", "pdf_body_template": "<p></p>",
    }, headers={"Authorization": f"Bearer {kades_tok}"})
    assert resp.status_code == 403

    # But kades CAN read.
    listed = await client.get("/api/v1/templates", headers={"Authorization": f"Bearer {kades_tok}"})
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_template_preview_returns_pdf(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village_id = await _village(client, tok)
    created = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>Nama: {{ nama }}, Lama: {{ lama_tinggal }}</p>",
    }, headers=h)
    template_id = created.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "lama_tinggal", "label": "Lama Tinggal", "field_type": "text",
    }, headers=h)

    preview = await client.get(f"/api/v1/templates/{template_id}/preview", headers=h)
    assert preview.status_code == 200
    assert preview.content[:5] == b"%PDF-"
    assert preview.headers["content-type"] == "application/pdf"
```

- [ ] **Step 5: Run** — FAIL (no router yet)

- [ ] **Step 6: Implement `app/api/v1/letter_template.py`**

```python
"""Letter template CRUD endpoints: template + field management, PDF preview."""
import io
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.letter_template import (
    LetterTemplateCreate,
    LetterTemplateRead,
    LetterTemplateUpdate,
    ReorderFieldsRequest,
    TemplateFieldCreate,
    TemplateFieldRead,
    TemplateFieldUpdate,
)
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService
from app.services.template_render import TemplateRenderService

router = APIRouter(tags=["letter-templates"])


@router.post("/templates", response_model=Envelope[LetterTemplateRead])
async def create_template(
    body: LetterTemplateCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Create a new letter template."""
    obj = await LetterTemplateService(session).create(body.model_dump(exclude_unset=True))
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/templates", response_model=Envelope[Page[LetterTemplateRead]])
async def list_templates(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    is_active: bool | None = Query(None),
    search: str | None = Query(None),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List letter templates, paginated, with optional active filter and name search."""
    items, total = await LetterTemplateService(session).list(
        p.page, p.size, is_active=is_active, search=search
    )
    return success_response(build_page(items, total, p.page, p.size, LetterTemplateRead))


@router.get("/templates/{template_id}", response_model=Envelope[LetterTemplateRead])
async def get_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """Get a single letter template by id."""
    obj = await LetterTemplateService(session).get_or_404(template_id)
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"))


@router.put("/templates/{template_id}", response_model=Envelope[LetterTemplateRead])
async def update_template(
    template_id: UUID,
    body: LetterTemplateUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Update a letter template's metadata."""
    obj = await LetterTemplateService(session).update(template_id, body.model_dump(exclude_unset=True))
    return success_response(LetterTemplateRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/templates/{template_id}", response_model=Envelope[None])
async def delete_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Soft-delete a letter template."""
    await LetterTemplateService(session).delete(template_id)
    return success_response(None, "Dihapus")


@router.get("/templates/{template_id}/fields", response_model=Envelope[list[TemplateFieldRead]])
async def list_template_fields(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List a template's fields, ordered."""
    fields = await LetterTemplateService(session).list_fields(template_id)
    return success_response(
        [TemplateFieldRead.model_validate(f).model_dump(mode="json") for f in fields]
    )


@router.post("/templates/{template_id}/fields", response_model=Envelope[TemplateFieldRead])
async def add_template_field(
    template_id: UUID,
    body: TemplateFieldCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Add a new field to a template, appended at the end of the order."""
    obj = await LetterTemplateService(session).add_field(
        template_id, body.model_dump(exclude_unset=True)
    )
    return success_response(TemplateFieldRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


# Static "reorder" route MUST precede the parameterized "{field_id}" route below,
# mirroring the /residents/import-before-/residents/{item_id} pattern in master.py.
@router.put(
    "/templates/{template_id}/fields/reorder",
    response_model=Envelope[list[TemplateFieldRead]],
)
async def reorder_template_fields(
    template_id: UUID,
    body: ReorderFieldsRequest,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Rewrite field order from a full ordered list of field ids."""
    fields = await LetterTemplateService(session).reorder_fields(template_id, body.field_ids)
    return success_response(
        [TemplateFieldRead.model_validate(f).model_dump(mode="json") for f in fields],
        "Urutan diperbarui",
    )


@router.put("/templates/{template_id}/fields/{field_id}", response_model=Envelope[TemplateFieldRead])
async def update_template_field(
    template_id: UUID,
    field_id: UUID,
    body: TemplateFieldUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Update a single template field."""
    obj = await LetterTemplateService(session).update_field(
        template_id, field_id, body.model_dump(exclude_unset=True)
    )
    return success_response(TemplateFieldRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/templates/{template_id}/fields/{field_id}", response_model=Envelope[None])
async def delete_template_field(
    template_id: UUID,
    field_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:manage")),
) -> dict:
    """Soft-delete a single template field."""
    await LetterTemplateService(session).delete_field(template_id, field_id)
    return success_response(None, "Dihapus")


@router.get("/templates/{template_id}/preview")
async def preview_template(
    template_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> StreamingResponse:
    """Render a PDF preview of the template using auto-generated sample data."""
    service = LetterTemplateService(session)
    template = await service.get_or_404(template_id)
    fields = await service.list_fields(template_id)
    village = await VillageService(session).get_or_404(template.village_id)
    pdf_bytes = TemplateRenderService().render_preview(template, fields, village)
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="preview-{template.code}.pdf"'},
    )
```

- [ ] **Step 7: Register the router** in `app/api/v1/__init__.py`

```python
from app.api.v1 import auth, health, letter_template, master

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
```

- [ ] **Step 8: Run** — `pytest tests/test_letter_template_api.py tests/test_master_data.py -v` → PASS

- [ ] **Step 9: Commit**

```bash
git add app/api/v1/letter_template.py app/api/v1/master.py app/api/v1/__init__.py app/schemas/common.py tests/test_letter_template_api.py
git commit -m "feat(templates): letter-template API router + shared build_page helper"
```

---

### Task 9: Seed 11 letter templates from mockData

**Files:**
- Create: `app/seed/letter_template_data.py`
- Modify: `app/seed/seed.py`
- Test: `tests/test_seed_letter_templates.py`

**Interfaces:**
- Produces: `SURAT_TEMPLATES: list[dict]` (11 entries) in `app/seed/letter_template_data.py`; `async seed_letter_templates(session)` in `app/seed/seed.py`, idempotent, requires `seed_master` to have already created the village; `seed_all` extended to call it last.

- [ ] **Step 1: Implement `app/seed/letter_template_data.py`**

```python
"""Seed data for the 11 letter templates, transcribed from mockData.js suratTypes.

Each entry's ``fields`` list holds tuples:
(field_key, label, field_type, options, placeholder, is_required, validation_rules)
"""

SURAT_TEMPLATES: list[dict] = [
    {
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Usulan cetak / perubahan KK",
        "required_documents": ["KK lama", "KTP kepala keluarga"],
        "numbering_prefix": "474",
        "fields": [
            ("status_perubahan", "Status Perubahan", "select",
             ["Cetak baru", "Perubahan data", "KK hilang"], None, True, None),
            ("jumlah_anggota_keluarga", "Jumlah Anggota Keluarga", "number",
             None, "mis. 4", True, None),
            ("keterangan_perubahan", "Keterangan Perubahan", "text",
             None, "mis. penambahan anggota", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Adalah benar warga kami yang mengajukan permohonan Kartu Keluarga dengan "
            "rincian sebagai berikut:</p>"
            "<p>Status Perubahan: {{ status_perubahan }}<br>"
            "Jumlah Anggota Keluarga: {{ jumlah_anggota_keluarga }} orang<br>"
            "Keterangan: {{ keterangan_perubahan }}</p>"
            "<p>Demikian surat keterangan ini dibuat untuk dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "domisili", "name": "Surat Domisili", "icon": "home_pin",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Keterangan tempat tinggal",
        "required_documents": ["KTP", "KK"],
        "numbering_prefix": "470",
        "fields": [
            ("alamat_tinggal_saat_ini", "Alamat Tinggal Saat Ini", "text",
             None, "Dusun / RT / RW", True, None),
            ("lama_tinggal", "Lama Tinggal", "text", None, "mis. 5 tahun", True, None),
            ("tujuan_penggunaan", "Tujuan Penggunaan", "text",
             None, "mis. persyaratan bank", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat KTP: {{ alamat }}</p>"
            "<p>Benar-benar berdomisili/bertempat tinggal di {{ alamat_tinggal_saat_ini }} "
            "selama {{ lama_tinggal }}.</p>"
            "<p>Surat keterangan ini dibuat untuk keperluan {{ tujuan_penggunaan }} dan agar "
            "dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "description": "Surat keterangan usaha",
        "required_documents": ["KTP", "KK", "Foto tempat usaha"],
        "numbering_prefix": "503",
        "fields": [
            ("jenis_usaha", "Jenis Usaha", "text", None, "mis. warung sembako", True, None),
            ("alamat_usaha", "Alamat Usaha", "text", None, "lokasi usaha", True, None),
            ("nib", "NIB (jika ada)", "text", None, "opsional", False, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Benar memiliki/menjalankan usaha dengan keterangan sebagai berikut:</p>"
            "<p>Jenis Usaha: {{ jenis_usaha }}<br>Alamat Usaha: {{ alamat_usaha }}<br>"
            "NIB: {{ nib }}</p>"
            "<p>Demikian Surat Keterangan Usaha ini dibuat untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "sktm", "name": "Ket. Tidak Mampu", "icon": "volunteer_activism",
        "color_bg": "#F3EAFB", "color_fg": "#7B4BC0",
        "description": "SKTM untuk bantuan",
        "required_documents": ["KTP", "KK", "Surat pengantar RT/RW"],
        "numbering_prefix": "460",
        "fields": [
            ("keperluan", "Keperluan", "select",
             ["Beasiswa", "Kesehatan", "Bansos"], None, True, None),
            ("penghasilan_bulan", "Penghasilan / Bulan", "text",
             None, "mis. Rp 1.200.000", True, None),
            ("lampiran_pendukung", "Lampiran Pendukung", "text",
             None, "mis. surat sekolah", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Adalah benar warga kami yang tergolong keluarga kurang mampu dengan "
            "penghasilan {{ penghasilan_bulan }} per bulan.</p>"
            "<p>Surat keterangan ini dibuat untuk keperluan {{ keperluan }} dengan lampiran "
            "pendukung: {{ lampiran_pendukung }}.</p>"
            "<p>Demikian surat ini dibuat dengan sebenarnya untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "lahir", "name": "Ket. Kelahiran", "icon": "child_friendly",
        "color_bg": "#FFF1F4", "color_fg": "#C93B6A",
        "description": "Surat keterangan lahir",
        "required_documents": ["KK", "KTP orang tua", "Surat bidan/RS"],
        "numbering_prefix": "471",
        "fields": [
            ("nama_bayi", "Nama Bayi", "text", None, "nama lengkap bayi", True, None),
            ("tanggal_tempat_lahir", "Tanggal & Tempat Lahir", "text",
             None, "mis. Kopo, 12 Jul 2026", True, None),
            ("nama_saksi", "Nama Saksi", "text", None, "saksi kelahiran", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa telah lahir seorang anak dari:</p>"
            "<p>Nama Orang Tua: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Dengan keterangan bayi sebagai berikut:</p>"
            "<p>Nama Bayi: {{ nama_bayi }}<br>Tanggal &amp; Tempat Lahir: "
            "{{ tanggal_tempat_lahir }}<br>Nama Saksi: {{ nama_saksi }}</p>"
            "<p>Demikian Surat Keterangan Kelahiran ini dibuat untuk dipergunakan "
            "sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "description": "Surat keterangan kematian",
        "required_documents": ["KK", "KTP almarhum", "Surat RS (bila ada)"],
        "numbering_prefix": "472",
        "fields": [
            ("nama_almarhum", "Nama Almarhum/ah", "text", None, "nama lengkap", True, None),
            ("tanggal_tempat_wafat", "Tanggal & Tempat Wafat", "text",
             None, "mis. Kopo, 10 Jul 2026", True, None),
            ("penyebab", "Penyebab", "text", None, "mis. sakit", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama Almarhum/ah: <b>{{ nama_almarhum }}</b></p>"
            "<p>Benar telah meninggal dunia pada {{ tanggal_tempat_wafat }} dengan penyebab "
            "{{ penyebab }}.</p>"
            "<p>Yang melaporkan:</p>"
            "<p>Nama: {{ nama }}<br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Demikian Surat Keterangan Kematian ini dibuat untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "pindah", "name": "Surat Pindah", "icon": "moving",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Pindah domisili keluar",
        "required_documents": ["KK", "KTP semua anggota"],
        "numbering_prefix": "475",
        "fields": [
            ("alamat_tujuan", "Alamat Tujuan", "text", None, "alamat baru lengkap", True, None),
            ("alasan_pindah", "Alasan Pindah", "text", None, "mis. pekerjaan", True, None),
            ("anggota_yang_ikut", "Anggota yang Ikut", "number",
             None, "jumlah orang", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat Asal: {{ alamat }}</p>"
            "<p>Benar bermaksud pindah domisili ke {{ alamat_tujuan }} dengan alasan "
            "{{ alasan_pindah }}, bersama {{ anggota_yang_ikut }} anggota keluarga.</p>"
            "<p>Demikian Surat Pindah ini dibuat untuk dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "datang", "name": "Ket. Datang", "icon": "login",
        "color_bg": "#E7F4EC", "color_fg": "#1F8A56",
        "description": "Kedatangan penduduk baru",
        "required_documents": ["Surat pindah desa asal", "KTP", "KK"],
        "numbering_prefix": "476",
        "fields": [
            ("asal_domisili_sebelumnya", "Asal Domisili Sebelumnya", "text",
             None, "alamat asal", True, None),
            ("tujuan_menetap", "Tujuan Menetap", "text", None, "mis. bekerja", True, None),
            ("surat_pindah_asal", "Surat Pindah Asal", "text",
             None, "nomor surat pindah", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat Sekarang: {{ alamat }}</p>"
            "<p>Benar telah datang dan menetap di desa ini, berasal dari "
            "{{ asal_domisili_sebelumnya }} dengan tujuan {{ tujuan_menetap }}, sesuai Surat "
            "Pindah Nomor {{ surat_pindah_asal }}.</p>"
            "<p>Demikian Surat Keterangan Kedatangan ini dibuat untuk dipergunakan "
            "sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "ktp", "name": "Pengantar KTP", "icon": "badge",
        "color_bg": "#FDF3DC", "color_fg": "#B7791F",
        "description": "Pengantar rekam/cetak KTP",
        "required_documents": ["KK", "KTP lama (bila ada)"],
        "numbering_prefix": "477",
        "fields": [
            ("keperluan", "Keperluan", "select",
             ["KTP baru", "Perubahan data", "KTP hilang"], None, True, None),
            ("keterangan", "Keterangan", "text", None, "detail keperluan", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, dengan ini memberikan "
            "surat pengantar kepada:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Untuk keperluan {{ keperluan }} dengan keterangan: {{ keterangan }}.</p>"
            "<p>Surat pengantar ini dibuat agar yang bersangkutan dapat memproses KTP di "
            "instansi terkait.</p>"
        ),
    },
    {
        "code": "kkpengantar", "name": "Pengantar KK", "icon": "contact_page",
        "color_bg": "#FDF3DC", "color_fg": "#B7791F",
        "description": "Pengantar cetak/ubah KK",
        "required_documents": ["KTP", "KK lama (bila ada)"],
        "numbering_prefix": "478",
        "fields": [
            ("keperluan", "Keperluan", "select",
             ["KK baru", "Perubahan data", "KK hilang"], None, True, None),
            ("keterangan", "Keterangan", "text", None, "detail keperluan", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, dengan ini memberikan "
            "surat pengantar kepada:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Untuk keperluan {{ keperluan }} dengan keterangan: {{ keterangan }}.</p>"
            "<p>Surat pengantar ini dibuat agar yang bersangkutan dapat memproses Kartu "
            "Keluarga di instansi terkait.</p>"
        ),
    },
    {
        "code": "keramaian", "name": "Izin Keramaian", "icon": "celebration",
        "color_bg": "#F3EAFB", "color_fg": "#7B4BC0",
        "description": "Izin acara / hajatan",
        "required_documents": ["KTP penanggung jawab", "Denah lokasi"],
        "numbering_prefix": "300",
        "fields": [
            ("jenis_acara", "Jenis Acara", "text", None, "mis. pernikahan", True, None),
            ("tanggal_lokasi", "Tanggal & Lokasi", "text",
             None, "kapan & di mana", True, None),
            ("estimasi_peserta", "Estimasi Peserta", "number", None, "mis. 200", True, None),
            ("penanggung_jawab", "Penanggung Jawab", "text",
             None, "nama & kontak", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, memberikan izin "
            "penyelenggaraan keramaian/acara dengan keterangan sebagai berikut:</p>"
            "<p>Jenis Acara: {{ jenis_acara }}<br>Tanggal &amp; Lokasi: {{ tanggal_lokasi }}<br>"
            "Estimasi Peserta: {{ estimasi_peserta }} orang<br>"
            "Penanggung Jawab: {{ penanggung_jawab }}</p>"
            "<p>Pemohon:</p>"
            "<p>Nama: {{ nama }}<br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Demikian surat izin ini dibuat dengan ketentuan penyelenggara wajib menjaga "
            "ketertiban dan keamanan selama acara berlangsung.</p>"
        ),
    },
]
```

- [ ] **Step 2: Write failing test** `tests/test_seed_letter_templates.py`

```python
import pytest
from sqlalchemy import func, select

from app.models.letter_template import LetterTemplate, TemplateField
from app.seed.seed import seed_master, seed_letter_templates


@pytest.mark.asyncio
async def test_seed_letter_templates_idempotent(db_session):
    await seed_master(db_session)  # creates the village seed_letter_templates depends on
    await seed_letter_templates(db_session)
    await seed_letter_templates(db_session)

    template_count = await db_session.scalar(select(func.count()).select_from(LetterTemplate))
    assert template_count == 11

    field_count = await db_session.scalar(select(func.count()).select_from(TemplateField))
    assert field_count == 32  # kk,domisili,usaha,sktm,lahir,mati,pindah,datang=3 each (24);
    # ktp,kkpengantar=2 each (4); keramaian=4 → 24+4+4=32

    kk = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "kk"))
    assert kk.numbering_prefix == "474"
    assert kk.required_documents == ["KK lama", "KTP kepala keluarga"]
```

- [ ] **Step 3: Run** — FAIL

- [ ] **Step 4: Add `seed_letter_templates` to `app/seed/seed.py`**

Add these imports:
```python
from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.seed.letter_template_data import SURAT_TEMPLATES
```

Append this function:
```python
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
```

Update `seed_all`:
```python
async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: RBAC/demo-users, village hierarchy+residents, letter templates."""
    await seed_rbac(session)
    await seed_master(session)
    await seed_letter_templates(session)
```

- [ ] **Step 5: Run** — `pytest tests/test_seed_letter_templates.py -v` → PASS

- [ ] **Step 6: Commit**

```bash
git add app/seed/letter_template_data.py app/seed/seed.py tests/test_seed_letter_templates.py
git commit -m "feat(templates): seed 11 letter templates from mockData suratTypes"
```

---

### Task 10: Full verification

**Files:**
- Modify: `README.md`

**Interfaces:** none (verification + docs gate).

- [ ] **Step 1: Run the whole test suite**

Run: `pytest -q`

Expected: all tests PASS (existing Foundation tests + all new template tests).

- [ ] **Step 2: Lint**

Run: `ruff check app tests`

Expected: all checks passed.

- [ ] **Step 3: Live verification against `db_kopo`**

```bash
alembic upgrade head
python -m app.seed
```

Expected: migration applies cleanly (idempotent if already applied), seeding logs report 11
letter templates created (or "already present" on a re-run — run `python -m app.seed` twice
to confirm idempotency live, not just in the SQLite test DB).

Then manually confirm via a short SQLAlchemy query (or `psql`) that `letter_templates` has
11 rows and `template_fields` has the expected total row count in `db_kopo`.

- [ ] **Step 4: Manual smoke of the preview endpoint**

```bash
uvicorn app.main:app --reload
```
In `/docs`: log in as `operator/operator123`, `GET /api/v1/templates` (200, 11 items), pick
one template id, `GET /api/v1/templates/{id}/preview` — confirm it downloads/renders a real
PDF with the letterhead, body, and signature block.

- [ ] **Step 5: Update `README.md`**

Add a short "Letter Templates" section under the existing API surface list, documenting the
new endpoints (`/templates`, `/templates/{id}/fields`, `/templates/{id}/fields/reorder`,
`/templates/{id}/preview`) and noting that redaksi (letter body) is a generic draft pending
official text from Desa Kopo, editable via these endpoints. Update the Roadmap note to mark
Phase 4 done and B2 (Fase 5-7: Pengajuan, Approval, PDF issuance) as next.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: letter template engine run guide + Phase 4 verification"
```

---

## Self-Review

**1. Spec coverage:**
- Model + migration (`LetterTemplate`, `TemplateField`) → Task 3. ✓
- API (CRUD template + field CRUD/reorder + preview, all with `response_model`) → Tasks 4, 5, 6, 8. ✓
- Numbering format definition (pattern + prefix, preview-only, no counter) → Task 3 (columns) + Task 7 (`_preview_number`). ✓ No counter/allocation logic anywhere, per spec's explicit exclusion.
- PDF preview via sandboxed Jinja2 + xhtml2pdf (substituted for the spec's WeasyPrint after Task 1's Windows GTK-library blocker; user-approved), reusable render function → Task 7. ✓
- Seeding 11 templates from `mockData.js` with generic redaksi → Task 9. ✓ All 11 codes, names, icons, colors, required_documents, numbering_prefix, and field definitions cross-checked against the `suratTypes`/`NOMOR_PREFIX` transcription done during design.
- RBAC: `template:manage` (administrator via `*`), `template:read` (staf/sekretaris/kades) → Task 2, enforced in Task 8's router, tested in Task 8's 403 test.
- DoD: CRUD+pagination/validation/response_model, 11 templates seeded+previewable, RBAC enforced, tests green → Task 10.

**2. Placeholder scan:** No TBD/TODO in any step's code. `tests/test_seed_letter_templates.py`'s `field_count` assertion was initially miscounted (30) during drafting — caught in this self-review and corrected to the true sum (32: eight templates × 3 fields + two templates × 2 fields + one template × 4 fields). Fixing that now rather than leaving it as a trap.

**3. Type consistency:** `LetterTemplateService`/`TemplateRenderService` constructor and method signatures match between Task 5/6 (service) and Task 7/8 (render service, router) call sites. `TemplateFieldRead`/`LetterTemplateRead` field names match the ORM columns from Task 3. `build_page(items, total, page, size, schema)` signature is used identically in both `master.py` (refactored) and `letter_template.py` (new) — verified same positional order at both call sites in Task 8.
