# Design Spec — SIPADES Backend, Sub-project B1: Letter Template Engine

**Tanggal:** 2026-07-24
**Ruang lingkup:** Fase 4 (Template Surat)
**Status:** Disetujui (design), menunggu implementation plan
**Repo:** `sipades-kopo-api`

---

## 1. Konteks & Keputusan

Sub-project B (Letter Engine, Fase 4-7) dipecah menjadi dua sub-project berurutan:

| Sub-project | Fase | Cakupan |
|---|---|---|
| **B1 — Template & Definisi Surat** | 4 | Model template dinamis: field, validasi, layout PDF, format nomor. Berdiri sendiri (data konfigurasi, belum ada transaksi). |
| **B2 — Pengajuan, Approval & PDF** | 5-7 | Submission engine yang memvalidasi terhadap template B1, state machine approval configurable, generate PDF+QR saat terbit. |

Dokumen ini hanya mencakup **B1**. Alasan pemisahan: template harus ada dan stabil sebelum ada
yang bisa disubmit terhadapnya — mengikuti urutan pembangunan alami, mengurangi ukuran plan
per iterasi (pola yang terbukti berhasil pada Foundation: 21 task/6 bundle).

### Keputusan desain kunci

- **Redaksi surat (badan surat) 11 jenis surat ditulis generik oleh Claude** sebagai draf awal
  ala format surat keterangan pemerintah desa Indonesia standar, memakai placeholder Jinja2
  (`{{nama}}`, `{{nik}}`, dst). Admin dapat mengedit lewat Template Builder di masa depan.
  Bukan redaksi resmi final Desa Kopo — starting point yang wajar untuk sistem baru.
- **`TemplateField` sebagai tabel terpisah**, bukan kolom JSONB pada `LetterTemplate`. UI
  Template Builder butuh CRUD per-field + reorder (drag-and-drop); tabel relasional membuat
  operasi "tambah satu field" atau "ubah urutan" jadi query sederhana & aman dari race
  condition, dibanding read-modify-write satu blob JSON besar.
- **Format nomor surat hanya definisi pola**, bukan counter berjalan. `numbering_pattern`
  menyimpan string berplaceholder (`{prefix}`, `{seq}`, `{year}`); alokasi nomor urut
  sesungguhnya (bertambah tiap surat terbit, reset tahunan) adalah tanggung jawab **B2**
  karena terikat ke peristiwa penerbitan, bukan definisi template.
- **Preview PDF nyata (bukan cuma HTML)** di-endpoint B1, memakai WeasyPrint (sudah ter-install
  sejak Foundation). Fungsi render ini didesain untuk dipakai ulang B2 saat generate surat
  sungguhan atas submission yang disetujui.
- **11 template di-seed dari `mockData.js`** (`suratTypes`) — field, ikon, warna, syarat
  lampiran, prefix nomor ditranskripsi persis dari frontend; badan surat memakai redaksi
  generik di atas. Melanjutkan pola seeding-dari-mockData yang sudah dipakai di Foundation.
- **RBAC:** `template:manage` (mutasi — khusus role **administrator**, sesuai tabel role PRD:
  "Administrator | Pengelola sistem | ... Template Surat"), `template:read` (baca — semua role
  staf: staf/sekretaris/kades/administrator, agar bisa melihat definisi form).

---

## 2. Arsitektur & Model Data

Mengikuti pola Clean Architecture yang sama dengan Foundation: `router → service → repository →
model`, Pydantic v2 di tepi, DI untuk session/current-user/permission, response envelope
konsisten, `BaseRepository` yang sudah ada dipakai ulang.

### `LetterTemplate`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID PK | |
| `village_id` | FK → villages.id | Tenant-scoped |
| `code` | str, unik per village | Slug, mis. `domisili` |
| `name` | str | Nama tampil, mis. "Surat Domisili" |
| `description` | str, nullable | |
| `icon` | str | Nama ikon Material Symbols (frontend) |
| `color_bg` / `color_fg` | str | Warna kosmetik, dari `suratTypes.bg/fg` |
| `is_active` | bool, default True | Draft vs aktif (dipakai warga) |
| `required_documents` | JSON `list[str]` | Nama lampiran wajib, dari `suratTypes.syarat` |
| `numbering_prefix` | str | Kode klasifikasi, mis. `"474"` |
| `numbering_pattern` | str | Pola format, mis. `"{prefix}/{seq}/Ds.Kopo/{year}"` |
| `pdf_body_template` | text | Badan surat HTML+Jinja2 |
| `created_at`/`updated_at`/`deleted_at` | | Mixin standar |

### `TemplateField`

| Kolom | Tipe | Keterangan |
|---|---|---|
| `id` | UUID PK | |
| `template_id` | FK → letter_templates.id | |
| `order_index` | int | Urutan tampil/reorder |
| `field_key` | str | Slug dipakai di data submission (B2) & placeholder PDF |
| `label` | str | Label tampil di form |
| `field_type` | enum: text/number/select/date/textarea | |
| `options` | JSON `list[str]`, nullable | Hanya untuk `select` |
| `placeholder` | str, nullable | |
| `is_required` | bool | |
| `validation_rules` | JSON, nullable | `{min_length, max_length, min, max, pattern}` |
| `created_at`/`updated_at`/`deleted_at` | | Mixin standar |

