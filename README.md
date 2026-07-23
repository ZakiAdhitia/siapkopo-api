# SIPADES Backend (sipades-kopo-api)

Backend API for **SIPADES** — Sistem Administrasi Desa (Desa Kopo). Built with FastAPI,
SQLAlchemy (async), PostgreSQL, Redis, and Alembic, following Clean Architecture
(router → service → repository → model) with data-driven RBAC.

This repository currently implements the **Foundation**: infrastructure, authentication
(password + OTP login, JWT access/refresh, data-driven RBAC), and master data
(village hierarchy, residents, Excel import/export, seeding).

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

Seed roles, permissions, the 5 demo accounts, and Desa Kopo's master data
(village, 4 dusun, RW/RT, 36 residents) from `app/seed/data.py`:

```bash
python -m app.seed
```

Prints `Seeding complete.` on success. The seeder is **idempotent** — re-running it
will not create duplicate rows (it looks up existing roles/permissions/village/dusun
by name and existing residents by NIK before inserting).

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
- `GET /api/v1/health`, `GET /api/v1/health/ready`

## Roadmap: sub-projects B/C/D

Letters (surat) with dynamic templates/forms/PDF/numbering, configurable approval
workflows, notifications (email/WhatsApp via ARQ workers), and reporting are
**not implemented yet** — they are planned as follow-on sub-projects on top of this
Foundation and are intentionally out of scope here.
