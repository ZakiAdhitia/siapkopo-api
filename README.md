# SIPADES Backend (sipades-kopo-api)

Backend API for **SIPADES** — Sistem Administrasi Desa (Desa Kopo). Built with FastAPI,
SQLAlchemy (async), PostgreSQL, Redis, and Alembic, following Clean Architecture
(router → service → repository → model) with data-driven RBAC.

This repository currently implements the **Foundation** (infrastructure, authentication —
password + OTP login, JWT access/refresh, data-driven RBAC — and master data: village
hierarchy, residents, Excel import/export, seeding), **Sub-project B1 / Phase 4, the
Letter Template Engine**: dynamic letter templates + fields, sandboxed Jinja2/xhtml2pdf
preview rendering, and the 11 letter types seeded from the frontend's mock data, and
**Sub-project B2 / Phase 5-7**: citizen letter submissions, a village-configurable
approval chain, and automatic PDF issuance with numbering, a visual signature, and a
public no-auth QR-verification endpoint.
Multi-village support was removed per the feature-adjustment rework; the system is
now single-village (Desa Kopo) with a `VillageProfile` singleton.

## Overview

- **Router** — HTTP only, no business logic.
- **Service** — business logic.
- **Repository** — the only layer that talks to the database.
- **Response envelope** — every endpoint returns
  `{"success": bool, "message": str, "data": ..., "error_code": str|null}`.
- **RBAC** — permissions are rows in the database (`permissions`, `roles`,
  `role_permissions`), resolved per-request; there is no `if role == "..."` anywhere.

## Prerequisites

- Python 3.13+
- PostgreSQL running locally, with a database named `db_kopo` already created
  (or update `DATABASE_URL` to point at whichever database/user you use)
- Docker Desktop (used only to run Redis via `docker-compose.yml`)

## Setup

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows Git Bash; use .venv\Scripts\activate on cmd/PowerShell
pip install -e ".[dev]"
```

## Environment

Copy the template and adjust values for your machine:

```bash
cp .env.example .env
```

Key variables in `.env`:

- `DATABASE_URL` — async PostgreSQL DSN, e.g.
  `postgresql+asyncpg://postgres:<password>@localhost:5432/db_kopo`
- `REDIS_URL` — defaults to `redis://localhost:6379/0`
- `JWT_SECRET` — change for any non-local environment
- `CORS_ORIGINS` — comma-separated list; defaults to `http://localhost:5173` (the
  SIPADES frontend dev server)

## Redis

Redis backs OTP codes and the JWT access-token blacklist (used on every
authenticated request, not just OTP login), so it must be running for anything
beyond `/health` and password login to work end-to-end.

```bash
docker compose up -d redis
docker compose ps          # confirm sipades-redis is Up
```

If Docker Desktop is not running, start it first — `docker compose up` fails with
a "cannot connect to the Docker daemon" error until the desktop app is up.

## Migrations

Schema changes are managed exclusively through Alembic — never modify tables by hand.

```bash
alembic upgrade head
```

## Seeding

Seed roles, permissions, the 5 demo accounts, Desa Kopo's master data (village, 4 dusun,
RW/RT, 36 residents), the 11 letter templates (with their dynamic fields), the demo
`warga` account's link to its matching Resident row, and the default 3-step approval
chain (staf → sekretaris → kades), from `app/seed/data.py` and
`app/seed/letter_template_data.py`:

```bash
python -m app.seed
```

Prints `Seeding complete.` on success. The seeder is **idempotent** — re-running it
will not create duplicate rows (it looks up existing roles/permissions/village/dusun
by name, existing residents by NIK, existing letter templates by code, an existing
`resident_id` link on the `warga` user, and any existing `ApprovalStepConfig` rows for
the village before inserting). A fresh run creates 11 `letter_templates` rows, 32
`template_fields` rows, links `warga.resident_id` to the seeded "Siti Rohmah" resident,
and creates 3 `approval_step_configs` rows.

## Running

```bash
uvicorn app.main:app --reload
```

