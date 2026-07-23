# Bundle F Report — Master-Data Seeding, Seed CLI, Full Verification (Tasks 19-21)

## Status: DONE

## Commits
- `d8752c0` feat(master): seed village/dusun/rt/residents from mockData (Task 19)
- `8bacb37` feat(seed): CLI entrypoint for database seeding (Task 20)
- `bdfa0cc` docs: backend run guide + foundation verification (Task 21)

## Files touched

### Task 19
- `app/seed/data.py` (new) — `VILLAGE`, `DUSUN` (4 names), `RESIDENTS` (36 tuples
  `(nik_suffix, name, kk_suffix, dusun, rt, rw)`), copied verbatim from the plan
  (already extracted from the frontend `mockData.js`).
- `app/seed/seed.py` — added `seed_master(session)`: creates the Desa Kopo village
  singleton (lookup by name), the 4 dusun (lookup by name), then RW/RT built lazily
  and cached by `(dusun_name, rw_no)` / `(rw.id, rt_no)`, then 36 residents with
  synthetic NIK `3516` + zero-padded suffix (deliberately distinct from the demo
  `warga` user NIK `3516064588020003` — not touched). Idempotency guard: existing
  resident NIKs are loaded once and any row already present is skipped. `seed_all`
  now runs `seed_rbac` then `seed_master`. Added a module logger (`get_logger("seed")`)
  with one INFO line per seeder summarizing counts, matching the logging convention
  already used in `services/master.py` and `services/auth.py`.
- `tests/test_seed_master.py` (new) — 2 tests: first run creates 1 village / 4 dusun /
  36 residents; running `seed_master` twice leaves the same counts (idempotency).

### Task 20
- `app/seed/__main__.py` (new) — `python -m app.seed` opens an `AsyncSessionLocal`,
  runs `seed_all`, logs and prints `"Seeding complete."`. Calls `configure_logging()`
  first so seeding output is visible when run as a script.

### Task 21
- `README.md` (rewritten from the 1-line stub) — Overview, Prerequisites, Setup,
  Environment, Redis, Migrations, Seeding, Running, Testing, Demo Accounts table,
  current API surface, and a "Roadmap: sub-projects B/C/D" note for
  letters/approval/notifications (explicitly out of scope for this Foundation).

## Test results
- `pytest -q tests/test_seed_master.py` → **2 passed**.
- Full suite `pytest -q` → **50 passed**, 0 failed (48 baseline from Bundle E + 2 new
  seed-master tests = 50, matches). Runs entirely on SQLite + fakeredis, no external
  services required.
- `ruff check app tests` → **All checks passed.**

## Live `db_kopo` seed verification (real PostgreSQL 18.4, `alembic upgrade head` already at `ab51fdb6e0f1`)

Counts queried directly via SQLAlchemy against the live DB (not the API, to avoid
conflating with the Redis-dependent blacklist check — see Concerns below).

| Stage | users | residents | villages | dusun | rw | rt |
|---|---|---|---|---|---|---|
| Before (empty DB) | 0 | 0 | 0 | 0 | — | — |
| After `python -m app.seed` (1st run) | **5** | **36** | 1 | 4 | 4 | 16 |
| After `python -m app.seed` (2nd run, idempotency check) | **5** | **36** | 1 | 4 | 4 | 16 |

Second run's SQL log shows only `SELECT`s for the village/dusun/resident lookups and
zero `INSERT` statements — confirming idempotency at the SQL level, not just via
final counts. The 5 demo usernames present: `kades, operator, sekdes, staf, warga`.

## Live HTTP smoke (uvicorn against `db_kopo`, port 8811, no auto-reload)
- `GET /api/v1/health` → 200, `{"success":true,"data":{"status":"ok"}}`.
- `POST /api/v1/auth/login` (`operator`/`operator123`) → 200, valid JWT pair returned.
  Login itself does not touch Redis (only refresh-token persistence, which is DB-only).
- `GET /api/v1/health/ready` → 503 `{"database":true,"redis":false}` — correct,
  degraded-but-truthful readiness reporting since Redis is down.
