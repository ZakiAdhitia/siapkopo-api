"""Seed data for the 9 letter templates, transcribed from mockData.js suratTypes.

Each entry's ``fields`` list holds tuples:
(field_key, label, field_type, options, placeholder, is_required, validation_rules)
"""

# Conditional Sub-Category Form for KK (Bagian 4.2, STRATEGI doc), rev.
# 2026-08-06 per HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md's "Kartu Keluarga"
# section item 2: each category now lists its OWN complete, granular set of
# attachments (no more shared `_KK_WAJIB` base folded into every category --
# each list below is self-contained, e.g. "KK Lama Suami"/"KK Lama Istri"
# as two separate upload slots instead of one combined "kedua belah pihak"
# item, matching the same per-person unbundling pattern already used for
# NA's attachments). `_KK_WAJIB` now only serves as the template-level
# fallback `required_documents` shown before a category is picked.
#
# "KK Rusak atau Hilang" (ALUR_PENGISIAN_KK.md bagian C.4) is one
# `status_perubahan` form-category with a JIKA RUSAK / JIKA HILANG
# attachment split -- rather than inventing a second-level category field,
# it's split into two distinct `status_perubahan` options ("KK Rusak" /
# "KK Hilang") so the existing single-level `category_field_key` mechanism
# still applies unchanged.
_KK_WAJIB = [
    "Kartu Keluarga (KK) Asli yang Lama",
    "Foto KTP-el Seluruh Anggota Keluarga yang Akan Terdaftar",
]
KK_CATEGORY_DOCS: dict[str, list[str]] = {
    "Baru Menikah (Pecah KK Mandiri)": [
        "Foto Buku Nikah / Akta Perkawinan",
        "Foto KK Lama Suami",
        "Foto KK Lama Istri",
        "Foto KTP-el Suami",
        "Foto KTP-el Istri",
    ],
    "Ada Kelahiran Anak (Penambahan Anggota)": [
        "Foto KK Lama yang Aktif",
        "Foto Surat Keterangan Kelahiran",
        "Foto Buku Nikah / Akta Perkawinan",
        "Foto KTP-el Istri",
        "Foto KTP-el Suami",
    ],
    "Anggota Keluarga Meninggal Dunia (Pengurangan Anggota)": [
        "Foto KK Lama yang Aktif",
        "Foto Surat Keterangan Kematian",
        "Foto KTP-el Asli Jenazah (jika masih ada)",
        "Foto KTP-el Asli Pelapor/Anggota Keluarga",
    ],
    "KK Rusak": [
        "Foto Fisik Lembar KK Lama yang Rusak",
        "Foto KTP-el Kepala Keluarga (Asli)",
    ],
    "KK Hilang": [
        "Foto Surat Keterangan Kehilangan dari Polsek Setempat",
        "Fotokopi KK Lama yang Hilang (jika ada)",
        "Foto KTP-el Kepala Keluarga",
    ],
    "Cerai Hidup (Pecah KK Mandiri Pasca Perceraian)": [
        "Foto Akta/Surat Cerai",
        "Foto KK Lama yang Masih Bergabung",
        # ALUR_PENGISIAN_KK.md bagian C.5 juga mewajibkan ini; HASIL_UJICOBA's
        # 2-item list untuk kategori ini kemungkinan cuma ringkasan, bukan
        # instruksi menghapus -- dipertahankan sesuai PRD (CLAUDE.md: PRD
        # adalah sumber kebenaran utama saat ada konflik).
        "Foto KTP-el Pemohon (Asli)",
    ],
}

# Conditional Sub-Category Form for Ubah Data (ALUR_PENGAJUAN_UBAH_DATA.md,
# added 2026-08-03): "Nama" changes need an Akta Kelahiran specifically
# (Bagian C.2); every other elemen just needs "dokumen pendukung sesuai
# jenis perubahan" (Bagian C.1) -- an Ijazah for Pendidikan, a Surat
# Keterangan Kerja for Pekerjaan, etc. Same category_field_key mechanism
# already used by "kk" above.
_UBAH_DATA_WAJIB = ["Foto KK Lama yang Aktif (Asli)", "Foto KTP-el Asli"]
UBAH_DATA_CATEGORY_DOCS: dict[str, list[str]] = {
    "Nama": _UBAH_DATA_WAJIB + ["Foto Akta Kelahiran (Asli)"],
    "Status Perkawinan": _UBAH_DATA_WAJIB + [
        "Dokumen Pendukung Sesuai Jenis Perubahan (mis. Buku Nikah/Akta Cerai)",
    ],
    "Pekerjaan": _UBAH_DATA_WAJIB + [
        "Dokumen Pendukung Sesuai Jenis Perubahan (mis. Surat Keterangan Kerja)",
    ],
    "Pendidikan": _UBAH_DATA_WAJIB + [
        "Dokumen Pendukung Sesuai Jenis Perubahan (mis. Ijazah Terakhir)",
    ],
    "Agama": _UBAH_DATA_WAJIB + ["Dokumen Pendukung Sesuai Jenis Perubahan"],
    "Golongan Darah": _UBAH_DATA_WAJIB + [
        "Dokumen Pendukung Sesuai Jenis Perubahan (mis. Surat Keterangan Dokter)",
    ],
    "Elemen Data Kependudukan Lainnya": _UBAH_DATA_WAJIB + [
        "Dokumen Pendukung Sesuai Jenis Perubahan",
    ],
}

# Surat Pindah (F-1.03) restructure, 06/08/2026 per
# HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md + ALUR_PENGISIAN_SURAT_PINDAH.md: the
# real F-1.03 specimen's "11. Daftar Anggota Keluarga Yang Pindah" table has
# exactly 7 numbered rows, so that's the hard cap here -- each slot is 3
# flat fields (nik/nama/shdk), shown/required only up to whatever
# `anggota_yang_ikut` is currently set to (show_when, same generic
# conditional-field mechanism as NA's Duda/Janda group), mirroring SKTM's
# existing nik_2..nik_10 flat-numbered-slot convention rather than inventing
# a new nested/list answer shape (the whole system's `answers` stays a flat
# dict everywhere else).
_PINDAH_MAX_ANGGOTA = 7
_SHDK_OPTIONS = [
    "Suami", "Istri", "Anak", "Orang Tua", "Mertua", "Menantu", "Cucu", "Famili Lain",
]


def _pindah_anggota_fields() -> list[tuple]:
    fields: list[tuple] = []
    for n in range(1, _PINDAH_MAX_ANGGOTA + 1):
        show_when = {"show_when": {
            "field": "anggota_yang_ikut",
            "in": [str(i) for i in range(n, _PINDAH_MAX_ANGGOTA + 1)],
        }}
        fields += [
            (f"anggota_{n}_nik", "NIK", "text", None, "16 digit NIK", True, show_when),
            (f"anggota_{n}_nama", "Nama Lengkap", "text", None, "nama sesuai KTP", True, show_when),
            (f"anggota_{n}_shdk", "SHDK (Status Hubungan dalam Keluarga)", "select",
             _SHDK_OPTIONS, None, True, show_when),
        ]
    return fields


