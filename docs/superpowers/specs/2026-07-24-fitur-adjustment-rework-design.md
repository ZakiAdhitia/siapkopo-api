# Rework: Penyesuaian Fitur SIPADES — Design Spec

> Sumber kebenaran perubahan: `PENYESUAIAN_FITUR.md` (root repo), hasil diskusi dengan pihak
> klien. Spec ini menggantikan/membatalkan sebagian rencana Sub-project C lama
> (`2026-07-24-*` belum sempat ditulis untuk Fase 8-11 — dibatalkan sebelum sempat jadi
> spec tersendiri) dan sekaligus mendefinisikan REWORK atas kode yang sudah dibangun di
> `feat/foundation`, `feat/letter-templates`, `feat/submission-approval-pdf` (ketiganya
> masih lokal, belum di-push/merge ke `main` — aman diubah bebas).

## 1. Latar Belakang & Ruang Lingkup

Setelah Fase 1-7 (Foundation, Template Engine, Pengajuan/Approval/PDF) selesai dibangun,
klien meminta serangkaian perubahan signifikan sebelum lanjut ke fitur berikutnya:
penghapusan beberapa fitur yang sudah/akan dibangun, perombakan model role menjadi
role+position dua dimensi, penghapusan dukungan multi-desa, dan beberapa modul baru
(registrasi, lupa password, LAPDUK, manajemen user).

Scope rework ini **menyentuh ulang semua fase yang sudah dibangun** (bukan cuma
menambah fase baru), karena RBAC dan approval workflow adalah fondasi yang dipakai di
mana-mana. Spec ini adalah kompilasi final dari seluruh keputusan desain yang sudah
disetujui, jadi rujukan tunggal untuk implementation plan.

## 2. Penghapusan Fitur — Detail

| Fitur | Status sebelumnya | Tindakan |
|---|---|---|
| Pengaduan Masyarakat | Belum dibangun (baru direncanakan) | Dicoret dari rencana, tidak dibangun |
| APBDes (tampilan+fitur) | Belum dibangun | Dicoret dari rencana Portal Desa |
| Surat: Izin Keramaian, Pengantar KTP, Pengantar KK | Sudah dibangun & ter-seed (B1) | Dihapus dari `SURAT_TEMPLATES`; baris di `db_kopo` di-soft-delete via migrasi data |
| Nomor Antrian Online | Belum dibangun (frontend `Antrian.jsx` placeholder saja) | Dicoret dari rencana |
| Verifikasi WhatsApp (channel notifikasi) | Belum dibangun | Dicoret — Notifikasi hanya in-app + email |
| Login OTP (NIK+OTP) | Sudah dibangun (Foundation) | **Dihapus total** — diganti login unified (Bagian 4) |
| Multi-desa (`Village` model + `village_id`) | Sudah dibangun (Foundation, dipakai di 6 tabel) | **Dihapus total** — diganti `VillageProfile` singleton (Bagian 6) |
| Tanda tangan visual, QR code, `verification_code`, endpoint verifikasi publik | Sudah dibangun (B2) | **Dihapus total** — surat terbit sebagai dokumen belum ditandatangani (Bagian 5) |

**Package**: `qrcode` dihapus dari `pyproject.toml` (tidak ada pemakaian lain setelah QR
dihapus). Tidak ada package lain yang perlu dihapus — tidak pernah ada SDK WhatsApp/pihak
ketiga lain yang benar-benar terpasang.

**Kode yang dihapus total**:
- `app/services/qr.py`
- `app/services/otp.py`
- `app/api/v1/public.py` (endpoint `GET /public/verify/{code}`)
- Route `/auth/request-otp`, `/auth/verify-otp` di `app/api/v1/auth.py`
- `AuthService.login_otp`, `SubmissionService.resolve_signer_name`
- `Settings.otp_ttl_seconds`, `Settings.otp_length`
- Blok CRUD `/villages` di `app/api/v1/master.py` dan `app/models/master.py::Village`

## 3. RBAC Dua Dimensi: Role + Position

**Role** (4 — drive permission dasar, tabel `roles`/`role_permissions` tetap seperti
sekarang, cuma isinya diganti):