Constraint: `(template_id, field_key)` unik; `(template_id, order_index)` unik di antara
field non-soft-deleted.

---

## 3. API

Prefix `/api/v1/templates`.

| Method | Path | Permission | Keterangan |
|---|---|---|---|
| POST | `/templates` | `template:manage` | Buat template baru |
| GET | `/templates` | `template:read` | List + pagination + filter `is_active` + search nama |
| GET | `/templates/{id}` | `template:read` | Detail + daftar field terurut |
| PUT | `/templates/{id}` | `template:manage` | Update metadata template |
| DELETE | `/templates/{id}` | `template:manage` | Soft-delete |
| POST | `/templates/{id}/fields` | `template:manage` | Tambah field (auto order_index di akhir) |
| PUT | `/templates/{id}/fields/{field_id}` | `template:manage` | Update satu field |
| DELETE | `/templates/{id}/fields/{field_id}` | `template:manage` | Hapus field (soft-delete) |
| PUT | `/templates/{id}/fields/reorder` | `template:manage` | Terima urutan `field_id` baru, tulis ulang `order_index` |
| GET | `/templates/{id}/preview` | `template:read` | Render PDF asli (StreamingResponse, `application/pdf`), tidak menyimpan apa pun |

Semua endpoint non-preview memakai `response_model=Envelope[...]` (list pakai `Envelope[Page[...]]`),
konsisten dengan pola Foundation.

---

## 4. Preview PDF

`TemplateRenderService.render_preview(template)`:

1. Bangun data contoh otomatis dari tiap `TemplateField` — nilai contoh diturunkan dari
   `label`/`placeholder` field (mis. field "Nama Bayi" → `"Nama Bayi (Contoh)"`; field number →
   angka dummy; field select → opsi pertama). Data diri pemohon juga diisi contoh (mis. "Siti
   Rohmah (Contoh)", NIK dummy).
2. Interpolasi `pdf_body_template` via Jinja2 **sandboxed** (`jinja2.sandbox.SandboxedEnvironment`)
   — mencegah eksekusi kode arbitrer bila admin salah ketik/menyalahgunakan syntax template.
3. Bungkus hasil interpolasi dengan kop-surat bersama (nama desa, kecamatan, kabupaten dari
   `Village`, judul surat, blok tanda tangan placeholder — bukan tanda tangan digital
   sungguhan, itu cakupan B2/Fase 7).
4. Render HTML gabungan ke PDF via WeasyPrint, kembalikan bytes.

Fungsi ini murni sinkron dari sisi request (tanpa antrian) karena hanya dipanggil manual oleh
admin saat mendesain template — volume rendah, beda dengan generate PDF surat resmi massal
(B2) yang lewat ARQ.

---

## 5. Seeding

Dari `mockData.js` `suratTypes` (11 entri) + `NOMOR_PREFIX`: setiap entri menjadi satu
`LetterTemplate` (code=`suratTypes[i].id`, name, icon, color_bg/fg, required_documents=`syarat`,
numbering_prefix dari `NOMOR_PREFIX`, numbering_pattern=`"{prefix}/{seq}/Ds.Kopo/{year}"`) dan
`fields[]`-nya menjadi baris `TemplateField` terurut. `pdf_body_template` diisi redaksi generik
per jenis surat (ditulis saat implementasi, disimpan sebagai konstanta seed data seperti pola
`app/seed/data.py` di Foundation). Idempoten (re-seed tidak duplikat), mengikuti pola
`seed_master`/`seed_rbac` yang sudah ada.

---

## 6. Testing & Definition of Done

- Test CRUD template (create/list/get/update/delete) + response_model + pagination/filter/search.
- Test CRUD field + reorder (urutan tersimpan benar, `order_index` unik terjaga).
- Test permission: role non-administrator mendapat 403 pada endpoint `template:manage`;
  semua role staf bisa `GET` (template:read).
- Test preview: endpoint mengembalikan bytes PDF valid (`%PDF` magic bytes) untuk minimal satu
  template dengan field campuran (text/number/select).
- Test seed idempoten: re-run tidak menduplikasi 11 template.

**Selesai apabila:** seluruh endpoint di atas berjalan + tervalidasi + ber-response_model,
11 template ter-seed dengan redaksi generik dan bisa di-preview jadi PDF asli, RBAC
administrator-only untuk mutasi berfungsi, dan seluruh test hijau.

---

## 7. Di luar cakupan (ditunda ke B2 atau lebih jauh)

- Submission/pengajuan surat, validasi runtime terhadap `TemplateField.validation_rules`.
- Alokasi nomor urut sesungguhnya (counter, reset tahunan) — hanya *format*-nya di B1.
- Approval workflow configurable (step, role approver per step).
- Generate PDF surat resmi atas submission (tanda tangan digital, stempel, QR verifikasi
  sungguhan, penomoran final).
- Versi/snapshot template saat submission dibuat (agar edit template tidak mengubah surat yang
  sudah dalam proses) — perlu dipikirkan ulang saat mendesain B2, di luar cakupan B1.
- Redaksi resmi final dari Desa Kopo (saat ini masih draf generik).
