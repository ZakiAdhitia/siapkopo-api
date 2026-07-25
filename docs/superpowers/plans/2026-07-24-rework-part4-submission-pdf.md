# Rework Part 4: Submission/Approval/PDF — Unsigned Documents

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Letters are issued as unsigned draft PDFs (no QR code, no digital/visual signature, no public verification), and the letter catalog shrinks from 11 to 8 types (Izin Keramaian, Pengantar KTP, Pengantar KK removed).

**Architecture:** No architectural change to the approval engine (`ApprovalStepConfig`, turn enforcement) or PDF pipeline (`TemplateRenderService` + xhtml2pdf + `FileStorageService`) — only remove the QR/signature/verification-code data and rendering, and shrink the seeded template catalog.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, xhtml2pdf, Jinja2 sandboxed env.

## Global Constraints

- Spec source of truth: `docs/superpowers/specs/2026-07-24-fitur-adjustment-rework-design.md` Bagian 2 and 5.
- Every removed symbol must be deleted, not merely unused — CLAUDE.md prohibits dead shortcuts.
- New Alembic revision only (never edit an applied revision). `import app.db.base` must be added manually after autogenerate.
- Async only, no business logic in routers, all endpoints keep a response model, UTC timestamps.
- Run `pytest` and `ruff check app tests` at the end of every task; all must pass before commit.

---

### Task 1: Letterhead + TemplateRenderService — remove QR/signature rendering

**Files:**
- Modify: `app/services/template_render.py`
- Modify: `tests/test_template_render.py`
- Modify: `tests/test_pdf_smoke.py`