| Role (slug) | Deskripsi |
|---|---|
| `administrator-it` | Akses penuh (`"*"`) — pengelola sistem/IT |
| `admin` | Approval final surat, kelola user & master data/template/portal. Diisi user ber-position Kepala Desa **atau** Sekretaris Desa — keduanya setara dalam role ini |
| `staff` | Approval tahap pertama surat, verifikasi resident, lihat dashboard |
| `warga` | Ajukan surat, lihat status. Kalau position-nya RT/RW, dapat permission tambahan lewat Position (bukan lewat Role) |

**Position** (baru — tabel `positions` + `position_permissions`, pola identik
`role_permissions` supaya tetap data-driven, tanpa `if position == "..."` di kode mana pun):

| Position (slug) | `level` | Permission tambahan via Position |
|---|---|---|
| `kepala_desa` | 1 | — |
| `sekretaris_desa` | 2 | — |
| `bendahara_desa` | 3 | — |
| `staff_desa` | 4 | — |
| `rw` | 5 | `lapduk:read_rw` |
| `rt` | 6 | `lapduk:manage_own` |
| `warga_desa` | 7 | — |

`level` numerik lebih kecil = otoritas lebih tinggi. Dipakai murni untuk: (a) aturan
hierarki CRUD user (Bagian 8), (b) urutan tampil default halaman user. **Tidak** dipakai
untuk approval surat (itu murni lewat `Role`, sudah settled di Fase 6/B2, tidak berubah
arsitekturnya).

**Permission efektif seorang user** = union dari `role_permissions[user.role]` dan
`position_permissions[user.position]`. `AuthService.permissions_for` diperluas untuk
menggabungkan keduanya (masih 100% data-driven dari DB, JWT tetap membawa daftar
permission code hasil union ini seperti sekarang).

**Perubahan skema `User`**: tambah kolom `email` (wajib diisi saat registrasi — dipakai
notifikasi & reset password), `position_id` (FK ke `positions`, wajib), `rt_id` (FK
nullable, dipakai kalau `position=rt`), `rw_id` (FK nullable, dipakai kalau `position=rw`).

Position adalah data referensi tetap (di-seed, mirip `Permission`) — **tidak ada CRUD API
khusus** untuk menambah/mengubah Position kecuali ada permintaan eksplisit di masa depan.

## 4. Autentikasi: Registrasi, Login Unified, Lupa Password

**Registrasi** — `POST /auth/register` (publik, tanpa auth):
- Body: `full_name`, `nik`, `email`, `username`, `password`, `position_choice` (salah
  satu dari `staff|rt|rw|warga`). Posisi lain (`kepala_desa`/`sekretaris_desa`/
  `bendahara_desa`) **tidak** bisa dipilih sendiri saat registrasi — hanya bisa
  di-assign lewat halaman user (Bagian 8) oleh `admin`/`administrator-it`, termasuk
  saat mereka mengangkat seorang `staff_desa` menjadi posisi lebih tinggi.
- `position_choice` dipetakan ke `role` + `position` (slug, Bagian 3) yang benar-benar
  disimpan:
  | `position_choice` | `role` tersimpan | `position` tersimpan |
  |---|---|---|
  | `warga` | `warga` | `warga_desa` |
  | `rt` | `warga` | `rt` |
  | `rw` | `warga` | `rw` |
  | `staff` | `staff` | `staff_desa` |
- Kalau `position_choice=warga`: `nik` divalidasi harus cocok dengan `Resident` yang
  sudah ada di master data (pola sama seperti `seed_link_demo_resident` yang sudah ada,
  tapi lewat endpoint bukan seed) → akun langsung `is_active=true`, tanpa approval.
- Kalau `position_choice` lain (`staff|rt|rw`): akun dibuat dengan `is_active=false`,
  `pending_approval=true` (kolom baru di `User`) → tidak bisa login sampai di-approve
  oleh `admin`/`administrator-it`. Untuk `rt`/`rw`, request registrasi juga wajib
  menyertakan `rt_id`/`rw_id` yang dipilih (divalidasi ada di master data wilayah).
- Response: pesan status registrasi (langsung aktif vs menunggu approval), tidak
  langsung mengeluarkan token.

