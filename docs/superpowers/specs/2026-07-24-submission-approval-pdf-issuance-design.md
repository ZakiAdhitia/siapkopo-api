# Design Spec — SIPADES Backend, Sub-project B2: Pengajuan, Approval Workflow & PDF Issuance

**Tanggal:** 2026-07-24
**Ruang lingkup:** Fase 5 (Pengajuan Surat), Fase 6 (Approval Workflow), Fase 7 (PDF Generator)
**Status:** Disetujui (design), menunggu implementation plan
**Repo:** `sipades-kopo-api`

---

## 1. Konteks & Keputusan

Sub-project B2 melanjutkan B1 (Letter Template Engine, Fase 4 — selesai di branch
`feat/letter-templates`). B2 mencakup **3 fase sekaligus** (Submission, Approval Workflow,
PDF Issuance) sebagai satu sub-project — keputusan eksplisit pengguna untuk tidak memecahnya
lebih lanjut, meski ini bagian paling kompleks di seluruh sistem (state machine + workflow
configurable + integrasi `TemplateRenderService`). Plan implementasi diperkirakan lebih besar
dari B1.

### Keputusan desain kunci

- **Tanda tangan & stempel digital: representasi visual saja**, bukan tanda tangan
  kriptografis PKI. Nama Kepala Desa bergaya signature + placeholder stempel + kode
  verifikasi/QR yang dicek ke server membuktikan keaslian — bukan sertifikat digital.
  CLAUDE.md menandai "Digital Signature" sebagai item "Future Ready", bukan wajib sekarang.
- **Reject bersifat terminal.** Pengajuan yang ditolak tidak bisa diedit & dikirim ulang;
  warga membuat pengajuan baru jika ingin mencoba lagi. Menyederhanakan state machine
  (tidak perlu status draft/revisi), sesuai yang terlihat di frontend (`Detail.jsx` tidak
  punya tombol "perbaiki & kirim ulang").
- **Approval workflow configurable per desa** via tabel `ApprovalStepConfig` (bukan
  `if role == "sekdes"`), mengikuti prinsip CLAUDE.md: Approval Step → Approval Config →
  Next Step. Giliran approver ditegakkan dengan membandingkan `current_user.role_id` dengan
  konfigurasi step saat ini di **service layer** — endpoint dijaga permission umum
  (`submission:approve`), bukan permission per-role.
- **Approve di tahap terakhir (Kepala Desa) otomatis memicu issuance** (generate PDF+nomor+QR)
  — bukan tombol terpisah, sesuai `DetailAdmin.jsx` (tombol Kades: "Setujui & Tanda Tangani"
  → langsung TERBIT).
- **Nomor surat dialokasikan atomik** per `(template_id, tahun)`, reset tahunan — melengkapi
  B1 yang hanya mendefinisikan *format*, bukan counter.
- **Upload lampiran dibangun lengkap di backend** meski tombol upload di `FormSurat.jsx`
  masih stub (`notify('Fitur akan tersedia di versi final')`) — backend mengikuti PRD/CLAUDE.md
  penuh, bukan menunggu frontend.
- **Notification hanya hook/stub** (log saja) — infrastruktur antrian nyata (WhatsApp/Email/ARQ)
  adalah Fase 8, di luar cakupan B2. B2 hanya menyiapkan titik panggil yang bersih.
- **QR code** pakai library `qrcode` (murni Python + Pillow, Pillow sudah ter-install sebagai
  dependency `xhtml2pdf` dari B1) — tanpa risiko dependency native seperti WeasyPrint dulu.

---

## 2. Model Data

Mengikuti pola Clean Architecture & konvensi Foundation/B1 (`router → service → repository →
model`, `BaseRepository`, UUID/timestamp/soft-delete mixin, `village_id` tenant-scoped,
response envelope, RBAC data-driven).

### `ApprovalStepConfig`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `village_id` | FK → villages.id | |
| `order_index` | int | Urutan tahap |
| `role_id` | FK → roles.id | Role penanggung jawab tahap ini (data, bukan string hardcode) |

Unique `(village_id, order_index)`. Seed default: 3 tahap untuk Desa Kopo
(Staf Loket → Sekretaris Desa → Kepala Desa), sesuai `SETTINGS.approvalMode='3'` di mockData.
**Dapat dikonfigurasi ulang oleh administrator via API** (Bagian 8) — bukan cuma seed statis,
memenuhi kebutuhan eksplisit Task.md Fase 6 "Workflow Configuration". Untuk menghindari status
`Submission` yang PENDING menjadi tidak konsisten (mis. `current_step_index` menunjuk ke step
yang sudah dihapus), **mengubah konfigurasi ditolak (409) selama masih ada `Submission`
berstatus PENDING di desa tsb** — admin harus menunggu seluruh pengajuan berjalan selesai
(ISSUED/REJECTED) sebelum mengubah susunan tahap. Aturan sederhana ini cukup untuk MVP karena
reorganisasi alur approval adalah aksi admin yang jarang terjadi, bukan operasi harian.