**Interfaces:**
- Produces: `TemplateRenderService.render_preview(template, fields, profile) -> bytes` (unchanged signature — it never needed signer_name/qr_data_uri as caller-supplied args beyond what's removed below).
- Produces: `TemplateRenderService.render_issued(*, template, fields, profile, answers, applicant, nomor, tanggal) -> bytes` — **`signer_name` and `qr_data_uri` keyword params removed**.
- Produces: `TemplateRenderService._render_document(*, template, profile, data, nomor, tanggal) -> bytes` — same two params removed.
- Consumed by: Task 2's `SubmissionService._issue`.

- [ ] **Step 1: Update the failing tests first**

Open `tests/test_template_render.py`. Find any test that passes `signer_name=` / `qr_data_uri=` to `render_issued`/`_render_document`, or that asserts the rendered PDF/HTML contains a QR image or a signer name. Update those tests to:
  - Call `render_issued` / `_render_document` without `signer_name`/`qr_data_uri` kwargs.
  - Assert the render still succeeds (`result` is non-empty `bytes` starting with `%PDF`).
  - Remove or rewrite any assertion that specifically checked for QR image presence or a signer's name in the output (there is nothing to assert content-wise now beyond "PDF renders successfully" — xhtml2pdf output is a binary PDF stream, not raw HTML, so pre-existing tests likely already only assert byte-level things like the `%PDF` magic prefix and non-empty length; if a test asserts on the HTML fed into `pisa.CreatePDF` via a monkeypatch/mock, update that assertion to check the new letterhead text below instead of `.qr` or the old signer block).

Same treatment for `tests/test_pdf_smoke.py` — remove any `qr_data_uri`/`signer_name` args from calls into this service.

Run: `pytest tests/test_template_render.py tests/test_pdf_smoke.py -v`
Expected: FAIL (signature mismatch / TypeError: unexpected keyword argument, or AssertionError from removed content) — confirms you're editing the right call sites.

- [ ] **Step 2: Update `_LETTERHEAD` and the render methods**

In `app/services/template_render.py`, replace the `_LETTERHEAD` constant's body and `<style>` block. Remove the `.qr` CSS rule and div, and replace the `.ttd` block's signer-name line with a blank signature placeholder line, per the spec (Bagian 5):

```python
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
  .ttd .tanda-tangan-kosong { font-weight: bold; }
  .ttd .ttd-label { font-size: 10pt; margin-top: 4px; }
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
    <div class="tanda-tangan-kosong">( ......................................... )</div>
    <div class="ttd-label">Tanda Tangan &amp; Cap Basah</div>
  </div>
</body>
</html>
"""
```

Then update `_render_document`, `render_preview`, and `render_issued`:

```python
    def _render_document(
        self, *, template: LetterTemplate, profile: VillageProfile, data: dict,
        nomor: str, tanggal: str,
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
            kabupaten=profile.kabupaten or "-",
            kecamatan=profile.kecamatan or "-",
            village_name=profile.name,
            letter_title=template.name.upper(),
            nomor=nomor,
            body=body_html,
            tanggal=tanggal,
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
        self, template: LetterTemplate, fields: list[TemplateField], profile: VillageProfile
    ) -> bytes:
        """Render a PDF preview of a template using auto-generated sample data."""
        return self._render_document(
            template=template, profile=profile, data=self._sample_data(fields),
            nomor=self._preview_number(template),
            tanggal=date.today().strftime("%d %B %Y"),
        )

    def render_issued(
        self, *, template: LetterTemplate, fields: list[TemplateField], profile: VillageProfile,
        answers: dict, applicant: dict, nomor: str, tanggal: str,
    ) -> bytes:
        """Render the real issued letter using actual submission answers.

        ``fields`` is accepted (matching render_preview's signature shape)
        but not used to derive data here -- real answers/applicant data are
        passed in directly by the caller (SubmissionService), which already
        validated them against the template's fields at submission time.
        """
        data = {**applicant, **answers}
        return self._render_document(
            template=template, profile=profile, data=data, nomor=nomor, tanggal=tanggal,
        )
```

Leave `_sample_data`, `_sample_value`, `_preview_number`, `_SAMPLE_APPLICANT`, `_block_external_resources`, and the module-level docstring/constants untouched — only the pieces shown above change.

- [ ] **Step 3: Run tests to verify pass**

Run: `pytest tests/test_template_render.py tests/test_pdf_smoke.py -v`
Expected: PASS

- [ ] **Step 4: Ruff + commit**

Run: `ruff check app/services/template_render.py tests/test_template_render.py tests/test_pdf_smoke.py`
Expected: no errors.

```bash
git add app/services/template_render.py tests/test_template_render.py tests/test_pdf_smoke.py
git commit -m "feat(pdf): remove QR code and signature rendering from letterhead"
```

---

### Task 2: SubmissionService — remove signer/verification-code/QR generation

**Files:**
- Modify: `app/services/submission.py`
- Modify: `tests/test_submission_service.py`
- Modify: `tests/test_submission_api.py`

**Interfaces:**
- Consumes: Task 1's `TemplateRenderService.render_issued(*, template, fields, profile, answers, applicant, nomor, tanggal)` (no `signer_name`/`qr_data_uri`).
- Produces: `SubmissionService._issue(submission, actor)` unchanged signature, but no longer sets `submission.verification_code` (that model column is dropped in Task 4 — until Task 4's migration runs, leave the column assignment out entirely so this task's own tests pass against the current schema still having the column as nullable; the column still exists in the DB until Task 4, which is fine — an omitted nullable column write is a no-op).
- `SubmissionService.resolve_signer_name` and `SubmissionService._generate_verification_code` are **deleted** — no other file may call them after this task (verify with `grep -rn "resolve_signer_name\|_generate_verification_code" app tests`).

- [ ] **Step 1: Update the failing tests first**

In `tests/test_submission_service.py` and `tests/test_submission_api.py`: find every test that calls or mocks `resolve_signer_name`, or that asserts `submission.verification_code` is set to a non-None value after issuance, or that patches `app.services.submission.generate_qr_data_uri`. Update/remove these:
  - Remove any mock/patch of `generate_qr_data_uri` or `resolve_signer_name` (nothing to patch anymore).
  - Any assertion `submission.verification_code is not None` after issuance → remove that assertion line (the field will be fully dropped in Task 4; this task must not newly write to it, so don't replace it with an "is None" assertion here either — Task 4 removes the attribute entirely).
  - Keep all other issuance assertions (status == ISSUED, letter_number set, pdf_storage_path set, history row with action=ISSUED) unchanged.

Run: `pytest tests/test_submission_service.py tests/test_submission_api.py -v`
Expected: FAIL (AttributeError on the removed mock target, or leftover reference) — confirms the right call sites are touched.

- [ ] **Step 2: Update `app/services/submission.py`**

Remove the `import secrets` line (no longer used), remove `from app.services.qr import generate_qr_data_uri`, remove the `resolve_signer_name` method entirely, remove the `_generate_verification_code` method entirely. Update `_issue`:

```python
    async def _issue(self, submission: Submission, actor: User) -> None:
        """Allocate a real number, render the final PDF, and mark ISSUED."""
        template = await self.template_repo.get(submission.template_id)
        fields = await self._list_template_fields(submission.template_id)
        village = await VillageProfileService(self.session).get()
        submitter = await self.session.get(User, submission.submitted_by_user_id)
        applicant = await self.resolve_applicant_data(submitter)

        year = datetime.now(timezone.utc).year
        seq = await LetterNumberService(self.session).allocate(submission.template_id, year)
        letter_number = template.numbering_pattern.format(
            prefix=template.numbering_prefix, seq=seq, year=year
        )
        tanggal = datetime.now(timezone.utc).strftime("%d %B %Y")

        pdf_bytes = TemplateRenderService().render_issued(
            template=template, fields=fields, profile=village,
            answers=submission.answers, applicant=applicant, nomor=letter_number,
            tanggal=tanggal,
        )
        storage_path = await FileStorageService().save(
            pdf_bytes, f"{submission.id}.pdf", subdir="issued"
        )

        submission.status = SubmissionStatus.ISSUED
        submission.letter_number = letter_number
        submission.pdf_storage_path = storage_path
        submission.issued_at = datetime.now(timezone.utc)
        self.session.add(SubmissionStatusHistory(
            submission_id=submission.id, step_index=submission.current_step_index,
            action=HistoryAction.ISSUED, actor_user_id=actor.id, note=None,
        ))
        logger.info(
            "Submission issued id=%s letter_number=%s", submission.id, letter_number,
        )
```

Also remove the now-unused `get_settings` import if nothing else in the file uses it (check with `grep -n "get_settings" app/services/submission.py` — it was only used for `public_verify_base_url`).

- [ ] **Step 3: Run tests to verify pass**

Run: `pytest tests/test_submission_service.py tests/test_submission_api.py -v`
Expected: PASS

- [ ] **Step 4: Ruff + commit**

Run: `ruff check app/services/submission.py tests/test_submission_service.py tests/test_submission_api.py`
Expected: no errors.

```bash
git add app/services/submission.py tests/test_submission_service.py tests/test_submission_api.py
git commit -m "feat(submission): remove signer/verification-code/QR generation from issuance"
```

---

### Task 3: Delete QR module, public-verify endpoint, and the `qrcode` dependency

**Files:**
- Delete: `app/services/qr.py`
- Delete: `app/api/v1/public.py`
- Delete: `tests/test_qr_helper.py`
- Delete: `tests/test_qr_smoke.py`
- Delete: `tests/test_public_verify_api.py`
- Modify: `app/api/v1/__init__.py`
- Modify: `app/schemas/submission.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `api_router` (in `app/api/v1/__init__.py`) with the `public` router no longer included — no route at `GET /public/verify/{code}` exists anywhere after this task.
- Produces: `app.schemas.submission` no longer exports `PublicVerifyRead`; `SubmissionRead` no longer has a `verification_code` field.

- [ ] **Step 1: Confirm nothing else references what's being deleted**

Run: `grep -rn "verification_code\|qr_data_uri\|generate_qr_data_uri\|PublicVerifyRead\|app\.services\.qr\|api\.v1\.public\|app\.api\.v1 import.*public" app tests --include="*.py"`

Expected at this point (after Tasks 1-2): only these remaining hits, all of which this task removes:
- `app/api/v1/public.py` (the whole file, being deleted)
- `app/api/v1/__init__.py`'s import/registration of `public`
- `app/schemas/submission.py`'s `PublicVerifyRead` class and `SubmissionRead.verification_code` field
- `app/models/submission.py`'s `Submission.verification_code` column (left for Task 4 — the DB column drop is a schema migration, out of scope here; only remove it from the Pydantic **read** schema now, not the SQLAlchemy model)
- The three test files listed under Delete above

If anything else shows up, stop and re-read Tasks 1-2's diffs before proceeding — do not delete a call site whose caller you haven't verified is otherwise dead.

- [ ] **Step 2: Delete the dead files**

```bash
git rm app/services/qr.py app/api/v1/public.py tests/test_qr_helper.py tests/test_qr_smoke.py tests/test_public_verify_api.py
```

- [ ] **Step 3: Update `app/api/v1/__init__.py`**

```python
"""Aggregate all v1 routers."""
from fastapi import APIRouter

from app.api.v1 import approval_config, auth, health, letter_template, master, submission

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(master.router)
api_router.include_router(letter_template.router)
api_router.include_router(approval_config.router)
api_router.include_router(submission.router)
```

- [ ] **Step 4: Update `app/schemas/submission.py`**

Remove the `PublicVerifyRead` class entirely, and remove the `verification_code: str | None = None` line from `SubmissionRead`.

- [ ] **Step 5: Update `pyproject.toml`**

Remove the `"qrcode>=7.4",` line from `[project].dependencies`.

- [ ] **Step 6: Run the full suite**

Run: `pytest -v`
Expected: PASS (no collection errors from the deleted test files; no import errors from the removed router/schema).

- [ ] **Step 7: Uninstall the now-unlisted package and verify the app still imports**

```bash
pip uninstall -y qrcode
python -c "import app.main; app.main.create_app()"
```
Expected: no `ImportError`, the app factory builds successfully (proves nothing else transitively imports `qrcode`).

- [ ] **Step 8: Ruff + commit**

Run: `ruff check app tests`
Expected: no errors.

```bash
git add app/api/v1/__init__.py app/schemas/submission.py pyproject.toml
git commit -m "chore(pdf): remove QR module, public-verify endpoint, and qrcode dependency"
```

---

### Task 4: Reduce letter catalog 11→8 + drop `verification_code` column (Alembic)

**Files:**
- Modify: `app/seed/letter_template_data.py`
- Modify: `app/models/submission.py`
- Create: `alembic/versions/<hash>_drop_verification_code_soft_delete_templates.py`
- Modify: `tests/test_seed_letter_templates.py`
- Check: `tests/test_seed_submission.py`, `tests/test_letter_template_service.py`, `tests/test_letter_template_api.py`, `tests/test_letter_template_models.py` (grep for `keramaian`, `"ktp"`, `kkpengantar`, or a hardcoded `11` template count)

**Interfaces:**
- Produces: `SURAT_TEMPLATES` (in `app/seed/letter_template_data.py`) with exactly 8 entries: `kk`, `domisili`, `usaha`, `sktm`, `lahir`, `mati`, `pindah`, `datang`.
- Produces: `app.models.submission.Submission` with no `verification_code` column/attribute at all.

- [ ] **Step 1: Remove the 3 retired templates from seed data**

In `app/seed/letter_template_data.py`, delete the three dict entries whose `"code"` is `"ktp"`, `"kkpengantar"`, and `"keramaian"` from the `SURAT_TEMPLATES` list. Leave the remaining 8 entries (`kk`, `domisili`, `usaha`, `sktm`, `lahir`, `mati`, `pindah`, `datang`) exactly as they are — do not reorder or edit their content.

- [ ] **Step 2: Update tests that assert the template catalog**

Run: `grep -rn "keramaian\|kkpengantar\|len(SURAT_TEMPLATES)\|== 11\b" tests --include="*.py"`

For each hit in `tests/test_seed_letter_templates.py` (and any other file the grep surfaces): update counts from 11 to 8, and remove any test case that specifically exercises the `keramaian`/`ktp`/`kkpengantar` codes (replace with one of the 8 remaining codes if the test's intent — e.g. "seeding is idempotent" — still needs *a* code to exercise, use `"kk"`).

Run: `pytest tests/test_seed_letter_templates.py -v`
Expected: FAIL at this point if the test file still hardcodes 11 or references a removed code — confirms you found the right assertions before moving on.

- [ ] **Step 3: Remove `verification_code` from the `Submission` model**

In `app/models/submission.py`, delete this block from the `Submission` class:
```python
    verification_code: Mapped[str | None] = mapped_column(
        String(50), unique=True, nullable=True
    )
```
Check whether `String` is still used elsewhere in the file after this removal (`grep -n "String(" app/models/submission.py`) — if not, remove `String` from the `sqlalchemy` import line too.

- [ ] **Step 4: Generate and hand-edit the Alembic migration**

```bash
alembic revision --autogenerate -m "drop verification_code, soft-delete retired letter templates"
```

Open the generated file. It must do three things, all inside a single revision. Add `import app.db.base` near the top (autogenerate never adds this, and the migration will fail to find custom types without it — follow the exact pattern used in `alembic/versions/f075dda45d7f_drop_village_id_and_villages_table.py`). Autogenerate will produce the `drop_column` for `verification_code`; it will produce nothing for the data soft-delete (write that by hand). Structure `upgrade()`/`downgrade()` like this:

```python
"""drop verification_code, soft-delete retired letter templates

Revision ID: <generated>
Revises: f075dda45d7f
Create Date: <generated>

"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

import app.db.base  # noqa: F401 -- registers custom types (GUID) for reflection

# revision identifiers, used by Alembic.
revision = "<generated>"
down_revision = "f075dda45d7f"
branch_labels = None
depends_on = None

_RETIRED_CODES = ("ktp", "kkpengantar", "keramaian")


def upgrade() -> None:
    conn = op.get_bind()
    now = datetime.now(timezone.utc)

    letter_templates = sa.table(
        "letter_templates",
        sa.column("id", sa.String()),
        sa.column("code", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    template_fields = sa.table(
        "template_fields",
        sa.column("template_id", sa.String()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )

    retired_ids = [
        row[0] for row in conn.execute(
            sa.select(letter_templates.c.id).where(letter_templates.c.code.in_(_RETIRED_CODES))
        )
    ]

    if retired_ids:
        conn.execute(
            letter_templates.update()
            .where(letter_templates.c.id.in_(retired_ids))
            .values(is_active=False, deleted_at=now)
        )
        conn.execute(
            template_fields.update()
            .where(template_fields.c.template_id.in_(retired_ids))
            .values(deleted_at=now)
        )

    op.drop_column("submissions", "verification_code")


def downgrade() -> None:
    op.add_column(
        "submissions",
        sa.Column("verification_code", sa.String(length=50), nullable=True),
    )
    op.create_unique_constraint(
        "uq_submissions_verification_code", "submissions", ["verification_code"]
    )

    conn = op.get_bind()
    letter_templates = sa.table(
        "letter_templates",
        sa.column("id", sa.String()),
        sa.column("code", sa.String()),
        sa.column("is_active", sa.Boolean()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    template_fields = sa.table(
        "template_fields",
        sa.column("template_id", sa.String()),
        sa.column("deleted_at", sa.DateTime(timezone=True)),
    )
    retired_ids = [
        row[0] for row in conn.execute(
            sa.select(letter_templates.c.id).where(letter_templates.c.code.in_(_RETIRED_CODES))
        )
    ]
    if retired_ids:
        conn.execute(
            template_fields.update()
            .where(template_fields.c.template_id.in_(retired_ids))
            .values(deleted_at=None)
        )
        conn.execute(
            letter_templates.update()
            .where(letter_templates.c.id.in_(retired_ids))
            .values(is_active=True, deleted_at=None)
        )
```

Check the actual column name/type autogenerate infers for `letter_templates.id`/`template_fields.template_id` against `app/models/letter_template.py` (they use the project's custom `GUID()` type, not plain `String`) — if the reflected `sa.table()` column types autogenerate would use differ, match whatever `f075dda45d7f`'s existing `sa.table()` blocks used for the same columns (copy that pattern verbatim for consistency; the exact column Python type in a throwaway `sa.table()` reflection doesn't affect correctness for an UPDATE, but match house style).

If retired templates haven't been seeded yet in a given environment (e.g. a fresh test DB), `retired_ids` is simply empty and the updates are no-ops — this is safe and expected.

- [ ] **Step 5: Run the full suite against a real migration**

Run: `alembic upgrade head`
Expected: migration applies cleanly against the local `db_kopo` database (or the project's configured test/dev DB).

Run: `pytest -v`
Expected: all tests PASS (SQLite test DB path uses `Base.metadata.create_all`, not Alembic, so this also exercises the model-level `verification_code` removal independently of the migration).

- [ ] **Step 6: Ruff + commit**

Run: `ruff check app tests alembic`
Expected: no errors.

```bash
git add app/seed/letter_template_data.py app/models/submission.py tests/test_seed_letter_templates.py alembic/versions/
git commit -m "feat(letters): reduce catalog to 8 types, drop verification_code column"
```

If Step 2's grep surfaced hits in other test files (`test_seed_submission.py`, `test_letter_template_service.py`, `test_letter_template_api.py`, `test_letter_template_models.py`), include those files in this same commit with the same treatment (remove/replace references to the 3 retired codes; do not hardcode an 11-count anywhere).

---

## Notes for the controller (not part of any task)

- This part does NOT touch `app/services/notification.py` (`notify_status_change` stays a stub — Part 7 wires the real notification system).
- This part does NOT touch approval-chain step count (already 2-step from Part 1's spec-alignment seed data) or `ApprovalStepConfigService`.
- Live-DB smoke verification and README updates for this part are deferred to the end-of-branch review the user requested, not done per-part.