**Approval registrasi** — bagian dari halaman User (Bagian 8): `admin`/`administrator-it`
bisa lihat daftar `pending_approval=true` dan approve (`is_active=true,
pending_approval=false`) atau reject (hapus/soft-delete akun).

**Login unified** — `POST /auth/login`:
- Body: `identifier` (dicocokkan ke `username` **atau** `nik`, keduanya kolom unique yang
  sudah ada di `User`) + `password`.
- `AuthService.login_password` dan `login_otp` digabung jadi satu `login(identifier,
  password)` yang query `User` dengan `username == identifier OR nik == identifier`.
- NIK baru valid dipakai login setelah user register (bukan otomatis semua baris
  `Resident` bisa login seperti model lama).

**Lupa password** — `POST /auth/forgot-password` (body: `identifier`) →
generate kode acak, simpan di Redis dengan TTL (reuse pola `OtpService` lama tapi
generik, pindah ke helper baru mis. `app/services/password_reset.py`), kirim ke
`user.email` lewat `NotificationProvider` (Bagian 9, log-only/dummy).
`POST /auth/reset-password` (body: `identifier`, `code`, `new_password`) → verify+consume
kode, hash password baru, invalidate semua refresh token user tersebut (security best
practice standar).

## 5. Approval Surat & Penerbitan Dokumen

- Approval chain default (`seed_approval_steps`): **2 step** — `staff` (order_index=0) →
  `admin` (order_index=1). Engine `ApprovalStepConfig`/turn-enforcement (role_id-based,
  configurable, `PUT /approval-steps`) **tidak berubah arsitekturnya sama sekali** — cuma
  jumlah default step dan katalog role yang direferensikan berubah.
- **Hasil akhir surat = dokumen belum ditandatangani.** Setelah step approval terakhir
  (`admin`) disetujui, sistem: alokasi nomor surat (`LetterNumberService`, tidak
  berubah) → render PDF final (kop surat + nomor + isi jawaban) **tanpa** blok tanda
  tangan/nama penanda tangan, **tanpa** QR code → simpan via `FileStorageService`
  (tidak berubah) → status `ISSUED`.
- `_LETTERHEAD` (`template_render.py`) kehilangan div `.qr` dan bagian nama penanda
  tangan di `.ttd`; diganti placeholder polos, mis.:
  ```
  <div class="ttd">
    <div class="tempat-tanggal">{{ tanggal }}</div>
    <div class="tanda-tangan-kosong">( ......................................... )</div>
    <div class="ttd-label">Tanda Tangan &amp; Cap Basah</div>
  </div>
  ```
- `render_preview`/`render_issued`/`_render_document` kehilangan parameter
  `qr_data_uri`/`signer_name`.
- `Submission.verification_code` kolom dihapus. `GET /public/verify/{code}` dan
  `app/services/qr.py` dihapus total (Bagian 2).
- 11 → 8 jenis surat: `SURAT_TEMPLATES` (`app/seed/letter_template_data.py`) kehilangan
  entri `keramaian`, `ktp`, `kkpengantar`. Migrasi data men-soft-delete
  (`deleted_at`) baris `letter_templates`+`template_fields` terkait yang sudah
  ter-seed di `db_kopo`, plus `is_active=false`.

## 6. Penghapusan Multi-Desa

- `Village` model dan tabel `villages` **dihapus total**.
- Kolom `village_id` dihapus dari 6 tabel: `dusun`, `family_cards`, `residents`,
  `letter_templates`, `submissions`, `approval_step_configs`. `Dusun` jadi level
  teratas hierarki wilayah.
- Info deskriptif (`name`, `slogan`, `kecamatan`, `kabupaten`, `provinsi`) pindah ke
  tabel singleton baru `village_profile` — selalu tepat 1 baris (di-enforce di service
  layer, bukan constraint DB — cukup untuk skala aplikasi ini). Field tambahan untuk
  Portal Desa (Bagian 11): `description`, `photo_path`, `kades_name`, `kades_photo_path`,
  `sambutan_text`, `kontak_alamat`, `kontak_telp`, `kontak_email`, `kontak_jam`,
  `jumlah_jiwa`, `jumlah_kk`, `luas_wilayah`.
- `GET /village-profile` (publik/read oleh siapa saja yang login) + `PUT
  /village-profile` (`portal:manage` → `admin`/`administrator-it`) menggantikan seluruh
  blok CRUD `/villages` di `master.py`.