# Dynamic KTP-per-anggota attachment count (item 1, 06/08/2026): reuses the
# EXISTING Conditional Sub-Category Form mechanism (`category_field_key`/
# `required_documents_by_category`, built for KK's 5 permohonan categories)
# with `anggota_yang_ikut`'s own value AS the category -- no new backend
# mechanism needed. Base `required_documents` (below, "0 anggota" / Kepala
# Keluarga sendirian case, category field hidden+absent) always has KK +
# the pemohon's own KTP; each additional anggota adds one more named slot.
PINDAH_CATEGORY_DOCS: dict[str, list[str]] = {
    str(n): ["KK", "Foto KTP Pemohon"] + [
        f"Foto KTP Anggota Keluarga {i}" for i in range(1, n + 1)
    ]
    for n in range(0, _PINDAH_MAX_ANGGOTA + 1)
}

# NA (Pengantar Nikah) attachment restructure, 06/08/2026: the old single
# bundled "KTP & KK Calon + Ortu" item is unbundled into the 8 separate
# items ALUR_PENGISIAN_NA.md/HASIL_UJICOBA_PENGAJUAN_PER_SURAT.md's
# "Lampiran" list both spell out explicitly (Calon Suami/Calon Istri fixed
# labels, not "pemohon"/"pasangan" -- matches the spec's own wording,
# regardless of which side of the couple is the actual online applicant).
# "Izin Ortu" is dropped from required_documents entirely -- it's an
# OUTPUT document (N.5, generated by this system), not something a warga
# uploads as evidence; keeping it there was conflating the two. Akta
# Kematian/Cerai now scale with `sebab_cerai` via the same
# category_field_key mechanism as Pindah/KK, instead of one always-shown
# generic "Akta Cerai (jika Duda/Janda)" line.
_NA_WAJIB = [
    "Foto KTP Calon Suami", "Foto KK Calon Suami",
    "Foto KTP Ibu Calon Suami", "Foto KTP Ayah Calon Suami",
    "Foto KTP Calon Istri", "Foto KK Calon Istri",
    "Foto KTP Ibu Calon Istri", "Foto KTP Ayah Calon Istri",
]
NA_CATEGORY_DOCS: dict[str, list[str]] = {
    "Cerai Mati": _NA_WAJIB + ["Foto Akta Kematian Mantan Suami/Istri Terdahulu"],
    "Cerai Hidup": _NA_WAJIB + ["Foto Akta Cerai dari Pengadilan Agama/Pengadilan Negeri"],
}

