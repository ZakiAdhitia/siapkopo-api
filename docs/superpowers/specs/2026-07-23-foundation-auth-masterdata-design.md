# Design Spec — SIPADES Backend, Sub-project A: Foundation

**Tanggal:** 2026-07-23
**Ruang lingkup:** Fase 1 (Infrastructure), Fase 2 (Authentication), Fase 3 (Master Data)
**Status:** Disetujui (design), menunggu implementation plan
**Repo:** `sipades-kopo-api`

---

## 1. Konteks & Keputusan

SIPADES adalah sistem administrasi desa. Frontend (`sipades-kopo-client`, React + Vite)
sudah selesai sebagai prototipe yang **sepenuhnya berjalan di atas mock data**
(`src/data/mockData.js`) tanpa ada pemanggilan API. Konsekuensinya: mock data itu
adalah **kontrak** — ia mendefinisikan bentuk data yang harus dihasilkan backend.

Total pekerjaan backend adalah 16 fase (Task.md), diperkirakan 10–14 minggu. Karena
terlalu besar untuk satu spec, pekerjaan didekomposisi menjadi 4 sub-project. Dokumen
ini hanya mencakup **Sub-project A (Foundation)**.

### Dekomposisi keseluruhan (referensi)

| Sub-project | Fase | Alasan pengelompokan |
|---|---|---|
| **A. Foundation** | 1, 2, 3 | Infra + Auth + Master Data — fondasi semua fitur. |
| **B. Letter Engine** | 4, 5, 6, 7 | Template → Submission → Approval → PDF. Inti produk. |
| **C. Engagement** | 8, 9, 10, 11 | Notifikasi, Dashboard, Portal Desa, Pengaduan. |
| **D. Hardening** | 12, 13, 14, 15, 16 | Reporting, Audit, Optimization, Security, Testing. |

### Keputusan runtime & lingkungan

- **PostgreSQL:** sudah berjalan di lokal milik pengguna. Backend hanya butuh `.env`
  berisi kredensial koneksi.
- **Redis:** belum ada. Disediakan `docker-compose.yml` yang **hanya** menjalankan Redis,
  sehingga tidak perlu instalasi native.
- **OTP:** disimpan di Redis (TTL). Pada mode dev, kode OTP dikembalikan/di-log; pengiriman
  WhatsApp asli ditunda ke Fase 8 melalui interface notifier yang pluggable.
- **Seeding:** akun demo dan master data di-seed dari `mockData.js` agar frontend bisa
  login & berfungsi tanpa perubahan.

---

## 2. Arsitektur & Struktur Proyek

Clean Architecture, async-first. Alur request: **router → service → repository → model**.
Pydantic v2 di tepi (request/response), Dependency Injection untuk session/current-user/permission.

```
sipades-kopo-api/
  app/
    main.py                 # app factory: mount router, middleware, exception handler
    core/                   # config (pydantic-settings), security (jwt/hash), logging,
                            #   exceptions, response envelope, redis client
    db/                     # async engine, session, declarative base
    models/                 # SQLAlchemy 2.0 (UUID PK, soft-delete, UTC timestamps)
    schemas/                # Pydantic v2 request/response
    repositories/           # SATU-SATUNYA tempat akses DB
    services/               # SATU-SATUNYA tempat business logic
    api/v1/                 # router saja — tanpa logic
    dependencies/           # DI: get_db, get_current_user, pagination
    permissions/            # registry RBAC + require_permission()
    middleware/             # request-id, logging
    workers/                # setup ARQ (dipakai mulai Fase 8; disiapkan sekarang)
    utils/                  # excel, pagination helper
  alembic/                  # migrasi — satu-satunya sumber perubahan skema
  tests/                    # pytest-asyncio + httpx
  docker-compose.yml        # Redis only
  .env.example
  pyproject.toml
```

### Tech stack

