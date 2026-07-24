# Rework Part 2: Multi-Village Removal — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the `Village` model and every `village_id` column (6 tables), replacing
Village's descriptive fields with a single-row `VillageProfile` singleton — per the
rework spec's decision to drop multi-desa support entirely.

**Architecture:** `VillageProfile` is added first (additive, safe). All application code
is migrated off `Village`/`village_id` next (services, schemas, APIs, seed, tests).
Only once nothing references the old columns does the destructive migration
(drop `village_id` × 6, drop `villages`) run — minimizing the window where the app is
in a broken intermediate state.

**Tech Stack:** SQLAlchemy Async, Alembic (unchanged).

## Global Constraints

- Every schema change goes through a **new** Alembic revision — never edit an
  already-applied revision.
- `VillageProfile` has exactly one row, enforced at the service layer (not a DB
  constraint) — `VillageProfileService` only exposes `get()`/`update()`, no
  `create()`/`delete()`/list, and no CRUD API beyond `GET`/`PUT /village-profile`.
- After this part, **no table has a `village_id` column** and the `villages` table does
  not exist. Every place that used to accept/require `village_id` as an API/schema
  field must have it removed, not just made optional.
- `LetterTemplate`'s unique constraint changes from `(village_id, code)` to `code` alone
  (single-desa: template codes are now globally unique, not per-village).
- The final test suite must pass 100% and `ruff check app tests` must be clean before
  Part 2 is considered done — this part touches nearly every module, so treat "all
  green" as non-negotiable, not aspirational.
- Do not touch `app/api/v1/public.py`, `app/services/qr.py`, or anything about
  signatures/QR/`verification_code` — that removal is a separate, later rework part
  (Part 4). If a file you're editing also happens to reference those, leave that part
  alone and only touch the `village`/`village_id` concern.

---

### Task 1: `VillageProfile` model

**Files:**
- Modify: `app/models/master.py`

**Interfaces:**
- Produces: `VillageProfile` class. `Village` class is left untouched in this task
  (removed in Task 8) so intermediate states stay importable.

- [ ] **Step 1: Add `Text` to the sqlalchemy import**

Change the top of `app/models/master.py` from:
```python
from sqlalchemy import Date, ForeignKey, String
```
to:
```python
from sqlalchemy import Date, ForeignKey, String, Text
```

- [ ] **Step 2: Add the `VillageProfile` class**

Insert it right after the `Village` class (before `Dusun`):

```python
class VillageProfile(UUIDMixin, TimestampMixin, Base):
    """Singleton row describing the (single) village this system serves.

    Replaces the old multi-village ``Village`` model -- multi-desa support
    was explicitly removed (see the rework spec). Exactly one row is
    expected to exist; enforced by ``VillageProfileService``, not a DB
    constraint (sufficient for this application's single-tenant scale).
    """

    __tablename__ = "village_profile"
    name: Mapped[str] = mapped_column(String(150))
    slogan: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kecamatan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    kades_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    kades_photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    sambutan_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    kontak_alamat: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kontak_telp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    kontak_email: Mapped[str | None] = mapped_column(String(150), nullable=True)
    kontak_jam: Mapped[str | None] = mapped_column(String(150), nullable=True)
    jumlah_jiwa: Mapped[int | None] = mapped_column(nullable=True)
    jumlah_kk: Mapped[int | None] = mapped_column(nullable=True)
    luas_wilayah: Mapped[str | None] = mapped_column(String(50), nullable=True)
```

- [ ] **Step 3: Verify import**

