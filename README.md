# SIPADES Backend (sipades-kopo-api)

Backend API for **SIPADES** — Sistem Administrasi Desa (Desa Kopo). Built with FastAPI,
SQLAlchemy (async), PostgreSQL, Redis, and Alembic, following Clean Architecture
(router → service → repository → model) with data-driven RBAC.

This repository currently implements the **Foundation** (infrastructure, authentication —
password + OTP login, JWT access/refresh, data-driven RBAC — and master data: village
hierarchy, residents, Excel import/export, seeding) and **Sub-project B1 / Phase 4, the
Letter Template Engine**: dynamic letter templates + fields, sandboxed Jinja2/xhtml2pdf
preview rendering, and the 11 letter types seeded from the frontend's mock data.

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
RW/RT, 36 residents), and the 11 letter templates (with their dynamic fields) from
`app/seed/data.py` and `app/seed/letter_template_data.py`:

```bash
python -m app.seed
```

Prints `Seeding complete.` on success. The seeder is **idempotent** — re-running it
will not create duplicate rows (it looks up existing roles/permissions/village/dusun
by name, existing residents by NIK, and existing letter templates by code before
inserting). A fresh run creates 11 `letter_templates` rows and 32 `template_fields` rows.

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

| Username   | Password       | Role                  | Notes                          |
|------------|----------------|------------------------|---------------------------------|
| `warga`    | `warga123`     | Warga                  | NIK `3516064588020003`, OTP login |
| `staf`     | `staf123`      | Staf Loket             | password login |
| `sekdes`   | `sekdes123`    | Sekretaris Desa        | password login |
| `kades`    | `kades123`     | Kepala Desa            | password login |
| `operator` | `operator123`  | Admin / Operator (`*`) | password login, full permissions |

## API surface (current)

- `POST /api/v1/auth/login`, `/request-otp`, `/verify-otp`, `/refresh`, `/logout`, `GET /me`
- `GET/POST/PUT/DELETE /api/v1/villages`, `/dusun`, `/rw`, `/rt`, `/family-cards`
- `GET/POST/PUT/DELETE /api/v1/residents` (with `?search=&rt_id=&family_card_id=`)
- `POST /api/v1/residents/import`, `GET /api/v1/residents/export` (xlsx)
- `GET/POST/PUT/DELETE /api/v1/templates`, letter template CRUD (see Letter Templates below)
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
`{prefix}/{seq}/Ds.Kopo/{year}`) is a **format definition only** in this phase — there
is no counter/allocation logic yet; that lands with B2's letter issuance (Fase 5-7).

## Roadmap: sub-projects B2/C/D

Phase 4 (Letter Template Engine — this repository's current state) is **done**: template
+ field CRUD, PDF preview, numbering format definition, and the 11 seeded letter types.

Next up is **Sub-project B2 (Fase 5-7)**: Pengajuan (citizen letter requests against
these templates), configurable Approval workflows, and PDF issuance (numbered, signed
letters generated from an approved pengajuan). Notifications (email/WhatsApp via ARQ
workers) and reporting remain planned as further follow-on sub-projects and are
intentionally out of scope here.