Python 3.13, FastAPI, SQLAlchemy 2.0 async + `asyncpg`, Alembic, Pydantic v2 +
`pydantic-settings`, PyJWT, `passlib[bcrypt]`, `redis` (async), `openpyxl`, ARQ,
`pytest` + `pytest-asyncio` + `httpx`.

### Konvensi lintas modul

- **PK:** UUID v4 di semua tabel.
- **Timestamps:** `created_at`, `updated_at` (UTC, timezone-aware).
- **Soft delete:** kolom `deleted_at` (nullable). Query default mengecualikan yang terhapus.
- **Multi-tenant ready:** kolom `village_id` (FK) pada tabel yang relevan. Satu desa di-seed
  sekarang (Desa Kopo), tanpa mengubah arsitektur ke depan.
- **Response envelope (global, konsisten):**
  - Sukses: `{ "success": true, "message": "...", "data": {...} }`
  - Error: `{ "success": false, "message": "...", "error_code": "...", "data": null }`
- **Pagination:** query `page`, `size`; respons menyertakan `total`, `page`, `size`, `items`.
- **Type hint + docstring + logger** di semua modul (Coding Standards CLAUDE.md).

---

## 3. Fase 1 — Infrastructure

**Deliverable:** backend dapat dijalankan dan terkoneksi database.

Cakupan:

- App factory FastAPI + versioning `/api/v1`.
- Konfigurasi via `pydantic-settings` (baca `.env`).
- Async engine SQLAlchemy + session dependency (`get_db`).
- Setup Alembic (env async) + migrasi awal.
- Redis client (async) di `core`.
- Logger terstruktur + middleware request-id.
- Exception handler global → envelope error (tidak pernah bocorkan traceback).
- CORS untuk client Vite (`http://localhost:5173` default, dari config).
- Health endpoint: `GET /api/v1/health` (cek app), `GET /api/v1/health/ready`
  (cek koneksi Postgres + Redis).
- `docker-compose.yml` (Redis) + `.env.example`.

**Kriteria selesai Fase 1:** `uvicorn app.main:app` menyala, `/health` 200,
`/health/ready` melaporkan Postgres & Redis OK setelah `docker compose up -d redis`.

---

## 4. Fase 2 — Authentication

**Deliverable:** login (password & OTP), refresh, logout, me; RBAC data-driven.

### Model

- `Role` — id, name (unik), display_name, description.
- `Permission` — id, code (unik, mis. `resident:create`), description.
- `role_permissions` — M2M Role↔Permission.
- `User` — id, username (unik, nullable utk warga murni?), nik (unik, nullable),
  full_name, hashed_password (nullable utk warga OTP-only), phone, role_id (FK),
  resident_id (FK, nullable), is_active, timestamps, soft-delete.
- `RefreshToken` — id, user_id (FK), token_hash, expires_at, revoked_at, created_at.
  (Refresh token disimpan ter-hash; rotasi saat refresh.)
- **OTP** & **blacklist access-token (jti)** → Redis (TTL), bukan Postgres.

### Endpoint (`/api/v1/auth`)

| Method | Path | Fungsi |
|---|---|---|
| POST | `/auth/login` | Login staf: username + password (bcrypt). |
| POST | `/auth/request-otp` | Warga: input NIK → generate & kirim OTP (dev: return/log). |
| POST | `/auth/verify-otp` | Warga: NIK + kode → terbitkan token. |
| POST | `/auth/refresh` | Rotasi refresh token → access baru. |
| POST | `/auth/logout` | Blacklist access jti + revoke refresh. |
| GET | `/auth/me` | Identitas + daftar permission user aktif. |

### Aturan

- JWT **access** (pendek) + **refresh** (panjang). Access memuat `sub`, `jti`, `role`,
  `permissions` (atau ambil dari cache). `jti` dicek terhadap blacklist Redis tiap request.
- **RBAC data-driven:** endpoint dijaga `require_permission("...")`. **Dilarang**
  `if role == "..."` (aturan keras CLAUDE.md). Permission dievaluasi dari relasi
  Role→Permission di DB.