Run: `python -c "import app.models.master"`
Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add app/models/master.py
git commit -m "feat(village): add VillageProfile singleton model"
```

---

### Task 2: Migration — create `village_profile`, migrate existing data

**Files:**
- Create: `alembic/versions/<hash>_village_profile_table.py`

**Interfaces:**
- Consumes: `VillageProfile` (Task 1), the still-existing `villages` table (1 row in
  `db_kopo`, seeded from `app/seed/data.py`'s `VILLAGE` dict:
  `{"name": "Desa Kopo", "slogan": "Kopo Kita", "kecamatan": "Cisarua", "kabupaten":
  "Kabupaten Bogor", "provinsi": "Jawa Barat"}`).
- Produces: `village_profile` table, populated with exactly one row copied from the
  existing `villages` row (name/slogan/kecamatan/kabupaten/provinsi carried over; the
  new portal-only fields — description, photo_path, kades_name, etc. — left NULL, to be
  filled in by a later rework part).

- [ ] **Step 1: Autogenerate**

Run: `alembic revision --autogenerate -m "village profile table"`
Add `import app.db.base` (same fix every prior migration needed).

- [ ] **Step 2: Add the data migration**

Autogenerate only emits the `op.create_table('village_profile', ...)` — it never
migrates data. After the generated `op.create_table(...)` call inside `upgrade()`, add:

```python
    # Carry the existing single Village row's descriptive fields into the new
    # village_profile singleton. Uses raw table reflection (not the ORM
    # model, which may have already moved on by the time this migration
    # runs again in a fresh environment) so this stays correct independent
    # of app/models/master.py's current state.
    connection = op.get_bind()
    village_profile_table = sa.table(
        "village_profile",
        sa.column("id", app.db.base.GUID()),
        sa.column("name", sa.String),
        sa.column("slogan", sa.String),
        sa.column("kecamatan", sa.String),
        sa.column("kabupaten", sa.String),
        sa.column("provinsi", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    villages_table = sa.table(
        "villages",
        sa.column("id", app.db.base.GUID()),
        sa.column("name", sa.String),
        sa.column("slogan", sa.String),
        sa.column("kecamatan", sa.String),
        sa.column("kabupaten", sa.String),
        sa.column("provinsi", sa.String),
    )
    existing = connection.execute(sa.select(villages_table)).fetchone()
    if existing is not None:
        connection.execute(
            village_profile_table.insert().values(
                id=uuid.uuid4(),
                name=existing.name,
                slogan=existing.slogan,
                kecamatan=existing.kecamatan,
                kabupaten=existing.kabupaten,
                provinsi=existing.provinsi,
                created_at=sa.func.now(),
                updated_at=sa.func.now(),
            )
        )
```

Add `import uuid` at the top of the migration file alongside the existing imports (it's
needed for `uuid.uuid4()` above).

- [ ] **Step 3: Write the matching `downgrade()` data-reversal (optional but keep the table drop)**

The autogenerated `downgrade()` will `op.drop_table('village_profile')` — leave that as
the only downgrade step (no need to reconstruct the deleted `villages` row on
downgrade; `villages` itself isn't touched by this migration).

- [ ] **Step 4: Apply to `db_kopo` and verify**

Run: `alembic upgrade head`

Then verify the copy worked:
```bash
python -c "
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.master import VillageProfile

async def main():
    async with AsyncSessionLocal() as s:
        rows = (await s.scalars(select(VillageProfile))).all()
        assert len(rows) == 1, f'expected exactly 1 row, got {len(rows)}'
        print(rows[0].name, rows[0].slogan, rows[0].kecamatan, rows[0].kabupaten, rows[0].provinsi)

asyncio.run(main())
"
```
Expected: exactly one row, printing `Desa Kopo Kopo Kita Cisarua Kabupaten Bogor Jawa Barat`
(adjust the session-maker import if `AsyncSessionLocal` isn't the actual exported name —
check `app/db/session.py` first).

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(village): migration for village_profile table + data copy"
```

---

### Task 3: `VillageProfileService` + schemas + `GET`/`PUT /village-profile`

**Files:**
- Modify: `app/services/master.py` (add `VillageProfileService`, remove `VillageService`)
- Modify: `app/schemas/master.py` (add `VillageProfileRead`/`VillageProfileUpdate`,
  remove `VillageCreate`/`VillageUpdate`/`VillageRead`)
- Modify: `app/api/v1/master.py` (replace the `# ---- Villages ----` block)

**Interfaces:**
- Produces: `VillageProfileService.get() -> VillageProfile`,
  `VillageProfileService.update(data: dict) -> VillageProfile`.
- Consumed by: Task 5 (letter template preview), Task 6 (submission issuance).

- [ ] **Step 1: Replace `VillageService` with `VillageProfileService`**

In `app/services/master.py`, change the import line:
```python
from app.models.master import RT, RW, Dusun, FamilyCard, Resident, Village
```
to:
```python
from app.models.master import RT, RW, Dusun, FamilyCard, Resident, VillageProfile
```

Then replace the `VillageService` class with:

```python
class VillageProfileService:
    """Singleton accessor for the village's descriptive profile.

    Exactly one VillageProfile row is expected to exist (seeded). No
    create/delete/list by design -- see the rework spec.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, VillageProfile)

    async def get(self) -> VillageProfile:
        """Return the singleton profile row."""
        stmt = select(VillageProfile).limit(1)
        obj = await self.session.scalar(stmt)
        if obj is None:
            raise NotFoundError("Profil desa belum tersedia")
        return obj

    async def update(self, data: dict[str, Any]) -> VillageProfile:
        """Update the singleton profile row."""
        obj = await self.get()
        obj = await self.repo.update(obj, **data)
        await self.session.commit()
        logger.info("VillageProfile updated id=%s", obj.id)
        return obj
```

This needs `select` imported — add `from sqlalchemy import Column, select` (extending
the existing `from sqlalchemy import Column` line already in this file).

- [ ] **Step 2: Replace Village schemas with VillageProfile schemas**

In `app/schemas/master.py`, replace `VillageCreate`/`VillageUpdate`/`VillageRead` with:

```python
class VillageProfileUpdate(BaseModel):
    name: str | None = None
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None
    description: str | None = None
    photo_path: str | None = None
    kades_name: str | None = None
    kades_photo_path: str | None = None
    sambutan_text: str | None = None
    kontak_alamat: str | None = None
    kontak_telp: str | None = None
    kontak_email: str | None = None
    kontak_jam: str | None = None
    jumlah_jiwa: int | None = None
    jumlah_kk: int | None = None
    luas_wilayah: str | None = None


class VillageProfileRead(_Read):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None
    description: str | None = None
    photo_path: str | None = None
    kades_name: str | None = None
    kades_photo_path: str | None = None
    sambutan_text: str | None = None
    kontak_alamat: str | None = None
    kontak_telp: str | None = None
    kontak_email: str | None = None
    kontak_jam: str | None = None
    jumlah_jiwa: int | None = None
    jumlah_kk: int | None = None
    luas_wilayah: str | None = None
```

(No `VillageProfileCreate` — it's never created via API, only seeded.)

- [ ] **Step 3: Replace the `/villages` router block**

In `app/api/v1/master.py`, replace the entire `# ---- Villages ----` block (from
`@router.post("/villages"...)` through the `delete_village` function) with:

```python
# ---- Village Profile (singleton) ----
@router.get("/village-profile", response_model=Envelope[VillageProfileRead])
async def get_village_profile(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("auth:me")),
) -> dict:
    """Get the village's profile. Any authenticated user may read it."""
    obj = await VillageProfileService(session).get()
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"))


@router.put("/village-profile", response_model=Envelope[VillageProfileRead])
async def update_village_profile(
    body: VillageProfileUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("village:manage")),
) -> dict:
    """Update the village's profile."""
    obj = await VillageProfileService(session).update(body.model_dump(exclude_unset=True))
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")
```

Update the two import blocks at the top of the file accordingly: replace
`VillageCreate, VillageRead, VillageUpdate,` with `VillageProfileRead,
VillageProfileUpdate,` in the `from app.schemas.master import (...)` block, and replace
`VillageService,` with `VillageProfileService,` in the `from app.services.master
import (...)` block.

- [ ] **Step 4: Verify**

Run: `python -c "import app.api.v1.master"`
Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add app/services/master.py app/schemas/master.py app/api/v1/master.py
git commit -m "feat(village): VillageProfileService + GET/PUT /village-profile"
```

---

### Task 4: Remove `village_id` from Dusun/FamilyCard/Resident + Village model

**Files:**
- Modify: `app/models/master.py` (remove `village_id` from `Dusun`, `FamilyCard`,
  `Resident`; remove the `Village` class entirely)
- Modify: `app/schemas/master.py` (remove `village_id` from `DusunCreate`,
  `FamilyCardCreate`, `ResidentCreate`, `ResidentRead`, `FamilyCardRead`, `DusunRead`)
- Modify: `app/api/v1/master.py` (remove the `village_id` query param from
  `import_residents`/`export_residents`)
- Modify: `app/services/excel.py` (drop the `village_id` parameter)

**Interfaces:**
- Produces: `Dusun`/`FamilyCard`/`Resident` without `village_id`.
- Breaking change for: `ResidentExcelService.import_bytes`/`export_bytes` signatures
  (Task 9 fixes any remaining caller; this task fixes the direct ones in
  `app/api/v1/master.py`).

- [ ] **Step 1: `app/models/master.py` — remove `Village`, remove `village_id` columns**

Delete the entire `Village` class.

In `Dusun`, delete the line:
```python
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
```

In `FamilyCard`, delete the line:
```python
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
```

In `Resident`, delete the line:
```python
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
```

- [ ] **Step 2: `app/schemas/master.py` — remove `village_id` fields**

Remove `village_id: UUID` from `DusunCreate`, `DusunRead`, `FamilyCardCreate`,
`FamilyCardRead`, `ResidentCreate`, `ResidentRead` (6 occurrences total — `DusunUpdate`/
`FamilyCardUpdate`/`ResidentUpdate` never had it, leave those alone).

- [ ] **Step 3: `app/services/excel.py` — drop the `village_id` parameter**

Change `import_bytes`'s signature from
`async def import_bytes(self, file_bytes: bytes, village_id: uuid.UUID) -> dict:` to
`async def import_bytes(self, file_bytes: bytes) -> dict:`, and remove
`village_id=village_id,` from the `self.residents.repo.create(...)` call inside it.
Remove the now-unused `import uuid` at the top of the file if nothing else in the file
uses the `uuid` module (check first — `uuid.UUID` was only used in that one type hint).

`export_bytes` already takes generic `filters: dict[str, Any] | None` — no signature
change needed there, but its only caller currently passes
`{"village_id": village_id}` (fixed in Step 4 below).

- [ ] **Step 4: `app/api/v1/master.py` — drop `village_id` from import/export endpoints**

Change:
```python
@router.post("/residents/import", response_model=Envelope[ResidentImportResult])
async def import_residents(
    village_id: UUID,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:import")),
) -> dict:
    """Bulk-import residents for a village from an uploaded xlsx file."""
    content = await file.read()
    result = await ResidentExcelService(session).import_bytes(content, village_id)
    return success_response(result, "Import selesai")
```
to:
```python
@router.post("/residents/import", response_model=Envelope[ResidentImportResult])
async def import_residents(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:import")),
) -> dict:
    """Bulk-import residents from an uploaded xlsx file."""
    content = await file.read()
    result = await ResidentExcelService(session).import_bytes(content)
    return success_response(result, "Import selesai")
```

Change:
```python
@router.get("/residents/export")
async def export_residents(
    village_id: UUID | None = Query(None),
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:export")),
) -> StreamingResponse:
    """Export residents matching the given filters as an xlsx download."""
    data = await ResidentExcelService(session).export_bytes({"village_id": village_id})
```
to:
```python
@router.get("/residents/export")
async def export_residents(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("resident:export")),
) -> StreamingResponse:
    """Export all residents as an xlsx download."""
    data = await ResidentExcelService(session).export_bytes()
```

Also remove `ResidentCreate`'s `village_id` field usage anywhere else in this file if
present (there is none beyond schema validation, already handled in Step 2).

- [ ] **Step 5: Verify imports**

Run: `python -c "import app.models.master; import app.schemas.master; import app.services.excel; import app.api.v1.master"`
Expected: exit code 0.

- [ ] **Step 6: Commit**

```bash
git add app/models/master.py app/schemas/master.py app/services/excel.py app/api/v1/master.py
git commit -m "feat(village): drop Village model + village_id from Dusun/FamilyCard/Resident"
```

---

### Task 5: Remove `village_id` from `LetterTemplate`

**Files:**
- Modify: `app/models/letter_template.py`
- Modify: `app/schemas/letter_template.py`
- Modify: `app/api/v1/letter_template.py` (preview endpoint uses `VillageProfileService`
  now, not `VillageService`)
- Modify: `app/services/template_render.py` (`Village` param renamed to `VillageProfile`
  throughout)

**Interfaces:**
- Consumes: `VillageProfileService` (Task 3).
- Produces: `LetterTemplate` without `village_id`, unique constraint on `code` alone.
  `TemplateRenderService.render_preview`/`render_issued`/`_render_document` take a
  `VillageProfile` object (renamed parameter, same shape usage: `.kabupaten`,
  `.kecamatan`, `.name`).

- [ ] **Step 1: `app/models/letter_template.py`**

Change:
```python
    __table_args__ = (
        UniqueConstraint("village_id", "code", name="uq_letter_templates_village_code"),
    )

    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    code: Mapped[str] = mapped_column(String(50), index=True)
```
to:
```python
    __table_args__ = (
        UniqueConstraint("code", name="uq_letter_templates_code"),
    )

    code: Mapped[str] = mapped_column(String(50), unique=True, index=True)
```

(The `unique=True` on the column is redundant with the table-level `UniqueConstraint`
but matches this project's existing style elsewhere, e.g. `Permission.code` — keep
just the `UniqueConstraint` form to avoid a double-unique-index; drop `unique=True` from
the column itself, only add it to `__table_args__` as shown above.)

- [ ] **Step 2: `app/schemas/letter_template.py`**

Remove `village_id: UUID` from `LetterTemplateCreate` and `LetterTemplateRead`.

- [ ] **Step 3: `app/services/template_render.py`**

Replace every `Village` reference with `VillageProfile`:
- Import line: `from app.models.master import Village` → `from app.models.master import VillageProfile`
- `_render_document`'s signature: `village: Village` → `profile: VillageProfile`
- Inside `_render_document`, `village.kabupaten` → `profile.kabupaten`,
  `village.kecamatan` → `profile.kecamatan`, `village_name=village.name` →
  `village_name=profile.name`
- `render_preview`'s signature: `village: Village` → `profile: VillageProfile`, and its
  call into `_render_document` passes `village=village` → `profile=profile`
- `render_issued`'s signature: `village: Village` → `profile: VillageProfile`, same call
  update

- [ ] **Step 4: `app/api/v1/letter_template.py`**

Change the import from `from app.services.master import VillageService` to
`from app.services.master import VillageProfileService`.

Change the preview endpoint body from:
```python
    village = await VillageService(session).get_or_404(template.village_id)
    pdf_bytes = TemplateRenderService().render_preview(template, fields, village)
```
to:
```python
    profile = await VillageProfileService(session).get()
    pdf_bytes = TemplateRenderService().render_preview(template, fields, profile)
```

- [ ] **Step 5: Verify**

Run: `python -c "import app.models.letter_template; import app.schemas.letter_template; import app.services.template_render; import app.api.v1.letter_template"`
Expected: exit code 0.

- [ ] **Step 6: Commit**

```bash
git add app/models/letter_template.py app/schemas/letter_template.py app/services/template_render.py app/api/v1/letter_template.py
git commit -m "feat(village): drop village_id from LetterTemplate, use VillageProfile for rendering"
```

---

### Task 6: Remove `village_id` from `Submission`/`ApprovalStepConfig`

**Files:**
- Modify: `app/models/submission.py`
- Modify: `app/schemas/submission.py`
- Modify: `app/services/submission.py`
- Modify: `app/services/approval_config.py`
- Modify: `app/api/v1/submission.py`
- Modify: `app/api/v1/approval_config.py`
- Modify: `app/api/v1/public.py` (only the `village_id`-adjacent parts, if any — do NOT
  remove QR/verification_code logic, that's a later part)

**Interfaces:**
- Consumes: `VillageProfileService` (Task 3).
- Produces: `Submission`/`ApprovalStepConfig` without `village_id`.
  `ApprovalStepConfigService.list_steps()`/`replace_all()` no longer take a `village_id`
  parameter (there's only ever one chain now, not one per village).
  `SubmissionService.create`/`approve`/`reject`/`_issue` no longer reference
  `submission.village_id`.

- [ ] **Step 1: `app/models/submission.py`**

In `ApprovalStepConfig`, change:
```python
    __table_args__ = (
        UniqueConstraint("village_id", "order_index", name="uq_approval_step_village_order"),
    )

    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    order_index: Mapped[int] = mapped_column()
```
to:
```python
    __table_args__ = (
        UniqueConstraint("order_index", name="uq_approval_step_order"),
    )

    order_index: Mapped[int] = mapped_column()
```

In `Submission`, delete the line:
```python
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
```

- [ ] **Step 2: `app/schemas/submission.py`**

Remove `village_id: UUID` from `ApprovalStepConfigRead` and `SubmissionRead`.

- [ ] **Step 3: `app/services/approval_config.py`**

Change `list_steps` from:
```python
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
```
to:
```python
    async def list_steps(self) -> list[ApprovalStepConfig]:
        """Return the approval steps, ordered."""
        stmt = (
            select(ApprovalStepConfig)
            .where(ApprovalStepConfig.deleted_at.is_(None))
            .order_by(ApprovalStepConfig.order_index)
        )
        return list((await self.session.scalars(stmt)).all())
```

Change `replace_all` from `async def replace_all(self, village_id: uuid.UUID, role_ids:
list[uuid.UUID]) -> list[ApprovalStepConfig]:` to `async def replace_all(self, role_ids:
list[uuid.UUID]) -> list[ApprovalStepConfig]:`, and inside it:
- The pending-submission guard query drops `Submission.village_id == village_id,` from
  its `.where(...)` (it now checks globally: `select(func.count()).select_from(Submission).where(Submission.status == SubmissionStatus.PENDING)`).
- `existing = await self.list_steps(village_id)` → `existing = await self.list_steps()`
  (both occurrences in the function, including the final `return await
  self.list_steps(village_id)` → `return await self.list_steps()`).
- `ApprovalStepConfig(village_id=village_id, order_index=index, role_id=role_id)` →
  `ApprovalStepConfig(order_index=index, role_id=role_id)`.

- [ ] **Step 4: `app/api/v1/approval_config.py`**

Replace the whole file content with:

```python
"""Village approval-step configuration endpoints."""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.schemas.submission import ApprovalStepConfigRead, ApprovalStepsReplaceRequest
from app.services.approval_config import ApprovalStepConfigService

router = APIRouter(tags=["approval-config"])


@router.get("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def list_approval_steps(
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("template:read")),
) -> dict:
    """List the ordered approval steps."""
    steps = await ApprovalStepConfigService(session).list_steps()
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps]
    )