### `Submission`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `village_id` | FK → villages.id | |
| `template_id` | FK → letter_templates.id | |
| `submitted_by_user_id` | FK → users.id | Warga pengaju |
| `answers` | JSON | `field_key` → nilai, divalidasi terhadap `TemplateField` saat submit |
| `status` | enum: PENDING/REJECTED/ISSUED | |
| `current_step_index` | int, nullable | Posisi di `ApprovalStepConfig`, bermakna selama PENDING |
| `letter_number` | str, nullable | Terisi saat ISSUED, dari `numbering_pattern` + counter asli |
| `verification_code` | str, unik, nullable | Terisi saat ISSUED |
| `pdf_storage_path` | str, nullable | Path file PDF hasil issuance |
| `rejection_reason` | text, nullable | Wajib diisi saat REJECTED |
| `rejected_by_user_id`, `rejected_at` | nullable | |
| `issued_at` | nullable | |

Tidak ada endpoint update untuk mengubah `answers` setelah submit (sesuai keputusan reject
terminal — mengedit berarti membuat submission baru).

### `SubmissionStatusHistory`

`submission_id`, `step_index` (nullable), `action` (enum: SUBMITTED/APPROVED/REJECTED/ISSUED),
`actor_user_id` (nullable — SUBMITTED aktornya warga sendiri), `note` (nullable), `created_at`.
Sumber data untuk timeline "Lacak Progres" (`Detail.jsx`) dan pemenuhan kewajiban log
Approval/Reject di CLAUDE.md.

### `SubmissionAttachment`

`submission_id`, `document_label` (harus cocok salah satu `required_documents` template),
`original_filename`, `stored_filename` (UUID), `content_type`, `size_bytes`, `storage_path`.

### `LetterNumberCounter`

`template_id`, `year`, `next_seq` (mulai 1). Unique `(template_id, year)`. Dialokasikan atomik
via `UPDATE ... RETURNING` (lock-free, aman dari race condition dua approval bersamaan).

---

## 3. Approval Workflow Engine

Alur: `Submit → step 0..N-2 (verifikasi bertahap) → step N-1 (Kepala Desa, approve = issuance
otomatis) → ISSUED`. Reject di tahap manapun (dengan catatan wajib) → `REJECTED` (terminal).

**Enforcement:**
1. Endpoint `POST /submissions/{id}/approve` dan `/reject` dijaga permission umum
   `submission:approve`/`submission:reject` (semua tier staf boleh mencoba memanggil).
2. **Service** membandingkan `current_user.role_id` dengan `ApprovalStepConfig` di
   `current_step_index` desa tsb. Tidak cocok → `ForbiddenError` ("Bukan giliran Anda").
   Perbandingan data (`role_id == role_id`), bukan `if role == "..."` — tetap data-driven.
3. Approve pada step bukan-terakhir: `current_step_index += 1`, catat `SubmissionStatusHistory`.
4. Approve pada step terakhir: jalankan **PDF Issuance** (Bagian 5), set `status=ISSUED`.
5. Reject: `status=REJECTED`, simpan `rejection_reason`/`rejected_by_user_id`/`rejected_at`,
   catat history.

---

## 4. Upload Lampiran

`FileStorageService` — abstraksi kecil: `save(bytes, filename) -> path`,
`read(path) -> bytes`. Implementasi **local disk** sekarang (`storage/attachments/`,
di-gitignore), siap diganti ke Cloudflare R2 nanti tanpa mengubah kode pemanggil (CLAUDE.md:
"Object Storage ready").

Validasi saat upload: ukuran maks 5MB, mime type JPG/PNG/PDF, rename ke UUID filename.
`POST /submissions/{id}/attachments` (multipart), `document_label` harus cocok salah satu
`required_documents` template terkait.

---

## 5. PDF Issuance

Dipicu otomatis saat approve di step terakhir:

1. **Alokasi nomor** — `LetterNumberCounter` atomik untuk `(template_id, tahun_berjalan)`,
   render `numbering_pattern` (dari B1) dengan `seq` sungguhan.
2. **Generate kode verifikasi** — format `{PREFIX_DESA}-{tahun}-{acak}` (mirip
   `KOPO-2026-503119`), unik.
