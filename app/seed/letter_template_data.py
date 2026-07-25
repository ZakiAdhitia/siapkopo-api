"""Seed data for the 8 letter templates, transcribed from mockData.js suratTypes.

Each entry's ``fields`` list holds tuples:
(field_key, label, field_type, options, placeholder, is_required, validation_rules)
"""

SURAT_TEMPLATES: list[dict] = [
    {
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Usulan cetak / perubahan KK",
        "required_documents": ["KK lama", "KTP kepala keluarga"],
        "numbering_prefix": "474",
        "fields": [
            ("status_perubahan", "Status Perubahan", "select",
             ["Cetak baru", "Perubahan data", "KK hilang"], None, True, None),
            ("jumlah_anggota_keluarga", "Jumlah Anggota Keluarga", "number",
             None, "mis. 4", True, None),
            ("keterangan_perubahan", "Keterangan Perubahan", "text",
             None, "mis. penambahan anggota", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Adalah benar warga kami yang mengajukan permohonan Kartu Keluarga dengan "
            "rincian sebagai berikut:</p>"
            "<p>Status Perubahan: {{ status_perubahan }}<br>"
            "Jumlah Anggota Keluarga: {{ jumlah_anggota_keluarga }} orang<br>"
            "Keterangan: {{ keterangan_perubahan }}</p>"
            "<p>Demikian surat keterangan ini dibuat untuk dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "domisili", "name": "Surat Domisili", "icon": "home_pin",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Keterangan tempat tinggal",
        "required_documents": ["KTP", "KK"],
        "numbering_prefix": "470",
        "fields": [
            ("alamat_tinggal_saat_ini", "Alamat Tinggal Saat Ini", "text",
             None, "Dusun / RT / RW", True, None),
            ("lama_tinggal", "Lama Tinggal", "text", None, "mis. 5 tahun", True, None),
            ("tujuan_penggunaan", "Tujuan Penggunaan", "text",
             None, "mis. persyaratan bank", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat KTP: {{ alamat }}</p>"
            "<p>Benar-benar berdomisili/bertempat tinggal di {{ alamat_tinggal_saat_ini }} "
            "selama {{ lama_tinggal }}.</p>"
            "<p>Surat keterangan ini dibuat untuk keperluan {{ tujuan_penggunaan }} dan agar "
            "dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "description": "Surat keterangan usaha",
        "required_documents": ["KTP", "KK", "Foto tempat usaha"],
        "numbering_prefix": "503",
        "fields": [
            ("jenis_usaha", "Jenis Usaha", "text", None, "mis. warung sembako", True, None),
            ("alamat_usaha", "Alamat Usaha", "text", None, "lokasi usaha", True, None),
            ("nib", "NIB (jika ada)", "text", None, "opsional", False, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Benar memiliki/menjalankan usaha dengan keterangan sebagai berikut:</p>"
            "<p>Jenis Usaha: {{ jenis_usaha }}<br>Alamat Usaha: {{ alamat_usaha }}<br>"
            "NIB: {{ nib }}</p>"
            "<p>Demikian Surat Keterangan Usaha ini dibuat untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "sktm", "name": "Ket. Tidak Mampu", "icon": "volunteer_activism",
        "color_bg": "#F3EAFB", "color_fg": "#7B4BC0",
        "description": "SKTM untuk bantuan",
        "required_documents": ["KTP", "KK", "Surat pengantar RT/RW"],
        "numbering_prefix": "460",
        "fields": [
            ("keperluan", "Keperluan", "select",
             ["Beasiswa", "Kesehatan", "Bansos"], None, True, None),
            ("penghasilan_bulan", "Penghasilan / Bulan", "text",
             None, "mis. Rp 1.200.000", True, None),
            ("lampiran_pendukung", "Lampiran Pendukung", "text",
             None, "mis. surat sekolah", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Adalah benar warga kami yang tergolong keluarga kurang mampu dengan "
            "penghasilan {{ penghasilan_bulan }} per bulan.</p>"
            "<p>Surat keterangan ini dibuat untuk keperluan {{ keperluan }} dengan lampiran "
            "pendukung: {{ lampiran_pendukung }}.</p>"
            "<p>Demikian surat ini dibuat dengan sebenarnya untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "lahir", "name": "Ket. Kelahiran", "icon": "child_friendly",
        "color_bg": "#FFF1F4", "color_fg": "#C93B6A",
        "description": "Surat keterangan lahir",
        "required_documents": ["KK", "KTP orang tua", "Surat bidan/RS"],
        "numbering_prefix": "471",
        "fields": [
            ("nama_bayi", "Nama Bayi", "text", None, "nama lengkap bayi", True, None),
            ("tanggal_tempat_lahir", "Tanggal & Tempat Lahir", "text",
             None, "mis. Kopo, 12 Jul 2026", True, None),
            ("nama_saksi", "Nama Saksi", "text", None, "saksi kelahiran", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa telah lahir seorang anak dari:</p>"
            "<p>Nama Orang Tua: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Dengan keterangan bayi sebagai berikut:</p>"
            "<p>Nama Bayi: {{ nama_bayi }}<br>Tanggal &amp; Tempat Lahir: "
            "{{ tanggal_tempat_lahir }}<br>Nama Saksi: {{ nama_saksi }}</p>"
            "<p>Demikian Surat Keterangan Kelahiran ini dibuat untuk dipergunakan "
            "sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "description": "Surat keterangan kematian",
        "required_documents": ["KK", "KTP almarhum", "Surat RS (bila ada)"],
        "numbering_prefix": "472",
        "fields": [
            ("nama_almarhum", "Nama Almarhum/ah", "text", None, "nama lengkap", True, None),
            ("tanggal_tempat_wafat", "Tanggal & Tempat Wafat", "text",
             None, "mis. Kopo, 10 Jul 2026", True, None),
            ("penyebab", "Penyebab", "text", None, "mis. sakit", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama Almarhum/ah: <b>{{ nama_almarhum }}</b></p>"
            "<p>Benar telah meninggal dunia pada {{ tanggal_tempat_wafat }} dengan penyebab "
            "{{ penyebab }}.</p>"
            "<p>Yang melaporkan:</p>"
            "<p>Nama: {{ nama }}<br>NIK: {{ nik }}<br>Alamat: {{ alamat }}</p>"
            "<p>Demikian Surat Keterangan Kematian ini dibuat untuk dipergunakan sebagaimana "
            "mestinya.</p>"
        ),
    },
    {
        "code": "pindah", "name": "Surat Pindah", "icon": "moving",
        "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "description": "Pindah domisili keluar",
        "required_documents": ["KK", "KTP semua anggota"],
        "numbering_prefix": "475",
        "fields": [
            ("alamat_tujuan", "Alamat Tujuan", "text", None, "alamat baru lengkap", True, None),
            ("alasan_pindah", "Alasan Pindah", "text", None, "mis. pekerjaan", True, None),
            ("anggota_yang_ikut", "Anggota yang Ikut", "number",
             None, "jumlah orang", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat Asal: {{ alamat }}</p>"
            "<p>Benar bermaksud pindah domisili ke {{ alamat_tujuan }} dengan alasan "
            "{{ alasan_pindah }}, bersama {{ anggota_yang_ikut }} anggota keluarga.</p>"
            "<p>Demikian Surat Pindah ini dibuat untuk dipergunakan sebagaimana mestinya.</p>"
        ),
    },
    {
        "code": "datang", "name": "Ket. Datang", "icon": "login",
        "color_bg": "#E7F4EC", "color_fg": "#1F8A56",
        "description": "Kedatangan penduduk baru",
        "required_documents": ["Surat pindah desa asal", "KTP", "KK"],
        "numbering_prefix": "476",
        "fields": [
            ("asal_domisili_sebelumnya", "Asal Domisili Sebelumnya", "text",
             None, "alamat asal", True, None),
            ("tujuan_menetap", "Tujuan Menetap", "text", None, "mis. bekerja", True, None),
            ("surat_pindah_asal", "Surat Pindah Asal", "text",
             None, "nomor surat pindah", True, None),
        ],
        "pdf_body_template": (
            "<p>Yang bertanda tangan di bawah ini, Kepala Desa, menerangkan dengan "
            "sesungguhnya bahwa:</p>"
            "<p>Nama: <b>{{ nama }}</b><br>NIK: {{ nik }}<br>Alamat Sekarang: {{ alamat }}</p>"
            "<p>Benar telah datang dan menetap di desa ini, berasal dari "
            "{{ asal_domisili_sebelumnya }} dengan tujuan {{ tujuan_menetap }}, sesuai Surat "
            "Pindah Nomor {{ surat_pindah_asal }}.</p>"
            "<p>Demikian Surat Keterangan Kedatangan ini dibuat untuk dipergunakan "
            "sebagaimana mestinya.</p>"
        ),
    },
]