- API base path: `http://localhost:8000/api/v1`
- Liveness: `GET /api/v1/health`
- Readiness (checks Postgres + Redis): `GET /api/v1/health/ready`
- Interactive docs: `http://localhost:8000/docs`

## Testing

```bash
pytest
```

The test suite runs entirely against an in-memory SQLite database and a fake
in-process Redis (`fakeredis`) — no local Postgres or Redis instance is required
to run `pytest`.

Lint:

```bash
ruff check app tests
```

## Demo Accounts

Created by `python -m app.seed`. Use these against `POST /api/v1/auth/login`
(`{"username": ..., "password": ...}`) except `warga`, which authenticates via
OTP (`POST /api/v1/auth/request-otp` with the NIK below, then
`POST /api/v1/auth/verify-otp`).

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

## API surface (current)

- `POST /api/v1/auth/login`, `/request-otp`, `/verify-otp`, `/refresh`, `/logout`, `GET /me`
- `GET/PUT /api/v1/village-profile`; `GET/POST/PUT/DELETE /api/v1/dusun`, `/rw`, `/rt`, `/family-cards`
- `GET/POST/PUT/DELETE /api/v1/residents` (with `?search=&rt_id=&family_card_id=`)
- `POST /api/v1/residents/import`, `GET /api/v1/residents/export` (xlsx)
- `GET/POST/PUT/DELETE /api/v1/templates`, letter template CRUD (see Letter Templates below)
- `POST/GET /api/v1/submissions`, `GET /api/v1/submissions/{id}`,
  `POST /api/v1/submissions/{id}/attachments`, `POST /api/v1/submissions/{id}/approve`,
  `POST /api/v1/submissions/{id}/reject`, `GET /api/v1/submissions/{id}/history`,
  `GET /api/v1/submissions/{id}/pdf` (see Pengajuan, Approval & Penerbitan Surat below)
- `GET/PUT /api/v1/approval-steps` — village approval-chain configuration
- `GET /api/v1/public/verify/{code}` — no-auth public letter verification
- `GET /api/v1/health`, `GET /api/v1/health/ready`

## Letter Templates