- Setiap service yang query/scoping lewat `village_id` (letter_template, submission,
  approval_config, excel resident import/export, seed.py, semua test yang bikin fixture
  `Village`) disederhanakan untuk beroperasi tanpa scoping desa.
- **Strategi migrasi**: revisi Alembic BARU (bukan mengedit revisi lama
  `ab51fdb6e0f1_master_data_tables.py` dkk.) — data migration dulu (pindahkan 1 baris
  `villages` yang sudah ada di `db_kopo` lokal ke `village_profile`), baru schema
  migration (drop kolom/tabel).

## 7. LAPDUK (Laporan Penduduk)

- Model baru `LapdukReport`: `rt_id` (FK), `period` (string `"YYYY-MM"`), `jumlah_kk`,
  `laki_laki`, `perempuan`, `pindah`, `datang`, `lahir`, `meninggal`,
  `submitted_by_user_id`. Unique constraint `(rt_id, period)` — upsert per RT per bulan.
- `User.rt_id`/`User.rw_id` (Bagian 3) menentukan wilayah kewenangan.
- Permission (lewat `position_permissions`, Bagian 3): `lapduk:manage_own` (RT — hanya
  baris RT miliknya), `lapduk:read_rw` (RW — semua RT di RW-nya), `lapduk:read_all`,
  `lapduk:export`, `lapduk:import` (role-level: `staff`, `admin`, `administrator-it`).
- Endpoint:
  - `POST/PUT /lapduk` — upsert baris (scoping sesuai permission di atas)
  - `GET /lapduk?period=&rw_id=&rt_id=` — list dengan filter, scoping otomatis
  - `GET /lapduk/export?period=&rw_id=` — export Excel (reuse pola `app/services/excel.py`)
  - `POST /lapduk/import` — form-data file + `period` wajib di request, upsert massal
    per `(rt_id, period)`, validasi `rt_id` milik importer (kalau RW) atau importer
    sendiri (kalau RT — hanya boleh import barisnya sendiri)

## 8. Manajemen User & Position

- `GET/POST/PUT/DELETE /users` — akses hanya role `admin` (position kades/sekdes) dan
  `administrator-it` (permission `user:manage`). `POST`/`PUT` di sini juga satu-satunya
  cara meng-assign posisi `kepala_desa`/`sekretaris_desa`/`bendahara_desa` (tidak bisa
  lewat registrasi mandiri, Bagian 4). `DELETE` adalah soft-delete, konsisten dengan
  `SoftDeleteMixin` yang sudah dipakai `User` sejak Foundation.
- **Aturan hierarki**: service membandingkan `actor.position.level` vs
  `target.position.level` — actor hanya boleh CRUD target dengan `level` **lebih
  besar** (otoritas lebih rendah) dari `level` miliknya. Perbandingan numerik murni,
  tidak hardcode nama posisi.
- Filter: `?position_id=&search=` (search cocok nama/username/NIK).
- Default: user ber-`position=warga_desa` disembunyikan kecuali `?include_warga=true`.
- Default sort: `position.level ASC`, lalu `full_name ASC`.
- Termasuk endpoint approve/reject untuk `pending_approval=true` (Bagian 4).

## 9. Notifikasi (Fase 8)

- Model `Notification`: `user_id`, `event_type`, `title`, `body`, `is_read`,
  `created_at`.
- `NotificationProvider` — interface abstrak `send_email(to, subject, body)`.
  **Tidak ada channel WhatsApp sama sekali** (dihapus dari rencana awal). Implementasi
  konkret `LoggingNotificationProvider` (log-only, siap diganti nanti tanpa ubah caller).
- ARQ worker (`app/workers/worker.py`) — job `send_notification_job`: simpan
  `Notification` row + panggil provider, dengan retry bawaan ARQ.
- `NotificationService.notify(...)` dipakai untuk: perubahan status pengajuan surat
  (menggantikan stub `notify_status_change` di B2), approval/reject registrasi (Bagian
  4), kirim kode reset password (Bagian 4).
- `GET /notifications`, `POST /notifications/{id}/read`, `POST
  /notifications/read-all` — permission `notification:read` di semua role.