@router.put("/approval-steps", response_model=Envelope[list[ApprovalStepConfigRead]])
async def replace_approval_steps(
    body: ApprovalStepsReplaceRequest,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("approval_config:manage")),
) -> dict:
    """Replace the entire approval-step chain."""
    steps = await ApprovalStepConfigService(session).replace_all(
        [item.role_id for item in body.steps]
    )
    return success_response(
        [ApprovalStepConfigRead.model_validate(s).model_dump(mode="json") for s in steps],
        "Alur persetujuan diperbarui",
    )
```

This removes the `_ReplaceBody` subclass entirely (it existed only to bolt `village_id`
onto the request) — callers now post `ApprovalStepsReplaceRequest`'s own shape
directly (`{"steps": [...]}`), unchanged otherwise.

- [ ] **Step 5: `app/services/submission.py`**

Remove the `from app.models.master import FamilyCard, Resident, Village` import's
`Village` (keep `FamilyCard, Resident`) — add `VillageProfile` if still needed, or
remove entirely if this file no longer touches it directly after the changes below
(check: `_issue` uses `Village` — replace with `VillageProfile` via
`VillageProfileService`, so change the import to
`from app.models.master import FamilyCard, Resident` and add
`from app.services.master import VillageProfileService` alongside the other
`app.services.*` imports).

In `create()`, remove `village_id=template.village_id,` from the `Submission(...)`
construction.

`_generate_verification_code(self, village: Village, year: int)` — leave this method
alone entirely in THIS task (it's part of the QR/verification-code system removed in a
later rework part, not this one) EXCEPT it currently takes a `village: Village`
parameter that will break once `Village` is removed. Since fixing its actual logic is
out of this task's scope, the minimal correct fix here is to change its parameter type
from `Village` to `VillageProfile` (same `.name` attribute access, no behavior change)
so it keeps compiling — do not remove or restructure the verification-code feature
itself.

In `_issue()`, change:
```python
        village = await self.session.get(Village, submission.village_id)