- **Seed role & akun** dari `mockData.js`:
  - Role: Warga, Staf, Sekretaris, Kepala Desa, Administrator.
  - Akun demo: `warga/warga123`, `staf/staf123`, `sekdes/sekdes123`, `kades/kades123`,
    `operator/operator123` (password akan di-bcrypt; hanya untuk dev/seed).

**Kriteria selesai Fase 2:** kelima akun demo dapat login, alur OTP warga berjalan
(dev-mode), refresh & logout berfungsi, `/auth/me` mengembalikan permission sesuai role,
endpoint terproteksi menolak tanpa permission.

---

## 5. Fase 3 — Master Data

**Deliverable:** CRUD master data kependudukan lengkap dengan pagination/filter/search
dan import/export Excel.

### Model & hierarki

`Village → Dusun → RW → RT`, ditambah `FamilyCard (KK)` dan `Resident (Penduduk)`.

- `Village` — id, name, slogan, kecamatan, kabupaten, provinsi, dst.
- `Dusun` — id, village_id (FK), name.
- `RW` — id, dusun_id (FK), number.
- `RT` — id, rw_id (FK), number.
- `FamilyCard` — id, village_id, kk_number (unik), head_resident_id (nullable), address.
- `Resident` — id, village_id, nik (unik), full_name, family_card_id (FK), rt_id (FK),
  gender, birth_place, birth_date, occupation, phone, address, timestamps, soft-delete.

Semua tabel membawa `village_id` (langsung atau via relasi induk).

### Endpoint

Per modul (village, dusun, rw, rt, family-card, resident): **CRUD** dengan
**pagination + filter + search**, `response_model` wajib. Untuk `resident`:

- `POST /api/v1/residents/import` — import Excel (`openpyxl`), validasi baris,
  laporan error per baris. (Sinkron dulu; dapat dipindah ke ARQ nanti.)
- `GET /api/v1/residents/export` — export Excel sesuai filter.

### Seeding

Dari `mockData.js`: dusun (Krajan, Sumber, Ngemplak, Kopo Wetan), RT/RW, dan 36 resident.

**Kriteria selesai Fase 3:** CRUD keenam modul berjalan + tervalidasi, pagination/filter/
search berfungsi, import & export Excel resident berhasil (termasuk laporan error import).

---

## 6. Lintas-cutting & Testing

- **Exception khusus** → handler global → envelope error. Tidak ada traceback ke client.
- **Logging** aktivitas penting (login, logout, delete, import, export, error) — pondasi
  audit log penuh di Fase 13.
- **Alembic** satu-satunya jalur perubahan skema; dilarang DDL manual.
- **Testing:** `pytest-asyncio` + `httpx.AsyncClient` terhadap test DB.
  - Unit test service (auth, RBAC, resident).
  - Integration test endpoint auth (5 akun, OTP, refresh, logout, me) & master data
    (CRUD, pagination, import/export).

**Definition of Done Sub-project A:** app boot → connect ke Postgres lokal → migrasi apply →
5 akun demo terautentikasi → CRUD + import/export master data jalan → test hijau.

---

## 7. Alur Multi-agent (implementasi)

Setelah spec disetujui: tulis implementation plan (skill `writing-plans`), lalu dispatch
**subagent independen** per irisan bertepi jelas (mis. *core-infra*, *auth*, *master-data*),
masing-masing mengikuti TDD, dengan checkpoint review sebelum integrasi. Ini memenuhi
permintaan "multi-agent workflow per task" sambil menjaga tiap bagian terisolasi & mudah
direview.

## 8. Di luar cakupan (ditunda ke sub-project berikutnya)

- Template surat & dynamic form engine (B/Fase 4).
- Pengajuan, workflow approval, generate PDF, QR (B/Fase 5–7).
- Notifikasi WhatsApp/email asli, dashboard, portal, pengaduan (C).
- Reporting, audit log penuh, cache/optimisasi, rate limit & security hardening, testing
  menyeluruh (D).