3. **Render PDF sungguhan** via `TemplateRenderService` (B1, sudah di-hardening dari
   SSRF/DoS) — dengan **data submission asli** (bukan sample preview) + tanda tangan visual
   (nama Kepala Desa) + stempel placeholder + **QR code sungguhan** (`qrcode` + Pillow) yang
   meng-encode `{PUBLIC_VERIFY_BASE_URL}/{code}` (base URL dari config/settings).
4. PDF disimpan via `FileStorageService`, path tersimpan di `Submission.pdf_storage_path`.
5. `GET /submissions/{id}/pdf` — unduh, dijaga: pemilik submission atau tier staf.

---

## 6. Verifikasi Publik & Notification Hook

**Verifikasi publik** (tanpa login): `GET /api/v1/public/verify/{code}` — nomor surat, jenis,
atas nama, tanggal terbit, ditandatangani. 404 seragam untuk kode tidak ditemukan (tidak
membedakan format-salah vs tidak-ada, hindari enumerasi).

**Notification hook** — `notify_status_change(submission, event)`, saat ini hanya log (pola
sama seperti OTP dev-log di B1), dipanggil di setiap transisi (submit/approve/reject/issued).
Titik integrasi bersih untuk Fase 8; B2 tidak membangun antrian ARQ.

---

## 7. Permission Baru

| Permission | Role |
|---|---|
| `submission:create` | warga |
| `submission:read` | warga (baca punya sendiri — service filter `submitted_by_user_id`), staf/sekretaris/kades/administrator (baca semua) |
| `submission:approve`, `submission:reject` | staf/sekretaris/kades (giliran divalidasi service) |
| `submission:download` | warga (punya sendiri), staf tier (semua) |
| `approval_config:manage` | administrator (via `"*"`) |

---

## 8. API Surface

- `GET /approval-steps` — lihat konfigurasi tahap approval desa (permission `template:read` tier
  ke atas, sama seperti template — informasi operasional staf).
- `PUT /approval-steps` — ganti seluruh susunan tahap sekaligus (list ordered `role_id`), bukan
  CRUD per-baris — lebih sederhana & atomik untuk konfigurasi yang jarang diubah. Permission
  baru `approval_config:manage` (administrator only, via `"*"`). Ditolak 409 jika ada
  `Submission` PENDING (lihat Bagian 2).
- `POST /submissions` — buat pengajuan (warga, validasi `answers` terhadap `TemplateField`).
- `GET /submissions`, `GET /submissions/{id}` — list/detail (scoped kepemilikan untuk warga).
- `POST /submissions/{id}/attachments` — upload lampiran.
- `POST /submissions/{id}/approve`, `POST /submissions/{id}/reject` — aksi approval.
- `GET /submissions/{id}/history` — timeline `SubmissionStatusHistory`.
- `GET /submissions/{id}/pdf` — unduh PDF (hanya jika ISSUED).
- `GET /api/v1/public/verify/{code}` — verifikasi publik, tanpa auth.

Tidak ada endpoint update/delete untuk `Submission` (sesuai keputusan reject-terminal).

---

## 9. Testing & Definition of Done

- Validasi `answers` terhadap `TemplateField` (required, type, options) saat submit.
- Giliran approval ditegakkan (role salah di step manapun → 403).
- Race-condition nomor urut: dua issuance bersamaan untuk template+tahun sama tidak boleh
  menghasilkan nomor duplikat (test dengan alokasi konkuren).
- Upload lampiran: validasi ukuran/mime, penyimpanan lokal, `document_label` harus cocok
  `required_documents`.
- PDF issuance: nomor asli, kode verifikasi unik, QR ter-embed, file tersimpan.
- Verifikasi publik: kode valid → data benar; kode tidak ada → 404 seragam.
- Reject: catatan wajib, status terminal, tidak ada jalur edit-dan-kirim-ulang.

**Selesai apabila:** warga submit → tervalidasi → staf/sekdes/kades approve berurutan sesuai
config (giliran ditegakkan) → approve terakhir otomatis generate PDF+nomor+QR asli → warga
unduh PDF → siapa saja verifikasi via kode publik tanpa login → reject di tahap manapun
tercatat dengan alasan → seluruh riwayat status tersimpan → seluruh test di atas hijau.

---

## 10. Di luar cakupan (ditunda)

- Infrastruktur notifikasi nyata (WhatsApp/Email, antrian ARQ) — Fase 8.
- Edit & kirim ulang pengajuan yang ditolak — tidak direncanakan (keputusan produk: ajukan baru).
- Tanda tangan digital kriptografis (PKI) — di luar cakupan, ditandai "Future Ready" CLAUDE.md.
- Object storage Cloudflare R2 sungguhan — abstraksi disiapkan, implementasi lokal dulu.
- Dashboard statistik, laporan, audit log terpusat — Fase 9/12/13 (sub-project C/D).