```
to:
```python
        village = await VillageProfileService(self.session).get()
```
(the local variable name `village` can stay as-is here since it's purely local — the
rest of `_issue`'s body already refers to it as `village` and that still reads fine for
a `VillageProfile` instance; do not do a blanket rename inside this method, only change
the one assignment line above and the render call's keyword argument name to match
Task 5's renamed parameter: `TemplateRenderService().render_issued(template=template,
fields=fields, profile=village, ...)` — i.e. change the keyword from `village=village`
to `profile=village`, keep the local variable name `village`).

- [ ] **Step 6: `app/api/v1/submission.py`**

Confirmed: this file contains no reference to `village_id` or `Village` anywhere in its
current content. No changes needed — do not edit this file in this task.

- [ ] **Step 7: `app/api/v1/public.py`**

Confirmed: this file contains no reference to `village_id` or `Village` anywhere in its
current content (it only touches `Submission`, `LetterTemplate`, `User`,
`verification_code`, and `resolve_signer_name`). No changes needed — do not edit this
file in this task.

- [ ] **Step 8: Verify**

Run: `python -c "import app.models.submission; import app.schemas.submission; import app.services.submission; import app.services.approval_config; import app.api.v1.submission; import app.api.v1.approval_config; import app.api.v1.public"`
Expected: exit code 0.

- [ ] **Step 9: Commit**

```bash
git add app/models/submission.py app/schemas/submission.py app/services/submission.py app/services/approval_config.py app/api/v1/submission.py app/api/v1/approval_config.py app/api/v1/public.py
git commit -m "feat(village): drop village_id from Submission/ApprovalStepConfig, single global approval chain"
```

---

### Task 7: `seed.py` — drop Village creation, seed `VillageProfile`, drop `village_id` everywhere

**Files:**
- Modify: `app/seed/seed.py`

**Interfaces:**
- Consumes: `VillageProfile` (Task 1), updated services (Tasks 3-6).
- Produces: `seed_village_profile(session)` (new, replaces the Village-creation part of
  `seed_master`), updated `seed_master` (no `Village`, no `village_id` on `Dusun`/
  `Resident`), updated `seed_letter_templates` (no `village_id` lookup or filter),
  updated `seed_approval_steps` (no `village_id`, global chain).

- [ ] **Step 1: Update imports**

Change `from app.models.master import RT, RW, Dusun, Resident, Village` to
`from app.models.master import RT, RW, Dusun, Resident, VillageProfile`.

- [ ] **Step 2: Add `seed_village_profile`, remove Village creation from `seed_master`**

Add a new function (place it before `seed_master`):

```python
async def seed_village_profile(session: AsyncSession) -> None:
    """Seed the VillageProfile singleton from VILLAGE, if it doesn't exist yet.

    Idempotent: no-op if a profile row already exists (e.g. created by the
    village_profile-table migration's data copy, or a prior seed run).
    """
    existing = await session.scalar(select(VillageProfile))
    if existing is not None:
        return
    session.add(VillageProfile(**VILLAGE))
    await session.commit()
    logger.info("seed_village_profile: created singleton profile")