- `GET /api/v1/residents` (with the operator's Bearer token) → **500** — traced to
  `get_current_user` → `AuthService.is_blacklisted()` calling `self.redis.get(...)`
  on every authenticated request (the JTI-blacklist check from Task 10/13), which
  raises `redis.exceptions.ConnectionError` when Redis is unreachable. This is
  expected given Redis/Docker is down in this environment (not a code defect — the
  blacklist-on-every-request design is correct and was approved in Bundle C review);
  documented in the README's Redis section ("must be running for anything beyond
  `/health` and password login") so it's not mistaken for a bug later. Server process
  was stopped after the smoke test.

## Redis / Docker (expected-down, not a blocker)
- `docker compose up -d redis` → fails: `unable to get image 'redis:7-alpine': ...
  npipe:////./pipe/dockerDesktopLinuxEngine ... The system cannot find the file
  specified.` — Docker Desktop's daemon is down, exactly as flagged in the task
  brief. Not retried further. README's Redis section tells the user to start Docker
  Desktop, then `docker compose up -d redis`, then `uvicorn app.main:app --reload`.

## Deviations from the plan text
1. `seed.py`'s existing `seed_rbac` (pre-dating this bundle, from Bundle B/C review
   fixes) already differed from the plan snippet by making the `"*"` wildcard a real
   DB `Permission` row instead of a static-registry short-circuit — left untouched,
   `seed_master` was added alongside it without altering that behavior.
2. Added a `seed` logger with one summary INFO line per seeder (not present in the
   plan's Task 19/20 code) — for consistency with `services/master.py` and
   `services/auth.py`'s existing logging convention and CLAUDE.md's "Semua aktivitas
   penting harus dicatat" rule; does not log any PII (only counts).
3. `test_seed_master.py` has 2 tests instead of the plan's 1 (added a "first run
   creates the right shape" test in addition to the idempotency test) — additive only.
4. README is substantially more complete than the plan's minimal outline (added a
   Demo Accounts table, current API surface list, and Redis blacklist-dependency
   note) — all within Task 21 Step 3's brief ("concrete, correct, copy-pasteable").

## Concerns
- None blocking the Foundation bundle. The one real finding — authenticated
  endpoints 500 instead of degrading gracefully when Redis is unreachable mid-request
  (only `/health/ready` degrades gracefully) — is a pre-existing architectural
  property from Bundle C (blacklist check is intentionally hard-required for security:
  a logged-out/blacklisted token must not silently pass if Redis is down permissively).
  Not fixed here per the task brief's instruction not to treat Redis/Docker-down as a
  blocker; noted here and in the README for whoever operates this in production
  (Redis should be deployed as a required, monitored dependency, not optional).

## Final-review fixes

Three whole-branch code-review findings fixed on `feat/foundation`:

### IMPORTANT #1 — Excel import transaction poisoning
`app/services/excel.py::import_bytes` wraps each row's validation + insert in
`async with self.session.begin_nested():` (a SAVEPOINT). A DB-level failure on
one row (e.g. duplicate NIK triggering `IntegrityError` on `Resident.nik`'s
unique constraint) now rolls back only that row's SAVEPOINT; prior and later
valid rows still flush and the final `await self.session.commit()` persists
all successful rows. The pre-existing `ValueError` validation path (missing
nik/full_name) is unchanged and still lands in `errors`, now also inside the
nested transaction so it stays consistent with the DB-error path.
Test: `tests/test_excel.py::test_import_duplicate_nik_isolated_by_savepoint`
— 3-row workbook where row 2 duplicates row 1's NIK; asserts `imported == 2`,
row 2 reported in `errors`, no exception propagates, and exactly the 2 unique
NIKs are persisted.

### IMPORTANT #2 — DB constraint violations must return 409, not 500
`app/main.py::create_app` registers a global
`@app.exception_handler(IntegrityError)` (from `sqlalchemy.exc`) returning
HTTP 409 with `error_code="CONFLICT"` and a logged warning, ahead of the
catch-all `Exception` handler. This covers all six master-data services'
single-record `create`/`update` paths (and the excel importer's outer
`commit()`) without per-service changes.
Test: `tests/test_master_data.py::test_resident_create_duplicate_nik_returns_409`
— as `operator`, creates a village + resident, then POSTs a second resident
with the same NIK; asserts HTTP 409 and `error_code == "CONFLICT"`.

### MINOR — guard the default JWT secret in production
`app/main.py::create_app` now checks `settings.jwt_secret` against
`{"change-me", "change-me-in-production"}` right after loading settings: if
`settings.app_env == "production"` it raises `RuntimeError` before the
`FastAPI` app is even constructed; otherwise it logs a warning and continues
(so `development`/test defaults are unaffected).
Test: `tests/test_core.py::test_create_app_rejects_default_jwt_secret_in_production`
— monkeypatches `APP_ENV=production`, clears `JWT_SECRET` (falls back to the
insecure default), clears `get_settings` cache, and asserts `create_app()`
raises `RuntimeError` matching `"JWT_SECRET"`; clears the cache again in a
`finally` so later tests re-resolve settings from the restored environment.

### Verification
- `pytest tests/test_excel.py tests/test_master_data.py tests/test_core.py -v` → 18 passed
- `pytest -q` (full suite) → 53 passed
- `ruff check app tests` → All checks passed