Sub-project B1 / Phase 4 adds a dynamic letter-template engine: each letter type
(*surat*) is a `LetterTemplate` row with an ordered list of `TemplateField`s (its
dynamic form definition) and an HTML `pdf_body_template` rendered through a sandboxed
Jinja2 environment and `xhtml2pdf` (substituted for the originally-specified WeasyPrint,
which requires native GTK3/Pango/cairo libraries unavailable on this Windows dev
machine — see the plan's deviation note). No dedicated model exists per letter type;
all 11 types share the same engine and are distinguished only by their template data.

Endpoints (all under `/api/v1`, guarded by `template:manage`/`template:read`
permissions — `administrator` has both via the `*` wildcard; `staf`/`sekretaris`/`kades`
have read-only):

- `POST /templates`, `GET /templates` (paginated), `GET /templates/{id}`,
  `PUT /templates/{id}`, `DELETE /templates/{id}` — template CRUD
- `GET /templates/{id}/fields`, `POST /templates/{id}/fields`,
  `PUT /templates/{id}/fields/{field_id}`, `DELETE /templates/{id}/fields/{field_id}` —
  field CRUD (`field_key` is immutable after creation)
- `PUT /templates/{id}/fields/reorder` — bulk reorder; requires the complete, exact set
  of a template's field ids
- `GET /templates/{id}/preview` — renders and returns the template's `pdf_body_template`
  as a PDF using placeholder sample data, for reviewing layout/wording before use

The 11 seeded templates (`kk`, `domisili`, `usaha`, `sktm`, `lahir`, `mati`, `pindah`,
`datang`, `ktp`, `kkpengantar`, `keramaian`) are transcribed from the frontend's
`mockData.js` `suratTypes`, including each one's icon/colors/required documents/numbering
prefix/fields. **The redaksi (letter body) is a generic drafted Indonesian text, not
the official wording used by Desa Kopo** — it is meant as a working starting point and
is fully editable via `PUT /templates/{id}` once the real text is supplied.

Numbering (`numbering_prefix` + `numbering_pattern`, e.g.
`{prefix}/{seq}/Ds.Kopo/{year}`) was a **format definition only** as of B1; the actual
per-template, per-year counter and atomic allocation logic is implemented in B2's
letter issuance — see Pengajuan, Approval & Penerbitan Surat below.

## Pengajuan, Approval & Penerbitan Surat

Sub-project B2 (Fase 5-7) adds the full lifecycle from citizen request to issued,
verifiable letter, all reusing B1's template engine and hardened PDF pipeline — no
per-letter-type models or code paths.

Endpoints (all under `/api/v1`, guarded by `submission:*`/`approval_config:manage`
permissions):

- `POST /submissions` — a citizen (`warga`) creates a request against a `LetterTemplate`,
  with answers validated against that template's dynamic field definitions
- `GET /submissions` (paginated) — `submission:read` returns only the caller's own
  requests; `submission:read_all` (staf/sekretaris/kades/administrator) returns the
  village's requests. This distinction is why `submission:read_all` exists as a
  separate permission code rather than branching on role name.
- `GET /submissions/{id}` — single request, scoped the same way
- `POST /submissions/{id}/attachments` — upload a supporting document (size/mime
  validated, renamed to a UUID filename)
- `POST /submissions/{id}/approve`, `POST /submissions/{id}/reject` — advance or
  terminate the request. **Reject is terminal** — there is no edit/resubmit path.
  Approval turn-taking is enforced entirely by data: the acting user's `role_id` must
  match the current `ApprovalStepConfig.role_id` for that village and step index —
  never a hardcoded `if role == "..."` check. The final approval step automatically
  issues the letter: allocates a real sequential number via `LetterNumberCounter`,
  renders the final PDF (through the same hardened `TemplateRenderService`/xhtml2pdf
  pipeline B1's preview uses), and generates a verification code + QR image embedded in
  the PDF.
- `GET /submissions/{id}/history` — full status-change audit trail
- `GET /submissions/{id}/pdf` — download the issued PDF (raw bytes response, same
  pattern as B1's `/templates/{id}/preview`)
- `GET/PUT /approval-steps` — `GET` is `template:read`-guarded (staff tiers can view the
  chain); `PUT` is `approval_config:manage`-guarded (administrator only) and
  defines/replaces a village's ordered approval chain (default seeded as
  staf → sekretaris → kades, matching mockData's `SETTINGS.approvalMode='3'`). Replacing
  a chain while a
  submission is mid-flight is blocked with `409` to avoid orphaning an in-progress
  approval.
- `GET /public/verify/{code}` — **no authentication required**; resolves a letter's
  verification code (the same one encoded in its QR) to its public issuance details.
  Unknown codes return a uniform 404, revealing nothing about whether a code was ever
  valid.

**Storage:** uploaded attachments and generated PDFs are written to local disk under
`storage/` via `FileStorageService`, a small abstraction chosen so a future move to
Cloudflare R2 (or any object store) needs no call-site changes — it is not wired to any
remote store yet, per CLAUDE.md's "Object Storage ready" guidance.

**Notifications:** `notify_status_change()` is currently a stub that only logs the
event (submission created/approved/rejected/issued). Real dispatch (WhatsApp/email via
ARQ background workers) is a Phase 8 (Sub-project C) integration point, not built here.

## Roadmap: sub-projects B2/C/D

Phase 4-7 (Letter Template Engine, B1, plus Pengajuan/Approval/Penerbitan, B2 — this
repository's current state) are **done**: template + field CRUD, PDF preview, the 11
seeded letter types, citizen submissions, a configurable data-driven approval chain,
automatic numbered PDF issuance with visual signature + QR, and public no-auth
verification.

Next up is **Sub-project C (Fase 8-11)**: Notifikasi (real WhatsApp/email dispatch via
the ARQ workers the notification stub is designed to plug into), Dashboard, Portal
Desa, and Pengaduan (public complaint/report intake). These remain intentionally out of
scope here.