```

In `seed_master`, remove the whole block that looks up/creates `Village`:
```python
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        village = Village(**VILLAGE)
        session.add(village)
        await session.flush()
```
(delete it entirely — village profile seeding now happens in the new
`seed_village_profile` function, called separately in `seed_all`).

Remove every remaining reference to `village` in `seed_master`: the `Dusun(village_id=village.id,
name=name)` call becomes `Dusun(name=name)`, and the final
`Resident(village_id=village.id, nik=nik, full_name=name, rt_id=rt.id)` call becomes
`Resident(nik=nik, full_name=name, rt_id=rt.id)`.

- [ ] **Step 3: `seed_letter_templates` — drop village lookup**

Remove:
```python
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        raise RuntimeError("seed_letter_templates requires seed_master to run first")

    existing = {
        t.code for t in (await session.scalars(
            select(LetterTemplate).where(LetterTemplate.village_id == village.id)
        )).all()
    }
```
Replace with:
```python
    existing = {
        t.code for t in (await session.scalars(select(LetterTemplate))).all()
    }
```
And remove `village_id=village.id,` from the `LetterTemplate(...)` construction further
down.

- [ ] **Step 4: `seed_approval_steps` — drop village lookup, global chain**

Remove:
```python
    village = await session.scalar(select(Village).where(Village.name == VILLAGE["name"]))
    if village is None:
        raise RuntimeError("seed_approval_steps requires seed_master to run first")

    existing_count = await session.scalar(
        select(func.count()).select_from(ApprovalStepConfig).where(
            ApprovalStepConfig.village_id == village.id
        )
    )