## 10. Dashboard (Fase 9)

- Read-only agregasi dari `Submission` (tanpa `village_id` lagi, single-desa).
- `GET /dashboard/stats|trend|per-jenis|inbox` — permission `dashboard:read` (`staff`,
  `admin`, `administrator-it`).
- Redis cache TTL pendek (30-60 detik) di tiap endpoint.
- Konten sama untuk semua role yang punya akses (tidak dibedakan per role secara isi,
  hanya akses menu yang dibedakan lewat permission).

## 11. Portal Desa (Fase 10, minus APBDes & Pengaduan)

- `VillageProfile` — sudah didefinisikan di Bagian 6 (menggantikan `Village`).
- Model baru `NewsPost` (`content_type`: `berita`/`artikel`, `kategori`, `judul`,
  `tanggal`, `excerpt`, `photo_path` nullable, `icon` nullable).
- Model baru `GalleryPhoto` (`photo_path`, `caption`, `order_index`).
- Model baru `OrgMember` (`jabatan`, `nama`, `order_index`, `photo_path` nullable).
- Endpoint publik (no-auth): `GET /public/portal/profile`, `/news`, `/gallery`,
  `/organization`.
- Endpoint admin CRUD (`portal:manage` → `admin`/`administrator-it`) untuk keempat
  model di atas. Foto lewat `FileStorageService` yang sudah ada.
- Seed data diterjemahkan dari `mockData.js` (`berita`, `artikel`, `galeri`, `struktur`,
  info kontak/profil) — **tanpa** `apbdes`.

## 12. Migrasi Data & Strategi Alembic

Semua perubahan skema lewat revisi Alembic **baru** (bukan edit revisi lama), supaya
riwayat yang sudah ter-apply ke `db_kopo` lokal tetap konsisten. Urutan logis:
1. Tabel referensi baru: `positions`, `position_permissions` + seed.
2. Kolom baru di `users`: `email`, `position_id`, `rt_id`, `rw_id`, `pending_approval`.
3. Migrasi data `villages` (1 baris) → `village_profile` (tabel baru).
4. Drop `village_id` dari 6 tabel + drop tabel `villages`.
5. Soft-delete 3 baris `letter_templates`/`template_fields` yang dihapus.
6. Update baris `roles` (rename/hapus `sekretaris`/`kades`/`staf`/`administrator`,
   tambah `admin`/`staff`/`administrator-it`) — dilakukan lewat seed idempotent
   (`seed_rbac`), bukan migration data mentah, supaya konsisten dengan pola seeding
   yang sudah ada.
7. Drop `submissions.verification_code`.
8. Tabel baru: `notifications`, `lapduk_reports`, `news_posts`, `gallery_photos`,
   `org_members`.

## 13. Dokumen yang Diupdate

`PRD-Sistem-Pelayanan-Desa.md.md`, `Task.md`, `CLAUDE.md` diupdate terpisah (bukan
bagian dari implementation plan/kode) segera setelah spec ini disetujui, mengikuti
seluruh keputusan Bagian 1-11 di atas — termasuk pelunakan instruksi "Future Ready:
Multiple Village/Multi Tenant" di `CLAUDE.md` (jadi catatan non-tujuan, bukan
requirement arsitektur aktif) dan penghapusan baris terkait OTP/WhatsApp/QR/Tanda
Tangan Digital/Pengaduan/APBDes/Antrian di ketiga dokumen.

## 14. Non-Goals / Out of Scope

- Tidak ada tanda tangan digital kriptografis maupun representasi visual apa pun pada
  PDF surat (dihapus total, lihat Bagian 5).
- Tidak ada verifikasi publik dokumen (QR/kode) dalam bentuk apa pun.
- Tidak ada dukungan multi-desa/multi-tenant dalam bentuk apa pun (arsitektur
  disederhanakan ke single-desa; jika suatu saat dibutuhkan lagi, itu jadi migrasi
  arsitektur terpisah di masa depan, bukan sesuatu yang perlu diantisipasi sekarang).
- Tidak ada channel WhatsApp di mana pun (notifikasi maupun login).
- Tidak ada CRUD API untuk `Position` (data referensi tetap, di-seed).
- Pengaduan dan APBDes tidak dibangun sama sekali di rework ini.
