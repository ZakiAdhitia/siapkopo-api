# Ringkasan Rework `feat/fitur-adjustment-rework` (Part 1-9)

> Ditulis otomatis setelah seluruh Part 1-9 selesai diimplementasikan, sesuai instruksi:
> selesaikan semua dulu, baru rangkum, baru lakukan pengecekan menyeluruh bersama.

**Branch:** `feat/fitur-adjustment-rework` (lokal, belum di-push ke `origin`)
**Base:** `feat/submission-approval-pdf` (Foundation + B1 Letter Templates + B2 Submission/Approval/PDF, semuanya sudah lokal sebelum rework ini dimulai)
**Commit rework:** 45 commit di atas base
**HEAD saat ini:** `5f64678`
**Status test:** **172/172 passing**, `ruff check app tests alembic` **bersih**
**Spec acuan:** `docs/superpowers/specs/2026-07-24-fitur-adjustment-rework-design.md`

---

## Cara kerja berbeda antar Part — penting untuk diketahui sebelum review

- **Part 1-5**: dikerjakan dengan alur *subagent-driven-development* penuh — setiap task diimplementasikan oleh subagent, lalu direview independen oleh subagent reviewer terpisah (verifikasi spec compliance + code quality, dengan re-review setelah fix). Setiap temuan Critical/Important sudah di-fix dan di-reverify sebelum task ditandai selesai.
- **Part 6-9**: setelah Anda memperbarui `CLAUDE.md` (kebijakan baru: tidak pakai subagent untuk CRUD/endpoint/service/migration, tidak bikin plan tertulis, tidak full-review per task), keempat part ini dikerjakan **langsung oleh saya (main session)**, bukan lewat subagent implementer+reviewer. Tetap TDD (test ditulis & dijalankan per fitur), tapi **belum ada independent adversarial review** seperti Part 1-5. Ini alasan utama kenapa "pengecekan menyeluruh" yang akan kita lakukan berikutnya penting — Part 6-9 belum pernah "diserang" oleh reviewer terpisah.

---

## Part 1 — RBAC Dua Dimensi (Role + Position)

- Tabel baru `positions`, `position_permissions` (pola identik `role_permissions`).
- 4 Role: `administrator-it` (`*`), `admin`, `staff`, `warga`. 7 Position: `kepala_desa`(1) → `warga_desa`(7), level numerik lebih kecil = otoritas lebih tinggi.
- `User` dapat kolom baru: `email`, `position_id`, `rt_id`, `rw_id`, `pending_approval`.
- `AuthService.permissions_for(user)` = union permission Role ∪ Position, 100% data-driven (tidak ada `if role == "..."` di mana pun).
- 8 demo account diperbarui (kades/sekdes/bendahara/staf/warga/operator/rt001/rw001).
- **108/108 test saat itu, sudah direview subagent.**

## Part 2 — Penghapusan Multi-Desa

- Model `Village` + tabel `villages` dihapus total. `village_id` dihapus dari 6 tabel (dusun, family_cards, residents, letter_templates, submissions, approval_step_configs).
- Tabel singleton baru `village_profile` (nama, kontak, sambutan kades, dll — field untuk Portal Desa juga sudah disiapkan di sini).
- `GET/PUT /village-profile` menggantikan seluruh blok CRUD `/villages`.
- Migrasi data 2 tahap (pindahkan 1 baris `villages` lama → `village_profile`, baru drop kolom/tabel).
- **110/110 test saat itu, sudah direview subagent.**

## Part 3 — Autentikasi: Registrasi, Login Unified, Lupa Password

- OTP login **dihapus total** (`OtpService` di-`git rm`).
- `POST /auth/login` — `identifier` (username ATAU NIK) + `password`.
- `POST /auth/register` — `position_choice` (`warga|rt|rw|staff`). Warga wajib NIK cocok data `Resident`, langsung aktif. `staff/rt/rw` dibuat `pending_approval=true`, tidak bisa login sampai di-approve (baru bisa di-approve setelah Part 5 ada).
- `POST /auth/forgot-password` / `POST /auth/reset-password` — kode via Redis TTL, tidak membocorkan apakah akun ada, invalidate semua refresh token saat reset berhasil.
- **124/124 test saat itu, sudah direview subagent.**

## Part 4 — Submission/Approval/PDF: Dokumen Belum Ditandatangani

- QR code, tanda tangan visual, `verification_code`, endpoint `GET /public/verify/{code}` **dihapus total** (`app/services/qr.py`, `app/api/v1/public.py` di-`git rm`, dependency `qrcode` dicopot dari `pyproject.toml`).
- Letterhead PDF diganti placeholder tanda tangan kosong `( ......... )` + label "Tanda Tangan & Cap Basah".
- Katalog surat **11 → 8 jenis** (Izin Keramaian, Pengantar KTP, Pengantar KK dihapus via migrasi soft-delete, bukan hard-delete, supaya data historis aman).
- **120/120 test, sudah direview subagent** (termasuk review khusus line-by-line untuk migrasi Alembic hand-written).