```
Replace with:
```python
    existing_count = await session.scalar(
        select(func.count()).select_from(ApprovalStepConfig)
    )
```
And change the loop's `ApprovalStepConfig(village_id=village.id, order_index=index,
role_id=roles[role_name].id)` to `ApprovalStepConfig(order_index=index,
role_id=roles[role_name].id)`. This function already seeds `("staff", "admin")` per
Part 1's Task 7 fix — leave that 2-role tuple as-is, only remove the village-related
code.

- [ ] **Step 5: Update `seed_all`**

```python
async def seed_all(session: AsyncSession) -> None:
    """Run all seeders: positions, RBAC/demo-users, village profile, master data,
    letter templates, demo links, default approval steps."""
    await seed_positions(session)
    await seed_rbac(session)
    await seed_village_profile(session)
    await seed_master(session)
    await seed_letter_templates(session)
    await seed_link_demo_resident(session)
    await seed_link_demo_rt_rw(session)
    await seed_approval_steps(session)
```

- [ ] **Step 6: Verify**

Run: `python -c "import app.seed.seed"`
Expected: exit code 0.

- [ ] **Step 7: Commit**

```bash
git add app/seed/seed.py
git commit -m "feat(village): seed VillageProfile singleton, drop village_id from all seeders"
```

---

### Task 8: Migration — drop `village_id` columns + `villages` table

**Files:**
- Create: `alembic/versions/<hash>_drop_village_id_and_villages.py`

**Interfaces:**
- Consumes: all model changes from Tasks 4-6 (this migration must be generated AFTER
  those model edits are committed, so autogenerate sees the target state correctly).

- [ ] **Step 1: Autogenerate**

Run: `alembic revision --autogenerate -m "drop village_id and villages table"`
Add `import app.db.base`.

- [ ] **Step 2: Review**

Confirm the generated `upgrade()` drops (in FK-safe order): the unique constraints/
indexes referencing `village_id` on `dusun`, `family_cards`, `residents`,
`letter_templates`, `submissions`, `approval_step_configs`; the `village_id` columns
themselves; then the `villages` table. Confirm it also creates the NEW unique
constraints (`uq_letter_templates_code`, `uq_approval_step_order`) from Tasks 5-6's
model changes, replacing the old `village_id`-inclusive ones.

If autogenerate's ordering would drop `villages` before all `village_id` FK columns
referencing it are dropped, manually reorder the `op.drop_table('villages')` call to
be the LAST statement in `upgrade()`.

- [ ] **Step 3: Apply to `db_kopo`**

Run: `alembic upgrade head`
Expected: no errors.

- [ ] **Step 4: Verify**

```bash
python -c "
import asyncio
from sqlalchemy import inspect
from app.db.session import engine