SURAT_TEMPLATES: list[dict] = [
    {
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Usulan cetak / perubahan KK (format F1.02/F1.06)",
        "required_documents": _KK_WAJIB,
        "category_field_key": "status_perubahan",
        "required_documents_by_category": KK_CATEGORY_DOCS,
        "numbering_prefix": "474",
        "output_category": "dukcapil_pengantar",
        "is_active": True,
        "fields": [
            # "Jumlah Anggota Keluarga" dan "Keterangan Perubahan" dihapus
            # (06/08/2026, HASIL_UJICOBA item "Kartu Keluarga" #1) -- status
            # perubahan sudah cukup menentukan alur & lampiran, dua field
            # ini tidak menambah informasi yang staff/Dukcapil butuhkan.
            ("status_perubahan", "Status Perubahan", "select",
             list(KK_CATEGORY_DOCS.keys()), None, True, None),
        ],
        # F-1.02 "Formulir Pendaftaran Peristiwa Kependudukan" (ALUR_PENGISIAN_KK.md
        # bagian B): a registration form the citizen brings to Dukcapil, not a
        # Kepala-Desa-signed keterangan. 06/08/2026 (Tambahan): now rendered
        # from the real specimen (template_file/KK-Pengajuan/KK_TEMPLATE.docx)
        # via the docx pipeline (_docx_engine.py) -- this pdf_body_template
        # string is dead code, same precedent as domisili/lahir/mati/etc,
        # kept only as the KKRenderer/_kk.py HTML fallback's source.
        "pdf_body_template": (
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>N a m a</td><td style='width:4%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:2px 0;'>No. KK Lama</td><td>:</td><td>{{ no_kk or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat or '-' }} RT. {{ rt or '-' }} RW. {{ rw or '-' }} Desa {{ village_name }}<br>"
            "Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p>Dengan ini mengajukan pendaftaran peristiwa kependudukan sebagai berikut:</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Jenis Peristiwa</td><td style='width:4%;'>:</td><td><b>{{ status_perubahan }}</b></td></tr>"
            "</table>"
            "<p>Pemohon menyatakan data di atas benar dan bersedia melengkapi berkas pendukung "
            "sesuai jenis peristiwa yang diajukan sebagaimana disyaratkan Desa {{ village_name }}, "
            "untuk selanjutnya diproses lebih lanjut oleh Dinas Kependudukan dan Catatan Sipil.</p>"
        ),
    },
    {
        "code": "domisili", "name": "Surat Domisili", "icon": "home_pin",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Keterangan tempat tinggal domisili (tinggal sementara)",
        # Surat Pengantar RT/RW dihapus dari syarat (2026-08-02, instruksi user).
        "required_documents": ["KTP", "KK"],
        "numbering_prefix": "470",
        "numbering_pattern": "{prefix}/{seq}/Pem",
        "output_category": "desa_direct",
        "is_active": True,
        # 2026-08-05 TAMBAHAN item 6: every field is now warga-input at
        # submission time (was: alamat asal/masa berlaku deferred to staff
        # via is_staff_only, completed later at the detail page) -- the
        # two-tier "Data Pemohon" (staff) vs "Data Formulir" (warga) split
        # is retired; staff now only crosschecks what the warga already
        # filled in before approving.
        "fields": [
            ("alamat_asal", "Alamat Asal (KTP/KK)", "text", None, "Kampung / Jalan", True, None),
            ("rt_asal", "RT Asal", "text", None, "mis. 003", True, None),
            ("rw_asal", "RW Asal", "text", None, "mis. 005", True, None),
            ("kel_desa_asal", "Desa/Kelurahan Asal", "text", None, "mis. Citeko", True, None),
            ("kec_asal", "Kecamatan Asal", "text", None, "mis. Cisarua", True, None),
            ("kab_kota_asal", "Kabupaten/Kota Asal", "text", None, "mis. Bogor", True, None),
            ("provinsi_asal", "Provinsi Asal", "text", None, "mis. Jawa Barat", True, None),
            ("alamat_domisili", "Alamat Domisili Saat Ini", "text", None, "Kampung / Dusun di Desa Kopo", True, None),
            ("rt_domisili", "RT Domisili", "text", None, "mis. 001", True, None),
            ("rw_domisili", "RW Domisili", "text", None, "mis. 007", True, None),
            ("keperluan", "Keperluan Surat", "text", None, "mis. Identitas Diri / Administrasi Sekolah", True, None),
            ("masa_berlaku_bulan", "Masa Berlaku (Bulan)", "select", ["1 Bulan", "2 Bulan", "3 Bulan", "6 Bulan"], None, True, None),
        ],
        # Mirrors 2025 DOMISILI/DOMISILI.doc ("KETERANGAN TINGGAL SEMENTARA")
        # field-for-field and paragraph-for-paragraph.
        "pdf_body_template": (
            "<p>Yang bertanda tangan dibawah ini Kepala Desa {{ village_name }} Kecamatan {{ kecamatan }} "
            "Kabupaten {{ kabupaten }}, dengan ini menerangkan bahwa :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>N a m a</td><td style='width:4%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Jenis Kelamin</td><td>:</td><td>{{ jk or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Tempat, Tgl lahir</td><td>:</td><td>{{ tempat_lahir or '-' }}, {{ tanggal_lahir|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Status</td><td>:</td><td>{{ status_kawin or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat lengkap</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat_asal }} RT. {{ rt_asal }} RW. {{ rw_asal }}<br>"
            "Kel./Desa {{ kel_desa_asal }}<br>"
            "Kecamatan {{ kec_asal }}<br>"
            "Kabupaten/Kota {{ kab_kota_asal }}<br>"
            "Provinsi {{ provinsi_asal }}.</td></tr>"
            "</table>"
            "<p>Nama tersebut diatas adalah benar pada saat ini yang bersangkutan berdomisili di "
            "{{ alamat_domisili }} RT. {{ rt_domisili }} RW. {{ rw_domisili }} Desa {{ village_name }} "
            "Kecamatan {{ kecamatan }}, Kabupaten {{ kabupaten }}.</p>"
            "<p>Surat keterangan ini kami buat atas permintaan yang bersangkutan guna pelengkap "
            "persyaratan : ---{{ keperluan }}---</p>"
            "<p>Demikian Surat keterangan Domisili ini dibuat dengan sebenarnya, kepada instansi yang "
            "terkait agar menjadi tahu serta maklum adanya.</p>"
            "<p><b>Berlaku Sampai Dengan Tanggal : {{ berlaku }}</b></p>"
        ),
    },
    {
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "description": "Surat Keterangan Usaha warga",
        # PERBAIKAN_INPUT_DAN_LAMPIRAN_SURAT.MD Bagian 1.2 (2026-08-02):
        # KTP+KK jadi satu lampiran gabungan, Surat Pengantar RT/RW dihapus
        # dari syarat.
        "required_documents": ["Foto KK/KTP"],
        "numbering_prefix": "500",
        "numbering_pattern": "{prefix}/{seq}/Ekonomi",
        "output_category": "desa_direct",
        "is_active": True,
        "fields": [
            ("jenis_usaha", "Jenis Usaha", "text", None, "mis. Warung Sembako / Bengkel Steam", True, None),
            ("lokasi_usaha", "Lokasi Usaha", "text", None, "mis. Kp. Kopo", True, None),
            ("rt_usaha", "RT Lokasi Usaha", "text", None, "mis. 003", True, None),
            ("rw_usaha", "RW Lokasi Usaha", "text", None, "mis. 005", True, None),
            ("desa_usaha", "Desa Lokasi Usaha", "text", None, "mis. Kopo", True, None),
            ("keperluan_usaha", "Keperluan Pengajuan", "select", ["Pengajuan Kredit Bank", "Pengajuan UMKM", "Administrasi BPJS Ketenagakerjaan", "Pengajuan Pinjaman", "Lainnya"], None, True, None),
        ],
        # Mirrors 2025 SKU/SKU.doc ("SURAT KETERANGAN USAHA") field order.
        "pdf_body_template": (
            "<p>Yang bertandatangan dibawah ini Kepala Desa {{ village_name }} Kecamatan {{ kecamatan }} "
            "Kabupaten {{ kabupaten }}, menerangkan bahwa :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>N a m a</td><td style='width:4%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Tempat, Tgl lahir</td><td>:</td><td>{{ tempat_lahir or '-' }}, {{ tanggal_lahir|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Jenis Kelamin</td><td>:</td><td>{{ jk or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Status</td><td>:</td><td>{{ status_kawin or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat lengkap</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat or '-' }} RT. {{ rt or '-' }} RW. {{ rw or '-' }} Desa {{ village_name }}<br>"
            "Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p>Nama tersebut diatas adalah benar warga yang beralamatkan sebagaimana tersebut diatas, dan "
            "berdasarkan pengakuannya yang bersangkutan benar mempunyai usaha :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Jenis Usaha</td><td style='width:4%;'>:</td><td><b>{{ jenis_usaha|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Lokasi Usaha</td><td style='vertical-align:top;'>:</td><td>"
            "{{ lokasi_usaha }} RT. {{ rt_usaha }} RW. {{ rw_usaha }} Desa {{ desa_usaha }}<br>"
            "Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p>Surat Keterangan ini kami berikan atas permintaan yang bersangkutan guna pelengkap "
            "Persyaratan : {{ keperluan_usaha }}</p>"
            "<p>Demikian Surat keterangan ini kami buat dengan sebenar-benarnya, untuk dipergunakan "
            "sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "lahir", "name": "Ket. Kelahiran", "icon": "child_friendly",
        "color_bg": "#FFF1F4", "color_fg": "#C93B6A",
        "description": "Surat Keterangan Kelahiran Anak",
        # PERBAIKAN_INPUT_DAN_LAMPIRAN_SURAT.MD Bagian 2.2 (2026-08-02): KTP
        # Orang Tua dan Buku Nikah dihapus dari syarat, foto kedua orang tua
        # (bukan scan KTP) jadi lampiran baru, surat bidan jadi opsional.
        "required_documents": ["Foto KK", "Foto Kedua Orang Tua Anak"],
        "optional_documents": ["Surat Keterangan Kelahiran dari Bidan (Bila Ada)"],
        "numbering_prefix": "474.1",
        "numbering_pattern": "{prefix}/{seq}/Pem",
        "output_category": "dukcapil_pengantar",
        "is_active": True,
        # 2026-08-05 TAMBAHAN item 6: NIK/TTL/pekerjaan/alamat kedua orang
        # tua are now warga-input and required, same as the other 6 fields
        # (was: is_staff_only, completed later by staff from KK/orang tua
        # photos) -- see the module-level note on "domisili" above.
        "fields": [
            ("nama_anak", "Nama Anak", "text", None, "nama lengkap bayi/anak", True, None),
            ("gender_anak", "Jenis Kelamin Anak", "select", ["Laki-laki", "Perempuan"], None, True, None),
            ("tempat_lahir_anak", "Tempat Lahir Anak", "text", None, "mis. Serang / Rumah Sakit", True, None),
            ("tgl_lahir_anak", "Tanggal Lahir Anak", "date", None, None, True, None),
            ("jam_lahir_anak", "Jam Lahir", "text", None, "mis. 08:30 WIB", True, None),
            ("anak_ke", "Anak Ke-", "text", None, "mis. 1 (Pertama)", True, None),
            ("nama_ayah", "Nama Ayah", "text", None, "nama lengkap ayah kandung", True, None),
            ("nik_ayah", "NIK Ayah", "text", None, "16 digit NIK ayah", True, None),
            ("tempat_lahir_ayah", "Tempat Lahir Ayah", "text", None, "mis. Bogor", True, None),
            ("tanggal_lahir_ayah", "Tanggal Lahir Ayah", "date", None, None, True, None),
            ("pekerjaan_ayah", "Pekerjaan Ayah", "text", None, "mis. Wiraswasta", True, None),
            ("alamat_ayah", "Alamat Ayah", "text", None, "Kampung / Jalan", True, None),
            ("rt_ayah", "RT Ayah", "text", None, "mis. 003", True, None),
            ("rw_ayah", "RW Ayah", "text", None, "mis. 012", True, None),
            ("nama_ibu", "Nama Ibu", "text", None, "nama lengkap ibu kandung", True, None),
            ("nik_ibu", "NIK Ibu", "text", None, "16 digit NIK ibu", True, None),
            ("tempat_lahir_ibu", "Tempat Lahir Ibu", "text", None, "mis. Bogor", True, None),
            ("tanggal_lahir_ibu", "Tanggal Lahir Ibu", "date", None, None, True, None),
            ("pekerjaan_ibu", "Pekerjaan Ibu", "text", None, "mis. Mengurus Rumah Tangga", True, None),
            ("alamat_ibu", "Alamat Ibu", "text", None, "Kampung / Jalan", True, None),
            ("rt_ibu", "RT Ibu", "text", None, "mis. 003", True, None),
            ("rw_ibu", "RW Ibu", "text", None, "mis. 012", True, None),
        ],
        # Mirrors 2025 KELAHIRAN/KELAHIRAN.docx ("SURAT KETERANGAN KELAHIRAN").
        "pdf_body_template": (
            "<p>Yang bertandatangan dibawah ini, Kepala Desa {{ village_name }} Kecamatan {{ kecamatan }} "
            "Kabupaten {{ kabupaten }}, menerangkan bahwa berdasarkan buku induk kependudukan yang ada pada "
            "kami terdaftar seorang : ---{{ gender_anak }}--- :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:28%; padding:2px 0;'>Bernama</td><td style='width:4%;'>:</td><td><b>{{ nama_anak|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Adalah Anak ke</td><td>:</td><td>{{ anak_ke }}</td></tr>"
            "</table>"
            "<p>Dari</p>"
            "<p style='font-weight:bold; text-decoration:underline;'>A Y A H</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:28%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama_ayah|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Tempat, Tgl Lahir</td><td>:</td><td>{{ tempat_lahir_ayah }}, {{ tanggal_lahir_ayah|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan_ayah }}</td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik_ayah }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat_ayah }} RT. {{ rt_ayah }} RW. {{ rw_ayah }} Desa {{ village_name }}<br>"
            "Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p style='font-weight:bold; text-decoration:underline;'>I B U</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:28%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama_ibu|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Tempat, Tgl Lahir</td><td>:</td><td>{{ tempat_lahir_ibu }}, {{ tanggal_lahir_ibu|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan_ibu }}</td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik_ibu }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat_ibu }} RT. {{ rt_ibu }} RW. {{ rw_ibu }} Desa {{ village_name }}<br>"
            "Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p>Nama tersebut diatas benar-benar dilahirkan di -----{{ tempat_lahir_anak }}----- "
            "Pada hari ---{{ tgl_lahir_anak|hari_indonesia }}--- Tanggal ---{{ tgl_lahir_anak|ddmmyyyy }}--- Jam {{ jam_lahir_anak }} Wib</p>"
            "<p>Demikian Surat Keterangan Kelahiran ini dibuat dengan penuh rasa tanggung jawab atas kebenarannya.</p>"
        ),
    },
    {
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "description": "Surat Keterangan Kematian Penduduk",
        # PERBAIKAN_INPUT_DAN_LAMPIRAN_SURAT.MD Bagian 3.2 (2026-08-02): surat
        # dokter/RS jadi opsional, label KTP/KK dirapikan.
        "required_documents": ["Foto KTP (Almarhum/Almarhumah)", "Foto KK (Almarhum/Almarhumah)"],
        "optional_documents": ["Surat Kematian dari Dokter (Bila Ada)"],
        "numbering_prefix": "472",
        "numbering_pattern": "{prefix}/{seq}/Pem",
        "output_category": "dukcapil_pengantar",
        "is_active": True,
        # 2026-08-05 TAMBAHAN item 6: NIK and the rest are now warga-input
        # (was: is_staff_only, completed later by staff from KTP/KK photos)
        # -- see the module-level note on "domisili" above. TTL/usia_tahun
        # stay optional (not "staff will fill it in" but a genuine
        # either/or: exact tanggal lahir OR an approximate usia, whichever
        # the reporting family member actually knows).
        "fields": [
            ("nama_almarhum", "Nama Almarhum / Almarhumah", "text", None, "nama lengkap almarhum", True, None),
            ("jk_almarhum", "Jenis Kelamin", "select", ["Laki-laki", "Perempuan"], None, True, None),
            ("tempat_lahir_almarhum", "Tempat Lahir (jika diketahui)", "text", None, "mis. Bogor", False, None),
            ("tanggal_lahir_almarhum", "Tanggal Lahir (jika diketahui)", "date", None, None, False, None),
            ("usia_tahun", "Usia Saat Meninggal (Tahun, jika TTL tidak diketahui)", "number", None, "mis. 64", False, None),
            ("pekerjaan_almarhum", "Pekerjaan", "text", None, "mis. Buruh Harian Lepas", True, None),
            ("alamat_almarhum", "Alamat", "text", None, "Kampung / Jalan", True, None),
            ("rt_almarhum", "RT", "text", None, "mis. 002", True, None),
            ("rw_almarhum", "RW", "text", None, "mis. 011", True, None),
            ("nik_almarhum", "NIK Almarhum", "text", None, "16 digit NIK", True, None),
            ("tgl_meninggal", "Tanggal Meninggal", "date", None, None, True, None),
            ("jam_meninggal", "Jam Meninggal", "text", None, "mis. 14:15 WIB", True, None),
            ("tempat_meninggal", "Tempat Meninggal", "select", ["Rumah Domisili", "Rumah Sakit", "Puskesmas", "Lainnya"], None, True, None),
            ("sebab_meninggal", "Sebab Kematian", "text", None, "mis. Sakit Biasa / Usia Lanjut", True, None),
        ],
        # Mirrors 2025 KEMATIAN/KEMATIAN.docx ("SURAT KEMATIAN").
        "pdf_body_template": (
            "<p>Yang bertanda tangan dibawah ini Kepala Desa {{ village_name }} Kecamatan {{ kecamatan }} "
            "Kabupaten {{ kabupaten }}, menerangkan bahwa :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:30%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama_almarhum|upper }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Jenis kelamin</td><td>:</td><td>{{ jk_almarhum or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0;'>TTL/Usia</td><td>:</td><td>"
            "{% if tanggal_lahir_almarhum %}{{ tempat_lahir_almarhum or '-' }}, {{ tanggal_lahir_almarhum|ddmmyyyy }}"
            "{% elif usia_tahun %}{{ usia_tahun }} Tahun{% else %}-{% endif %}</td></tr>"
            "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan_almarhum or '-' }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
            "{{ alamat_almarhum }} RT. {{ rt_almarhum }} RW. {{ rw_almarhum }}<br>"
            "Desa {{ village_name }} Kecamatan {{ kecamatan }}<br>"
            "Kabupaten {{ kabupaten }}.</td></tr>"
            "</table>"
            "<p>TELAH MENINGGAL DUNIA pada :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:30%; padding:2px 0;'>Hari</td><td style='width:4%;'>:</td><td>{{ tgl_meninggal|hari_indonesia }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Tanggal</td><td>:</td><td>{{ tgl_meninggal|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Jam</td><td>:</td><td>{{ jam_meninggal }} wib</td></tr>"
            "<tr><td style='padding:2px 0;'>Meninggal di</td><td>:</td><td>{{ tempat_meninggal }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Disebabkan karena</td><td>:</td><td>{{ sebab_meninggal }}</td></tr>"
            "</table>"
            "<p>Surat keterangan ini dibuat atas dasar yang sebenarnya.</p>"
        ),
    },
    {
        "code": "na", "name": "Pengantar Nikah (NA)", "icon": "favorite",
        "color_bg": "#FFF4EC", "color_fg": "#E06D20",
        "description": "Surat Pengantar & Kelengkapan Berkas Nikah (5 Sub-Dokumen)",
        "required_documents": _NA_WAJIB,
        "optional_documents": ["Foto Ijazah/Akte Kelahiran Kedua Calon (Bila Ada)"],
        "category_field_key": "sebab_cerai",
        "required_documents_by_category": NA_CATEGORY_DOCS,
        "numbering_prefix": "474.2",
        "numbering_pattern": "{prefix}/{seq}/Kesra",
        "output_category": "kua_pengantar",
        "post_issuance_note": (
            "Setelah disetujui, unduh kelima dokumen (N.1, N.4, N.5, Ket. Menumpang Nikah, "
            "Ket. Belum Pernah Nikah) dan bawa ke KUA setempat untuk proses pernikahan lebih lanjut."
        ),
        "is_active": True,
        "sub_documents": [
            {"code": "na_n1", "name": "Formulir N.1 (Pengantar Nikah)"},
            {"code": "na_n4", "name": "Formulir N.4 (Persetujuan Pengantin)"},
            {"code": "na_n5", "name": "Formulir N.5 (Izin Orang Tua)"},
            {"code": "na_menumpang", "name": "Surat Ket. Menumpang Nikah"},
            {"code": "na_belum_nikah", "name": "Surat Ket. Belum Pernah Nikah"},
            {"code": "na_n6", "name": "Formulir N.6 (Ket. Kematian Suami/Istri Terdahulu)"},
        ],
        "fields": [
            # Status Pernikahan Calon (item 3, 06/08/2026 -- HASIL_UJICOBA_
            # PENGAJUAN_PER_SURAT.md): right after "Data Pengaju", BEFORE the
            # calon's own identity block, per the explicit new step order.
            # Keputusan akhir (06/08/2026, susulan): Cerai Mati membutuhkan
            # data lengkap pasangan terdahulu (NIK/TTL/pekerjaan/alamat/
            # tanggal-tempat meninggal) karena dipakai N.6; Cerai Hidup tetap
            # cukup nama saja (tidak ada N.6 untuknya). Lihat 8 field
            # `*_pasangan_terdahulu` di bawah, digated ke sebab_cerai=="Cerai
            # Mati" (bukan status_calon) -- ini membalik keputusan sesi
            # sebelumnya hari ini yang sempat menghapus semuanya.
            ("status_calon", "Status Pernikahan Calon", "select", ["Jejaka", "Perawan", "Duda", "Janda"], None, True, None),
            ("jumlah_istri", "Jumlah Istri/Suami Sebelumnya", "text", None, "mis. 1",
             True, {"show_when": {"field": "status_calon", "in": ["Duda", "Janda"]}}),
            ("sebab_cerai", "Sebab Berakhirnya Perkawinan Terdahulu", "select", ["Cerai Mati", "Cerai Hidup"], None,
             True, {"show_when": {"field": "status_calon", "in": ["Duda", "Janda"]}}),
            ("no_akta_cerai", "No. Akta Cerai", "text", None, "mis. 4248/AC/2024/PA.Cbn",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Hidup"]}}),
            ("pasangan_terdahulu", "Nama Suami/Istri Terdahulu", "text", None, "nama pasangan sebelumnya",
             True, {"show_when": {"field": "status_calon", "in": ["Duda", "Janda"]}}),
            # Keputusan akhir (06/08/2026, susulan): untuk Cerai Mati, data
            # pasangan terdahulu TIDAK disederhanakan jadi nama saja --
            # dikembalikan lengkap karena dibutuhkan untuk menerbitkan N.6
            # (Ket. Kematian Suami/Istri Terdahulu). Cerai Hidup tetap nama
            # saja (tidak butuh N.6). Gated ke sebab_cerai, bukan status_calon.
            ("nik_pasangan_terdahulu", "NIK Pasangan Terdahulu", "text", None, "16 digit NIK",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("bin_binti_pasangan_terdahulu", "Bin/Binti Pasangan Terdahulu", "text", None, "mis. Bin Ahmad",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("tempat_lahir_pasangan_terdahulu", "Tempat Lahir Pasangan Terdahulu", "text", None, "mis. Bogor",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("tanggal_lahir_pasangan_terdahulu", "Tanggal Lahir Pasangan Terdahulu", "date", None, None,
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("pekerjaan_pasangan_terdahulu", "Pekerjaan Pasangan Terdahulu (Semasa Hidup)", "text", None, "mis. Guru",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("alamat_pasangan_terdahulu", "Alamat Pasangan Terdahulu (Semasa Hidup)", "text", None, "alamat semasa hidup",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("tanggal_meninggal_pasangan_terdahulu", "Tanggal Meninggal Pasangan Terdahulu", "date", None, None,
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("tempat_meninggal_pasangan_terdahulu", "Tempat Meninggal Pasangan Terdahulu", "text", None, "mis. RSUD Cibinong",
             True, {"show_when": {"field": "sebab_cerai", "in": ["Cerai Mati"]}}),
            ("jk_calon", "Jenis Kelamin Calon", "select", ["Laki-laki", "Perempuan"], None, True, None),
            ("tempat_lahir_calon", "Tempat Lahir Calon", "text", None, "mis. Bogor", True, None),
            ("tanggal_lahir_calon", "Tanggal Lahir Calon", "date", None, None, True, None),
            ("kewarganegaraan", "Kewarganegaraan", "select", ["Indonesia", "Asing"], None, True, None),
            ("agama_calon", "Agama Calon", "text", None, "mis. Islam", True, None),
            ("pekerjaan_calon", "Pekerjaan Calon", "text", None, "mis. Karyawan Swasta", True, None),
            ("alamat_calon", "Alamat Calon", "text", None, "Kampung / Jalan", True, None),
            ("rt_calon", "RT Calon", "text", None, "mis. 003", True, None),
            ("rw_calon", "RW Calon", "text", None, "mis. 012", True, None),
            ("nama_ayah", "Nama Ayah Kandung", "text", None, "nama ayah", True, None),
            ("nik_ayah", "NIK Ayah Kandung", "text", None, "16 digit NIK ayah", True, None),
            ("tempat_lahir_ayah", "Tempat Lahir Ayah", "text", None, "mis. Bogor", True, None),
            ("tanggal_lahir_ayah", "Tanggal Lahir Ayah", "date", None, None, True, None),
            ("pekerjaan_ayah", "Pekerjaan Ayah", "text", None, "mis. Wiraswasta", True, None),
            ("alamat_ayah", "Alamat Ayah", "text", None, "Kampung / Jalan", True, None),
            ("rt_ayah", "RT Ayah", "text", None, "mis. 002", True, None),
            ("rw_ayah", "RW Ayah", "text", None, "mis. 004", True, None),
            ("kel_desa_ayah", "Desa/Kel Ayah", "text", None, "mis. Citeko", True, None),
            ("kec_ayah", "Kecamatan Ayah", "text", None, "mis. Cisarua", True, None),
            ("kab_kota_ayah", "Kabupaten/Kota Ayah", "text", None, "mis. Bogor", True, None),
            ("nama_ibu", "Nama Ibu Kandung", "text", None, "nama ibu", True, None),
            ("nik_ibu", "NIK Ibu Kandung", "text", None, "16 digit NIK ibu", True, None),
            ("tempat_lahir_ibu", "Tempat Lahir Ibu", "text", None, "mis. Bogor", True, None),
            ("tanggal_lahir_ibu", "Tanggal Lahir Ibu", "date", None, None, True, None),
            ("pekerjaan_ibu", "Pekerjaan Ibu", "text", None, "mis. Mengurus Rumah Tangga", True, None),
            ("alamat_ibu", "Alamat Ibu", "text", None, "Kampung / Jalan", True, None),
            ("rt_ibu", "RT Ibu", "text", None, "mis. 002", True, None),
            ("rw_ibu", "RW Ibu", "text", None, "mis. 004", True, None),
            ("kel_desa_ibu", "Desa/Kel Ibu", "text", None, "mis. Citeko", True, None),
            ("kec_ibu", "Kecamatan Ibu", "text", None, "mis. Cisarua", True, None),
            ("kab_kota_ibu", "Kabupaten/Kota Ibu", "text", None, "mis. Bogor", True, None),
            ("nama_pasangan", "Nama Calon Pasangan", "text", None, "nama calon suami/istri", True, None),
            ("bin_binti_pasangan", "Bin / Binti Pasangan", "text", None, "mis. Bin Ahmad", True, None),
            ("nik_pasangan", "NIK Calon Pasangan", "text", None, "16 digit NIK pasangan", True, None),
            ("jk_pasangan", "Jenis Kelamin Pasangan", "select", ["Laki-laki", "Perempuan"], None, True, None),
            ("ttl_pasangan", "TTL Calon Pasangan", "text", None, "mis. Serang, 15 Mei 1998", True, None),
            ("agama_pasangan", "Agama Pasangan", "text", None, "mis. Islam", True, None),
            ("pekerjaan_pasangan", "Pekerjaan Pasangan", "text", None, "mis. Mengurus Rumah Tangga", True, None),
            ("alamat_pasangan", "Alamat Calon Pasangan", "text", None, "alamat lengkap pasangan", True, None),
            ("rt_pasangan", "RT Pasangan", "text", None, "mis. 003", True, None),
            ("rw_pasangan", "RW Pasangan", "text", None, "mis. 002", True, None),
            ("kel_desa_pasangan", "Desa/Kel Pasangan", "text", None, "mis. Sukasirna", True, None),
            ("kec_pasangan", "Kecamatan Pasangan", "text", None, "mis. Cibadak", True, None),
            ("kab_kota_pasangan", "Kabupaten/Kota Pasangan", "text", None, "mis. Sukabumi", True, None),
            ("provinsi_pasangan", "Provinsi Pasangan", "text", None, "mis. Jawa Barat", True, None),
            # Lokasi Pernikahan (item 2, 06/08/2026): replaces the old
            # always-optional desa_akad/kecamatan_akad ("jika menumpang
            # nikah") with an explicit dalam/luar domisili choice -- luar
            # domisili makes them required, dalam domisili only needs the
            # date. Positioned last (after Data Calon Pasangan), matching
            # the requested step order ("setelah mengisi modal pasangan").
            ("lokasi_akad", "Lokasi Pernikahan", "select",
             ["Di Dalam Domisili Pengaju", "Di Luar Domisili Pengaju"], None, True, None),
            ("desa_akad", "Desa/Kelurahan Tempat Akad", "text", None, "mis. Desa Kopo / Desa Lain", True,
             {"show_when": {"field": "lokasi_akad", "in": ["Di Luar Domisili Pengaju"]}}),
            ("kecamatan_akad", "Kecamatan Tempat Akad", "text", None, "mis. Kopo", True,
             {"show_when": {"field": "lokasi_akad", "in": ["Di Luar Domisili Pengaju"]}}),
            ("tgl_akad", "Rencana Tanggal Akad Nikah", "date", None, None, True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa Kopo, menerangkan dengan sesungguhnya bahwa:</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:30%; padding:3px 0;'>Nama Calon</td><td style='width:5%;'>:</td><td><b>{{ nama }}</b></td></tr>"
            "<tr><td style='padding:3px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:3px 0;'>Status</td><td>:</td><td>{{ status_calon }}</td></tr>"
            "</table>"
            "<p>Menerangkan bahwa calon pasangan yang bersangkutan adalah:</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:30%; padding:3px 0;'>Nama Pasangan</td><td style='width:5%;'>:</td><td><b>{{ nama_pasangan }}</b> ({{ bin_binti_pasangan }})</td></tr>"
            "<tr><td style='padding:3px 0;'>NIK Pasangan</td><td>:</td><td>{{ nik_pasangan }}</td></tr>"
            "<tr><td style='padding:3px 0;'>Alamat Pasangan</td><td>:</td><td>{{ alamat_pasangan }}</td></tr>"
            "<tr><td style='padding:3px 0;'>Lokasi Akad Nikah</td><td>:</td><td>{{ desa_akad }}, Kec. {{ kecamatan_akad }}</td></tr>"
            "</table>"
            "<p>Demikian Surat Pengantar Nikah (N.1/N.4/N.5) ini dibuat untuk dipergunakan dalam pengurusan pernikahan di KUA.</p>"
        ),
    },
    {
        # 2026-08-01 MASTER_COLUMN_LETTERS.md item 10: UHC (BPJS-PBI
        # referral) rebuilt as SKTM (Surat Keterangan Tidak Mampu) -- a
        # much simpler, more common village letter. `code` deliberately
        # stays "uhc" (no rename) so the existing master_uhc table/mapping
        # in _save_to_domain_master keeps working unchanged; only the
        # letter's presented identity and citizen-facing form change.
        "code": "uhc", "name": "Surat Keterangan Tidak Mampu (SKTM)", "icon": "volunteer_activism",
        "color_bg": "#EAFBF4", "color_fg": "#108050",
        "description": "Surat Keterangan Tidak Mampu berbasis DTKS untuk keperluan bantuan/keringanan biaya",
        "required_documents": ["Foto KK", "Foto KTP"],
        "numbering_prefix": "440",
        "output_category": "desa_direct",
        "is_active": True,
        # 2026-08-02: real specimen (template_file/UHC WORD.docx) is a
        # 2-document bundle -- "Surat Keterangan Keluarga Miskin" +
        # "Surat Pernyataan Tanggung Jawab Mutlak" (the latter lists the
        # head of family plus up to 9 dependents, nama_2..nik_10, already
        # schema-ready on MasterUHC from the earlier MASTER_COLUMN_LETTERS
        # pass). Applicant identity (nama/nik/jk/ttl/pekerjaan/status/
        # alamat/rt/rw) comes from the shared applicant snapshot --
        # `rt`/`rw` doubles as the RT/RW that issued the referral in the
        # real specimen (same numbers), so no separate field for that.
        # `terdaftar_dtks` stays optional (2026-08-05 TAMBAHAN item 6: no
        # longer is_staff_only/deferred -- warga self-reports it as best
        # they know at submission time; staff can still correct it via
        # update_answers during crosscheck if it doesn't match DTKS).
        "sub_documents": [
            {"code": "sktm_utama", "name": "Surat Keterangan Keluarga Miskin"},
            {"code": "sktm_tjm", "name": "Surat Pernyataan Tanggung Jawab Mutlak"},
        ],
        "fields": [
            ("no_kk", "No. KK", "text", None, "16 digit nomor KK", True, None),
            ("tgl_dikeluarkan_kk", "Tanggal KK Dikeluarkan", "date", None, None, True, None),
            ("tanggal_pengantar_rt", "Tanggal Surat Pengantar RT", "date", None, None, True, None),
            ("keperluan", "Keperluan", "text", None, "mis. keringanan biaya rumah sakit, beasiswa", True, None),
            ("terdaftar_dtks", "Terdaftar DTKS?", "select", ["Ya", "Tidak"], None, False, None),
            ("nama_2", "Nama Anggota Keluarga 2", "text", None, "opsional", False, None),
            ("nik_2", "NIK Anggota Keluarga 2", "text", None, "opsional", False, None),
            ("nama_3", "Nama Anggota Keluarga 3", "text", None, "opsional", False, None),
            ("nik_3", "NIK Anggota Keluarga 3", "text", None, "opsional", False, None),
            ("nama_4", "Nama Anggota Keluarga 4", "text", None, "opsional", False, None),
            ("nik_4", "NIK Anggota Keluarga 4", "text", None, "opsional", False, None),
            ("nama_5", "Nama Anggota Keluarga 5", "text", None, "opsional", False, None),
            ("nik_5", "NIK Anggota Keluarga 5", "text", None, "opsional", False, None),
            ("nama_6", "Nama Anggota Keluarga 6", "text", None, "opsional", False, None),
            ("nik_6", "NIK Anggota Keluarga 6", "text", None, "opsional", False, None),
            ("nama_7", "Nama Anggota Keluarga 7", "text", None, "opsional", False, None),
            ("nik_7", "NIK Anggota Keluarga 7", "text", None, "opsional", False, None),
            ("nama_8", "Nama Anggota Keluarga 8", "text", None, "opsional", False, None),
            ("nik_8", "NIK Anggota Keluarga 8", "text", None, "opsional", False, None),
            ("nama_9", "Nama Anggota Keluarga 9", "text", None, "opsional", False, None),
            ("nik_9", "NIK Anggota Keluarga 9", "text", None, "opsional", False, None),
            ("nama_10", "Nama Anggota Keluarga 10", "text", None, "opsional", False, None),
            ("nik_10", "NIK Anggota Keluarga 10", "text", None, "opsional", False, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa Kopo, menerangkan dengan sesungguhnya bahwa:</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:30%; padding:3px 0;'>Nama</td><td style='width:5%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
            "<tr><td style='padding:3px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:3px 0;'>No. KK</td><td>:</td><td>{{ no_kk }}</td></tr>"
            "<tr><td style='padding:3px 0;'>Alamat</td><td>:</td><td>{{ alamat }}</td></tr>"
            "<tr><td style='padding:3px 0;'>Terdaftar DTKS</td><td>:</td><td>{{ terdaftar_dtks }}</td></tr>"
            "</table>"
            "<p>Adalah benar warga Desa Kopo yang termasuk keluarga tidak mampu, untuk keperluan "
            "<b>{{ keperluan }}</b>.</p>"
            "<p>Demikian Surat Keterangan Tidak Mampu ini dibuat untuk dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "pindah", "name": "Surat Pindah", "icon": "moving",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Pengantar Pindah Domisili Keluar",
        # "0 anggota lain" case (Kepala Keluarga pindah sendirian) -- see
        # PINDAH_CATEGORY_DOCS above for how this scales with anggota_yang_ikut.
        "required_documents": PINDAH_CATEGORY_DOCS["0"],
        "category_field_key": "anggota_yang_ikut",
        "required_documents_by_category": PINDAH_CATEGORY_DOCS,
        "numbering_prefix": "475",
        # Real F-1.03 specimen DOES print a village "Nomor" ("457 -Pem",
        # confirmed 06/08/2026 by reading the actual specimen -- the older
        # "no village Nomor" assumption baked into this pattern was based on
        # a different/incomplete reference, see HASIL_UJICOBA_PENGAJUAN_PER_
        # SURAT.md item 5).
        "numbering_pattern": "{prefix}/{seq}-Pem",
        "output_category": "dukcapil_pengantar",
        "is_active": True,
        "fields": [
            # Alamat asal (item 4, 06/08/2026): the applicant's CURRENT
            # address is always within Desa Kopo (that's who's eligible to
            # file this letter), so unlike alamat_tujuan below, rt_asal/
            # rw_asal have no kel_desa_/kec_/kab_kota_/provinsi_ sibling --
            # isVillageLocalRtRw (src/utils/rtRwField.js) picks that up
            # automatically and renders them as a village RW->RT dropdown,
            # not free text. Desa/Kecamatan/Kabupaten/Provinsi for "asal"
            # are always Desa Kopo's own (fixed, not asked -- see
            # PINDAH_TEMPLATE.docx, which prints VillageProfile's own fields
            # for that section instead of a warga-typed answer).
            ("alamat_asal", "Alamat Asal (Kp/Jalan)", "text", None, "mis. KP. Kopo Tengah", True, None),
            ("rt_asal", "RT Asal", "text", None, "mis. 003", True, None),
            ("rw_asal", "RW Asal", "text", None, "mis. 009", True, None),
            ("alamat_tujuan", "Alamat Tujuan (Kp/Jalan)", "text", None, "mis. Jl. Tanah Seratus No. 38", True, None),
            ("rt_tujuan", "RT Tujuan", "text", None, "mis. 005", True, None),
            ("rw_tujuan", "RW Tujuan", "text", None, "mis. 011", True, None),
            ("kel_desa_tujuan", "Desa/Kelurahan Tujuan", "text", None, "mis. Sudimara Jaya", True, None),
            ("kec_tujuan", "Kecamatan Tujuan", "text", None, "mis. Ciledug", True, None),
            ("kab_kota_tujuan", "Kabupaten/Kota Tujuan", "text", None, "mis. Kota Tangerang", True, None),
            ("provinsi_tujuan", "Provinsi Tujuan", "text", None, "mis. Banten", True, None),
            ("klasifikasi_kepindahan", "Klasifikasi Kepindahan", "select", [
                "Dalam satu Desa/Kelurahan", "Antar Desa/Kelurahan",
                "Antar Kecamatan dalam satu Kabupaten", "Antar Kabupaten/Kota dalam satu Provinsi",
                "Antar Provinsi",
            ], None, True, None),
            ("alasan_pindah", "Alasan Pindah", "select", [
                "Pekerjaan", "Pendidikan", "Kesehatan", "Keamanan", "Perumahan",
                "Keluarga", "Ikut Suami/Istri", "Lainnya",
            ], None, True, None),
            ("jenis_kepindahan", "Jenis Kepindahan", "select", [
                "Kepala Keluarga", "Kepala Keluarga dan Sebagian Anggota Keluarga",
                "Kepala Keluarga dan Seluruh Anggota Keluarga", "Anggota Keluarga",
            ], None, True, None),
            ("status_kk_tujuan", "Status KK di Tempat Tujuan", "select",
             ["Numpang KK", "Membuat KK Baru"], None, True, None),
            # Item 2, 06/08/2026: hidden+not required when jenis_kepindahan
            # is "Kepala Keluarga" (pindah sendirian, tidak ada anggota lain
            # untuk didaftarkan).
            ("anggota_yang_ikut", "Jumlah Anggota Keluarga Lain yang Ikut", "number", None,
             f"0-{_PINDAH_MAX_ANGGOTA}, di luar diri sendiri", True,
             {"show_when": {"field": "jenis_kepindahan", "in": [
                 "Kepala Keluarga dan Sebagian Anggota Keluarga",
                 "Kepala Keluarga dan Seluruh Anggota Keluarga",
                 "Anggota Keluarga",
             ]}}),
            # Item 3, 06/08/2026: replaces the old single free-text
            # "daftar_anggota_pindah" textarea with N separate numbered
            # sub-forms (grouped under "Anggota Keluarga yang Ikut Pindah
            # <n>" in GuestSubmission.jsx/ModeLoket.jsx via GROUP_DEFS),
            # each shown only once anggota_yang_ikut reaches that count.
            *_pindah_anggota_fields(),
        ],
        # Mirrors SURAT PINDAH 2024.docx ("SURAT PERNYATAAN") -- a citizen's
        # own declaration, not a Kepala Desa-issued certificate; see
        # PindahRenderer for the resulting signature-footer difference.
        "pdf_body_template": (
            "<p>Yang bertandatangan dibawah ini :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Nama Lengkap</td><td style='width:4%;'>:</td><td><b>{{ nama }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Tempat, Tanggal Lahir</td><td>:</td><td>{{ tempat_lahir or '-' }}, {{ tanggal_lahir|ddmmyyyy }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Jenis Kelamin</td><td>:</td><td>{{ jk or '-' }}</td></tr>"
            "</table>"
            "<p>Dengan ini menyatakan bahwa alamat tujuan pindah saya adalah :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Alamat</td><td style='width:4%;'>:</td><td>{{ alamat_tujuan }}</td></tr>"
            "<tr><td style='padding:2px 0;'>RT/RW</td><td>:</td><td>{{ rt_tujuan }} / {{ rw_tujuan }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Desa/Kelurahan</td><td>:</td><td>{{ kel_desa_tujuan }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Kecamatan</td><td>:</td><td>{{ kec_tujuan }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Kabupaten/Kota</td><td>:</td><td>{{ kab_kota_tujuan }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Provinsi</td><td>:</td><td>{{ provinsi_tujuan }}</td></tr>"
            "</table>"
            "<p>Klasifikasi Kepindahan : <b>{{ klasifikasi_kepindahan }}</b></p>"
            "<p>Jenis Kepindahan : <b>{{ jenis_kepindahan }}</b></p>"
            "<p>Alasan Pindah : <b>{{ alasan_pindah }}</b>, diikuti sebanyak {{ anggota_yang_ikut }} anggota keluarga.</p>"
            "{% if daftar_anggota_pindah %}"
            "<p>Daftar Anggota Keluarga yang Ikut Pindah (Nama - NIK - SHDK):</p>"
            "<p style='white-space:pre-line;'>{{ daftar_anggota_pindah }}</p>"
            "{% endif %}"
            "<p>Demikian pernyataan ini saya buat dengan sebenarnya untuk bahan tindaklanjut, dan apabila "
            "ada pernyataan saya yang tidak benar serta ada pihak yang keberatan atas penggunaan alamat "
            "tersebut atau kami sudah tidak berdomisili di alamat tersebut, kami akan segera mengurus "
            "kepindahan kealamat baru.</p>"
        ),
    },
    {
        # Added 2026-08-03 per ALUR_PENGAJUAN_UBAH_DATA.md.
        "code": "ubah_data", "name": "Perubahan Elemen Data Kependudukan", "icon": "edit_document",
        "color_bg": "#FDF2E9", "color_fg": "#C6690B",
        "description": "Pernyataan perubahan elemen data kependudukan (format F1.06)",
        "required_documents": _UBAH_DATA_WAJIB,
        "category_field_key": "elemen_diubah",
        "required_documents_by_category": UBAH_DATA_CATEGORY_DOCS,
        "numbering_prefix": "474.1",
        # Real template (F-1.06, "SURAT PERNYATAAN") has no village-issued
        # "Nomor" -- same situation as Pindah; internal tracking only.
        "numbering_pattern": "{prefix}/{seq}",
        "output_category": "dukcapil_pengantar",
        "is_active": True,
        "fields": [
            ("elemen_diubah", "Elemen Data yang Diubah", "select",
             list(UBAH_DATA_CATEGORY_DOCS.keys()), None, True, None),
            ("data_lama", "Data Semula", "text", None, "mis. Karyawan Swasta", True, None),
            ("data_baru", "Data Menjadi", "text", None, "mis. Wiraswasta", True, None),
            ("alasan_perubahan", "Dasar/Alasan Perubahan", "textarea", None,
             "mis. pindah kerja, lulus sekolah, keputusan pengadilan, dll", True, None),
        ],
        # Mirrors F-1.06.docx ("SURAT PERNYATAAN PERUBAHAN ELEMEN DATA
        # KEPENDUDUKAN") -- a citizen's own sworn declaration with Materai,
        # not a Kepala Desa-issued certificate; see UbahDataRenderer for the
        # single-signature footer (no RT/desa countersignature, unlike Pindah).
        "pdf_body_template": (
            "<p>Yang bertandatangan dibawah ini :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Nomor KK</td><td>:</td><td>{{ no_kk }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Alamat</td><td>:</td><td>{{ alamat }}</td></tr>"
            "</table>"
            "<p>Dengan ini menyatakan bahwa data elemen data kependudukan saya telah berubah, dengan rincian :</p>"
            "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
            "<tr><td style='width:32%; padding:2px 0;'>Elemen Data yang Diubah</td><td style='width:4%;'>:</td><td><b>{{ elemen_diubah }}</b></td></tr>"
            "<tr><td style='padding:2px 0;'>Data Semula</td><td>:</td><td>{{ data_lama }}</td></tr>"
            "<tr><td style='padding:2px 0;'>Data Menjadi</td><td>:</td><td>{{ data_baru }}</td></tr>"
            "<tr><td style='padding:2px 0; vertical-align:top;'>Dasar/Alasan Perubahan</td><td style='vertical-align:top;'>:</td><td>{{ alasan_perubahan }}</td></tr>"
            "</table>"
            "<p>Terlampir disampaikan fotokopi berkas-berkas yang terkait dengan perubahan elemen data tersebut.</p>"
            "<p>Demikian Surat Pernyataan ini saya buat dengan sebenarnya, apabila dalam keterangan yang saya "
            "berikan terdapat hal-hal yang tidak berdasarkan keadaan yang sebenarnya, saya bersedia dikenakan "
            "sanksi sesuai ketentuan peraturan perundang-undangan yang berlaku.</p>"
        ),
    },
]