## Part 5 — Manajemen User & Position

- `UserManagementService` — CRUD user penuh untuk `admin`/`administrator-it`, termasuk assign posisi `kepala_desa`/`sekretaris_desa`/`bendahara_desa` yang TIDAK bisa dipilih lewat registrasi mandiri.
- **Aturan hierarki**: actor hanya boleh CRUD target dengan `position.level` lebih besar (otoritas lebih rendah) — perbandingan numerik murni. Kades bisa kelola sekdes, tapi sekdes TIDAK bisa kelola kades, walau sama-sama Role `admin`.
- Endpoint approve/reject untuk akun `pending_approval=true` hasil registrasi Part 3.
- `GET /users` default sembunyikan `warga_desa` (kecuali `?include_warga=true`), filter `position_id`/`search`.
- **145/145 test, sudah direview subagent** — termasuk review khusus keamanan (privilege-escalation check).

## Part 6 — LAPDUK (Laporan Penduduk) *(tanpa subagent review)*

- Model baru `LapdukReport` (per RT per bulan `YYYY-MM`, unique constraint `(rt_id, period)` — upsert).
- Permission data-driven: `lapduk:manage_own` (RT, hanya baris RT sendiri), `lapduk:read_rw` (RW, semua RT di RW-nya), `lapduk:read_all`/`export`/`import` (role staff/admin/`*`).
- `POST/PUT /lapduk` (upsert), `GET /lapduk` (filter period/rw_id/rt_id), `GET /lapduk/export`, `POST /lapduk/import` (Excel, per-baris isolasi error).
- 10 test service + 4 test API, semua lolos.

## Part 7 — Notifikasi *(tanpa subagent review)*

- Model `Notification` (per user, event_type/title/body/is_read).
- `NotificationProvider` abstrak + `LoggingNotificationProvider` (log-only, tidak ada channel WhatsApp sama sekali).
- `app/workers/tasks.py` — scaffold ARQ (`send_notification_job` + `WorkerSettings`) sebagai *seam* untuk provider blocking di masa depan; jalur request saat ini memanggil provider secara sinkron (provider log-only, tidak ada biaya blocking).
- `GET /notifications`, `POST /notifications/{id}/read`, `POST /notifications/read-all`.
- Terhubung ke: perubahan status pengajuan surat (`submitted/approved/issued/rejected`), approve/reject registrasi (Part 5), pengiriman kode reset password (Part 3).
- **Regresi ditemukan & diperbaiki**: test Part 1 (`test_auth_service.py`) memakai `"lapduk:manage_own"` sebagai placeholder kode permission fiktif — begitu Part 6 benar-benar men-seed kode itu, test-nya bentrok (`UNIQUE constraint`). Sudah diperbaiki (ganti ke placeholder yang tidak collide).
- 7 test service+API baru, semua lolos.

## Part 8 — Dashboard *(tanpa subagent review)*

- `GET /dashboard/stats|trend|per-jenis|inbox`, permission `dashboard:read` (staff/admin/`*`).
- Konten sama untuk semua role yang punya akses (tidak dibedakan isi per role, spec Bagian 10).
- Setiap query di-cache Redis 45 detik.
- 2 test API, lolos.

## Part 9 — Portal Desa *(tanpa subagent review)*

- Model baru `NewsPost` (berita/artikel), `GalleryPhoto`, `OrgMember` — `VillageProfile` sudah ada sejak Part 2, tidak diduplikasi.
- Endpoint publik tanpa auth: `GET /public/portal/profile|news|gallery|organization`.
- Endpoint admin CRUD (`portal:manage` → admin/`*`) untuk NewsPost/GalleryPhoto/OrgMember. **`/village-profile` yang sudah ada dari Part 2 sengaja TIDAK diubah** (tetap pakai permission `village:manage`, bukan diganti `portal:manage`) — keputusan minimal-diff supaya tidak menyentuh ulang desain Part 2 yang sudah selesai.
- 4 test API, lolos.

---

## Rangkuman Permission Baru yang Ditambahkan Sepanjang Rework

| Permission | Diberikan ke |
|---|---|
| `user:manage` | admin, `*` |
| `lapduk:manage_own` | Position `rt` |
| `lapduk:read_rw` | Position `rw` |
| `lapduk:read_all`, `lapduk:export`, `lapduk:import` | staff, admin, `*` |
| `notification:read` | **semua role** (warga, staff, admin, `*`) |
| `dashboard:read` | staff, admin, `*` |
| `portal:manage` | admin, `*` |