async def main():
    async with engine.connect() as conn:
        def check(sync_conn):
            insp = inspect(sync_conn)
            assert 'villages' not in insp.get_table_names(), 'villages table still exists'
            for table in ('dusun', 'family_cards', 'residents', 'letter_templates', 'submissions', 'approval_step_configs'):
                cols = {c['name'] for c in insp.get_columns(table)}
                assert 'village_id' not in cols, f'{table} still has village_id'
            print('OK: villages table gone, village_id dropped everywhere')
        await conn.run_sync(check)

asyncio.run(main())
"
```
(Adjust the `engine` import if `app/db/session.py` exports it under a different name —
check first.)
Expected: prints `OK: villages table gone, village_id dropped everywhere`.

- [ ] **Step 5: Commit**

```bash
git add alembic/versions/
git commit -m "feat(village): migration dropping village_id columns and villages table"
```

---

### Task 9: Fix every test broken by the Village removal

**Files:**
- Modify (as needed, discover via running the suite): `tests/test_master_models.py`,
  `tests/test_master_service.py`, `tests/test_master_data.py`, `tests/test_seed_master.py`,
  `tests/test_letter_template_models.py`, `tests/test_letter_template_service.py`,
  `tests/test_letter_template_api.py`, `tests/test_seed_letter_templates.py`,
  `tests/test_template_render.py`, `tests/test_pdf_smoke.py`,
  `tests/test_submission_models.py`, `tests/test_submission_service.py`,
  `tests/test_submission_api.py`, `tests/test_approval_config_service.py`,
  `tests/test_approval_config_api.py`, `tests/test_public_verify_api.py`,
  `tests/test_seed_submission.py`, `tests/test_excel.py`, `tests/conftest.py`

- [ ] **Step 1: Run the full suite to see the actual damage**

Run: `pytest -v 2>&1 | tail -100`

- [ ] **Step 2: Fix each failure**

The mechanical pattern for every failure will be one of:
- A test fixture constructs `Village(...)` or passes `village_id=...` to a model
  constructor — remove it (models no longer have that field/FK).
- A test asserts a response schema includes `village_id` — remove that assertion.
- A test calls a service method with a `village_id` positional/keyword argument that no
  longer exists (`ApprovalStepConfigService.list_steps`/`.replace_all`,
  `ResidentExcelService.import_bytes`) — remove the argument.
- A test posts to `/villages` or asserts on that route — replace with
  `/village-profile` (`GET`/`PUT`, not `POST`/`DELETE` — there is no create/delete for
  the singleton; if a test specifically exercised village creation/deletion, that
  capability no longer exists at all and the test should be deleted, not adapted,
  since there's nothing left to test).
- `tests/conftest.py`'s fixtures may build a `Village` row as test setup for other
  fixtures (e.g. to get a `village_id` to hand to a `Resident`/`Submission` factory) —
  remove that setup entirely, since those models no longer need it.

Do not weaken an assertion's actual intent while removing the village-related noise —
e.g. if a test was checking "creating a resident succeeds and the resident is scoped
correctly," keep checking that; only strip the village-scoping mechanics that no longer
exist.

- [ ] **Step 3: Confirm everything passes**

Run: `pytest -v`
Expected: 100% pass, 0 failures.

Run: `ruff check app tests`
Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "test(village): fix tests broken by Village removal"
```

---

### Task 10: Live verification against `db_kopo` + README update

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Re-seed live `db_kopo`**

Run: `python -m app.seed`
Expected: `Seeding complete.`

- [ ] **Step 2: Spot-check**

```bash
python -c "
import asyncio
from sqlalchemy import select
from app.db.session import AsyncSessionLocal
from app.models.master import VillageProfile, Dusun, Resident
from app.models.letter_template import LetterTemplate

async def main():
    async with AsyncSessionLocal() as s:
        profile = await s.scalar(select(VillageProfile))
        print('profile:', profile.name if profile else None)
        dusun = await s.scalar(select(Dusun).limit(1))
        print('dusun has village_id attr:', hasattr(dusun, 'village_id'))
        resident = await s.scalar(select(Resident).limit(1))
        print('resident has village_id attr:', hasattr(resident, 'village_id'))
        templates = (await s.scalars(select(LetterTemplate))).all()
        print('templates:', len(templates))

asyncio.run(main())
"
```
Expected: `profile: Desa Kopo`, both `has village_id attr` lines print `False`,
`templates: 11` (template count is unaffected by this part — the 11→8 reduction is a
different, later rework part).

- [ ] **Step 3: Update README**

In `README.md`:
- Under "## API surface (current)", change
  `GET/POST/PUT/DELETE /api/v1/villages, /dusun, /rw, /rt, /family-cards` to
  `GET/PUT /api/v1/village-profile; GET/POST/PUT/DELETE /api/v1/dusun, /rw, /rt, /family-cards`.
- Anywhere the README describes residents import/export as taking a `village_id`
  parameter, remove that description (search for "village_id" in the file and update
  each hit — there is no fixed line count to give here since the file has been edited
  by several prior sub-projects; read it fresh and fix what you find).
- Add a one-line note near the top overview paragraph (wherever the existing
  Foundation/B1/B2 summary sentence is) stating that multi-village support was removed
  per the feature-adjustment rework and the system is single-village (Desa Kopo) with a
  `VillageProfile` singleton — do not remove the existing Foundation/B1/B2 history, just
  append this fact.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: update README for multi-village removal (VillageProfile singleton)"
```