Semua sudah di-reseed ke database lokal `db_kopo` (live), bukan cuma kode — diverifikasi query langsung setelah tiap penambahan.

## Migrasi Alembic Baru (Part 4-9, semua sudah `alembic upgrade head` ke `db_kopo` lokal)

1. `8608fa1beedd` — drop `verification_code`, soft-delete 3 template surat yang dihapus (Part 4)
2. `9091aeaf3f6c` — tabel `lapduk_reports` (Part 6)
3. `bd23bc4a9c86` — tabel `notifications` (Part 7)
4. `d549039d7c60` — tabel `news_posts`, `gallery_photos`, `org_members` (Part 9)

## Package Dihapus

- `qrcode` (Part 4) — dicopot dari `pyproject.toml` dan di-`pip uninstall`, diverifikasi tidak ada lagi import transitif.

---

## Yang PERLU Diperiksa di Sesi "Pengecekan Menyeluruh" Berikutnya

Daftar temuan yang sengaja **belum diperbaiki** (bukan blocking, tapi perlu keputusan Anda):

1. **README.md sudah usang** — masih menyebut Notifikasi/Dashboard/Portal Desa sebagai "belum dikerjakan / Sub-project C selanjutnya" padahal semua sudah dibangun (Part 6-9). Perlu ditulis ulang.
2. **Part 6-9 belum pernah direview independen** (lihat catatan di atas) — cocok jadi fokus utama sesi pengecekan menyeluruh, terutama bagian otorisasi LAPDUK (RT/RW scoping) dan hierarki di endpoint lain.
3. **`seed_rbac` bisa menimpa akun asli** — komentar di `app/seed/seed.py` sejak Part 1 sudah memperingatkan: setelah registrasi mandiri (Part 3) hidup, re-run seed bisa menimpa role/position user asli kalau usernamenya kebetulan sama dengan salah satu `DEMO_ACCOUNTS`. Belum di-fix (butuh keputusan desain: scope ulang matching-nya).
4. **`UserManagementService._load_actor`** (Part 5, `app/api/v1/users.py`) tidak menjaga kasus actor admin yang akunnya sendiri di-soft-delete di tengah sesi (token masih valid) — akan jatuh ke 500 generik, bukan 401 bersih. Reachable tapi jarang terjadi.
5. **Downgrade migrasi `8608fa1beedd`** (Part 4) membangkitkan ulang template surat yang di-retired tanpa cek apakah soft-delete-nya memang berasal dari migrasi ini atau alasan lain — edge case kecil, sesuai literal spec plan.
6. **ARQ belum benar-benar terhubung** — `app/workers/tasks.py` sudah ada (scaffold `send_notification_job` + `WorkerSettings`), tapi jalur request (`NotificationService.notify`) masih memanggil provider secara sinkron, bukan lewat `enqueue_job`. Sengaja begitu (provider log-only, tidak ada I/O blocking hari ini) — tapi kalau nanti provider email sungguhan (SMTP) dipasang, jalur enqueue perlu benar-benar disambungkan.
7. **Belum ada worker process yang benar-benar dijalankan** (`arq app.workers.tasks.WorkerSettings`) — hanya modul & job function-nya yang sudah dibuat dan diverifikasi bisa di-import.

## Git — Status & Rencana Push

- Semua pekerjaan **masih 100% lokal**, branch `feat/fitur-adjustment-rework`, belum disentuh ke `origin`.
- Riwayat branch **linear bersih**: `main` → `feat/foundation` → `feat/letter-templates` → `feat/submission-approval-pdf` → `feat/fitur-adjustment-rework` (setiap branch strict ancestor dari berikutnya, tidak ada divergensi) — jadi nanti fast-forward `main` ke HEAD lalu `git push origin main` **tidak akan menghasilkan conflict**.
- Sesuai kesepakatan sebelumnya: **push ke `origin/main` ditunda sampai seluruh Part 1-9 + review akhir selesai** — belum dilakukan sekarang, menunggu hasil pengecekan menyeluruh berikutnya.
- Semua commit sudah tercatat atas nama `ZakiAdhitia <zakiadhitia@smkwikrama.sch.id>` (identitas git yang sudah ada di mesin ini, tidak pernah diubah).

## Test Coverage Akhir

```
172 passed, 0 failed
ruff check app tests alembic -> All checks passed!
```

Test baru yang ditambahkan Part 6-9: `test_lapduk_service.py` (10), `test_lapduk_api.py` (4),
`test_notification_service.py` (5), `test_notification_api.py` (2), `test_dashboard_api.py` (2),
`test_portal_api.py` (4) — total 27 test baru tanpa review independen (lihat poin 2 di atas).
