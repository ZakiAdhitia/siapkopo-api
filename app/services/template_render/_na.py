"""Renderer for Pengantar Nikah (NA) -- produces 5 separate sub-documents.

Mirrors `2025 SYARAT PELAYANAN DESA/2025 NA/2025 N.A.doc` exactly:

  na_n1         - FORMULIR PENGANTAR NIKAH (Model N.1, KUA legal-basis kop,
                  signed by Kepala Desa directly -- not "A/n. ... Sekdes")
  na_n4         - SURAT PERSETUJUAN PENGANTIN (Model N.4, KUA legal-basis
                  kop, signed by the couple themselves)
  na_n5         - SURAT IZIN ORANG TUA (Model N.5, KUA legal-basis kop,
                  signed by both parents)
  na_menumpang  - SURAT KETERANGAN MENUMPANG NIKAH (normal desa kop +
                  A/n. Kepala Desa/Sekdes signature, like every other letter)
  na_belum_nikah - SURAT KETERANGAN BELUM PERNAH NIKAH (same as menumpang)

N.1/N.4/N.5 are prescribed by Kepdirjen Bimas Islam No. 473/2020 -- they
replace the village's own Pemerintah/Kecamatan/Desa kop with the KUA legal
citation block (KUA_KOP) and use different signature footers per document,
hence the per-sub-document kop_template/footer_template overrides below.

Ayah/Ibu/pasangan's own "Warga Negara"/"Agama" aren't separate template
fields (NA is inherently an Islamic/KUA marriage process, so "Islam" and
"Indonesia" are hardcoded for them here rather than adding fields whose
answer would never vary in practice); "Bin/Binti" for the calon themselves
is derived from nama_ayah + jk_calon rather than asked as its own field.
"""
from __future__ import annotations

from datetime import date

from app.core.exceptions import AppException
from app.models.letter_template import LetterTemplate, TemplateField
from app.models.master import VillageProfile

from ._base import (
    KUA_KOP,
    DUAL_SIGNATURE_FOOTER,
    KEPALA_DESA_DIRECT_FOOTER,
    BaseLetterRenderer,
    format_tanggal_indonesia,
)

# ---------------------------------------------------------------------------
# Sub-document body templates
# ---------------------------------------------------------------------------

_BIN_BINTI_CALON = (
    "{% if jk_calon == 'Laki-laki' %}Bin{% else %}Binti{% endif %} {{ nama_ayah }}"
)

_NA_N1_BODY = (
    "<p style='text-align:center; font-weight:bold; text-decoration:underline;'>FORMULIR PENGANTAR NIKAH</p>"
    "<p>Yang bertanda tangan dibawah ini menerangkan dengan sesungguhnya bahwa :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Warga Negara</td><td style='vertical-align:top;'>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }}<br>Kecamatan {{ kecamatan }} Kabupaten {{ kabupaten }}.</td></tr>"
    "</table>"
    "<p>1. Status Perkawinan</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%;'>a)</td><td>Jika Pria, terangkan Jejaka, Duda atau beristri dan berapa isterinya.</td><td style='width:3%;'>:</td><td><b>{{ status_calon|upper }}</b>{% if jumlah_istri %} ({{ jumlah_istri }} istri){% endif %}</td></tr>"
    "<tr><td>b)</td><td>Jika Wanita, terangkan Perawan atau Janda</td><td>:</td><td><b>{{ status_calon|upper }}</b></td></tr>"
    "<tr><td>c)</td><td>Nomor Akta Cerai</td><td>:</td><td>{{ no_akta_cerai or '-' }}</td></tr>"
    "</table>"
    "<p>2. Nama Istri/Suami terdahulu : {{ pasangan_terdahulu or '-' }}</p>"
    "<p>* Adalah benar anak dari perkawinan seorang pria :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama_ayah|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik_ayah }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_ayah }}, {{ tanggal_lahir_ayah|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Warga Negara</td><td style='vertical-align:top;'>:</td><td>Indonesia</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>Islam</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_ayah }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_ayah }} RT. {{ rt_ayah }} RW. {{ rw_ayah }} Desa {{ kel_desa_ayah }}<br>Kecamatan {{ kec_ayah }} Kabupaten {{ kab_kota_ayah }}.</td></tr>"
    "</table>"
    "<p>* Dengan seorang wanita :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama_ibu|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik_ibu }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_ibu }}, {{ tanggal_lahir_ibu|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Warga Negara</td><td style='vertical-align:top;'>:</td><td>Indonesia</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>Islam</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_ibu }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_ibu }} RT. {{ rt_ibu }} RW. {{ rw_ibu }} Desa {{ kel_desa_ibu }}<br>Kecamatan {{ kec_ibu }} Kabupaten {{ kab_kota_ibu }}.</td></tr>"
    "</table>"
    "<p>Demikianlah, surat keterangan ini dibuat dengan mengingat sumpah jabatan dan untuk digunakan seperlunya.</p>"
    "{% if desa_akad %}<p><b>NUMPANG NIKAH :</b><br>Desa/Kel. {{ desa_akad }}, Kecamatan {{ kecamatan_akad }}.</p>{% endif %}"
)

_NA_N4_BODY = (
    "<p style='text-align:center; font-weight:bold; text-decoration:underline;'>SURAT PERSETUJUAN PENGANTIN</p>"
    "<p>Yang bertanda tangan di bawah ini menerangkan dengan sesungguhnya bahwa :</p>"
    "<p><b>{% if jk_calon == 'Laki-laki' %}I. Calon Suami{% else %}I. Calon Istri{% endif %}</b></p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%;'>1.</td><td style='width:35%;'>Nama Lengkap dan Alias</td><td style='width:3%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td>2.</td><td>Bin/Binti</td><td>:</td><td>" + _BIN_BINTI_CALON + "</td></tr>"
    "<tr><td>3.</td><td>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
    "<tr><td>4.</td><td>Jenis Kelamin</td><td>:</td><td>{{ jk_calon }}</td></tr>"
    "<tr><td>5.</td><td>Tempat, Tanggal Lahir</td><td>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td>6.</td><td>Warga Negara</td><td>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td>7.</td><td>Agama</td><td>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td>8.</td><td>Pekerjaan</td><td>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>9.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }}<br>Kecamatan {{ kecamatan }} Provinsi {{ provinsi }}.</td></tr>"
    "</table>"
    "<p><b>{% if jk_calon == 'Laki-laki' %}II. Calon Istri{% else %}II. Calon Suami{% endif %}</b></p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%;'>1.</td><td style='width:35%;'>Nama Lengkap dan Alias</td><td style='width:3%;'>:</td><td><b>{{ nama_pasangan|upper }}</b></td></tr>"
    "<tr><td>2.</td><td>Bin/Binti</td><td>:</td><td>{{ bin_binti_pasangan }}</td></tr>"
    "<tr><td>3.</td><td>NIK</td><td>:</td><td>{{ nik_pasangan }}</td></tr>"
    "<tr><td>4.</td><td>Jenis Kelamin</td><td>:</td><td>{{ jk_pasangan }}</td></tr>"
    "<tr><td>5.</td><td>Tempat, Tanggal Lahir</td><td>:</td><td>{{ ttl_pasangan }}</td></tr>"
    "<tr><td>6.</td><td>Warga Negara</td><td>:</td><td>Indonesia</td></tr>"
    "<tr><td>7.</td><td>Agama</td><td>:</td><td>{{ agama_pasangan }}</td></tr>"
    "<tr><td>8.</td><td>Pekerjaan</td><td>:</td><td>{{ pekerjaan_pasangan }}</td></tr>"
    "<tr><td style='vertical-align:top;'>9.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_pasangan }} RT. {{ rt_pasangan }} RW. {{ rw_pasangan }} Desa {{ kel_desa_pasangan }}<br>"
    "Kecamatan {{ kec_pasangan }} Kab./Kota {{ kab_kota_pasangan }} Provinsi {{ provinsi_pasangan }}.</td></tr>"
    "</table>"
    "<p>Menyatakan dengan sesungguhnya bahwa atas dasar sukarela, dengan kesadaran sendiri, tanpa paksaan "
    "dari siapapun juga, setuju untuk melangsungkan pernikahan.</p>"
    "<p>Demikian surat persetujuan ini di buat untuk digunakan seperlunya.</p>"
)

_NA_N5_BODY = (
    "<p style='text-align:center; font-weight:bold; text-decoration:underline;'>SURAT IZIN ORANG TUA</p>"
    "<p>Yang bertanda tangan di bawah ini :</p>"
    "<p><b>I. Ayah</b></p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama_ayah|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik_ayah }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_ayah }}, {{ tanggal_lahir_ayah|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Warga Negara</td><td style='vertical-align:top;'>:</td><td>Indonesia</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>Islam</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_ayah }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_ayah }} RT. {{ rt_ayah }} RW. {{ rw_ayah }} Desa {{ kel_desa_ayah }}<br>Kecamatan {{ kec_ayah }} Kabupaten {{ kab_kota_ayah }}.</td></tr>"
    "</table>"
    "<p><b>II. Ibu</b></p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama_ibu|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik_ibu }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_ibu }}, {{ tanggal_lahir_ibu|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Warga Negara</td><td style='vertical-align:top;'>:</td><td>Indonesia</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>Islam</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_ibu }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_ibu }} RT. {{ rt_ibu }} RW. {{ rw_ibu }} Desa {{ kel_desa_ibu }}<br>Kecamatan {{ kec_ibu }} Kabupaten {{ kab_kota_ibu }}.</td></tr>"
    "</table>"
    "<p>* Adalah benar Ayah kandung dan Ibu kandung dari seorang anak :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%;'>1.</td><td style='width:35%;'>Nama Lengkap dan Alias</td><td style='width:3%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td>2.</td><td>Bin/Binti</td><td>:</td><td>" + _BIN_BINTI_CALON + "</td></tr>"
    "<tr><td>3.</td><td>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
    "<tr><td>4.</td><td>Tempat, Tanggal Lahir</td><td>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td>5.</td><td>Jenis Kelamin</td><td>:</td><td>{{ jk_calon }}</td></tr>"
    "<tr><td>6.</td><td>Warga Negara</td><td>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td>7.</td><td>Agama</td><td>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td>8.</td><td>Pekerjaan</td><td>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>9.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }} Kecamatan {{ kecamatan }}.</td></tr>"
    "</table>"
    "<p>* Memberikan izin kepadanya untuk melakukan pernikahan dengan :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%;'>1.</td><td style='width:35%;'>Nama Lengkap dan Alias</td><td style='width:3%;'>:</td><td><b>{{ nama_pasangan|upper }}</b></td></tr>"
    "<tr><td>2.</td><td>Bin/Binti</td><td>:</td><td>{{ bin_binti_pasangan }}</td></tr>"
    "<tr><td>3.</td><td>NIK</td><td>:</td><td>{{ nik_pasangan }}</td></tr>"
    "<tr><td>4.</td><td>Tempat, Tanggal Lahir</td><td>:</td><td>{{ ttl_pasangan }}</td></tr>"
    "<tr><td>5.</td><td>Jenis Kelamin</td><td>:</td><td>{{ jk_pasangan }}</td></tr>"
    "<tr><td>6.</td><td>Warga Negara</td><td>:</td><td>Indonesia</td></tr>"
    "<tr><td>7.</td><td>Agama</td><td>:</td><td>{{ agama_pasangan }}</td></tr>"
    "<tr><td>8.</td><td>Pekerjaan</td><td>:</td><td>{{ pekerjaan_pasangan }}</td></tr>"
    "<tr><td style='vertical-align:top;'>9.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_pasangan }} RT. {{ rt_pasangan }} RW. {{ rw_pasangan }} Desa {{ kel_desa_pasangan }}<br>"
    "Kecamatan {{ kec_pasangan }} Kab./Kota {{ kab_kota_pasangan }} Provinsi {{ provinsi_pasangan }}.</td></tr>"
    "</table>"
    "<p>Demikian surat keterangan ini dibuat dengan kesadaran tanpa ada paksaan dari siapapun juga dan "
    "untuk dipergunakan seperlunya.</p>"
)

_NA_MENUMPANG_BODY = (
    "<p>Yang bertandatangan dibawah ini, Kepala Desa {{ village_name }} Kec. {{ kecamatan }} Kabupaten "
    "{{ kabupaten }}, menerangkan bahwa :</p>"
    "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
    "<tr><td style='width:30%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Jenis Kelamin</td><td>:</td><td>{{ jk_calon }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Tempat, Tanggal Lahir</td><td>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Kewarganegaraan</td><td>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Status</td><td>:</td><td>{{ status_calon }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }} Kecamatan {{ kecamatan }}</td></tr>"
    "</table>"
    "<p>Nama tersebut diatas adalah benar warga Desa {{ village_name }} yang beralamatkan sebagaimana "
    "tercantum diatas, dan bermaksud \"Menumpang Nikah\" di :</p>"
    "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
    "<tr><td style='width:30%; padding:2px 0;'>Desa/Kelurahan</td><td style='width:4%;'>:</td><td>{{ desa_akad }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Kecamatan</td><td>:</td><td>{{ kecamatan_akad }}</td></tr>"
    "</table>"
    "<p>Surat keterangan ini diberikan atas permintaan yang bersangkutan guna pelengkap persyaratan akad "
    "nikah di tempat tujuan.</p>"
    "<p>Demikian surat keterangan ini dibuat dengan sebenarnya, agar yang berkepentingan menjadi tahu dan "
    "maklum adanya.</p>"
)

_NA_N6_BODY = (
    "<p style='text-align:center; font-weight:bold; text-decoration:underline;'>SURAT KETERANGAN KEMATIAN</p>"
    "<p>Yang bertanda tangan di bawah ini menerangkan dengan sesungguhnya bahwa :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ pasangan_terdahulu|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>Bin/Binti</td><td style='vertical-align:top;'>:</td><td>{{ bin_binti_pasangan_terdahulu or '-' }}</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik_pasangan_terdahulu or '-' }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_pasangan_terdahulu or '-' }}, {{ tanggal_lahir_pasangan_terdahulu|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Kewarganegaraan</td><td style='vertical-align:top;'>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_pasangan_terdahulu or '-' }}</td></tr>"
    "<tr><td style='vertical-align:top;'>8.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>{{ alamat_pasangan_terdahulu or '-' }}</td></tr>"
    "</table>"
    "<p>Telah meninggal dunia pada tanggal : <b>{{ tanggal_meninggal_pasangan_terdahulu|ddmmyyyy }}</b> "
    "di : <b>{{ tempat_meninggal_pasangan_terdahulu or '-' }}</b>. Yang bersangkutan adalah suami/istri dari :</p>"
    "<table style='width:100%; margin:6px 0;'>"
    "<tr><td style='width:5%; vertical-align:top;'>1.</td><td style='width:35%; vertical-align:top;'>Nama Lengkap dan Alias</td><td style='width:3%; vertical-align:top;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td style='vertical-align:top;'>2.</td><td style='vertical-align:top;'>Bin/Binti</td><td style='vertical-align:top;'>:</td><td>" + _BIN_BINTI_CALON + "</td></tr>"
    "<tr><td style='vertical-align:top;'>3.</td><td style='vertical-align:top;'>NIK</td><td style='vertical-align:top;'>:</td><td>{{ nik }}</td></tr>"
    "<tr><td style='vertical-align:top;'>4.</td><td style='vertical-align:top;'>Tempat, Tanggal Lahir</td><td style='vertical-align:top;'>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td style='vertical-align:top;'>5.</td><td style='vertical-align:top;'>Kewarganegaraan</td><td style='vertical-align:top;'>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td style='vertical-align:top;'>6.</td><td style='vertical-align:top;'>Agama</td><td style='vertical-align:top;'>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>7.</td><td style='vertical-align:top;'>Pekerjaan</td><td style='vertical-align:top;'>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='vertical-align:top;'>8.</td><td style='vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }} Kecamatan {{ kecamatan }}.</td></tr>"
    "</table>"
    "<p>Demikian surat pengantar ini dibuat dengan mengingat sumpah jabatan dan untuk digunakan seperlunya.</p>"
)

_NA_BELUM_NIKAH_BODY = (
    "<p>Yang bertandatangan dibawah ini Kepala Desa {{ village_name }} Kecamatan {{ kecamatan }} Kabupaten "
    "{{ kabupaten }}, dengan ini menerangkan dengan sesungguhnya bahwa :</p>"
    "<table style='width:100%; border-collapse:collapse; margin:10px 0;'>"
    "<tr><td style='width:30%; padding:2px 0;'>Nama</td><td style='width:4%;'>:</td><td><b>{{ nama|upper }}</b></td></tr>"
    "<tr><td style='padding:2px 0;'>NIK</td><td>:</td><td>{{ nik }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Jenis Kelamin</td><td>:</td><td>{{ jk_calon }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Tempat, Tanggal Lahir</td><td>:</td><td>{{ tempat_lahir_calon }}, {{ tanggal_lahir_calon|ddmmyyyy }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Agama</td><td>:</td><td>{{ agama_calon }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Kewarganegaraan</td><td>:</td><td>{{ kewarganegaraan }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Status</td><td>:</td><td>{{ status_calon }}</td></tr>"
    "<tr><td style='padding:2px 0;'>Pekerjaan</td><td>:</td><td>{{ pekerjaan_calon }}</td></tr>"
    "<tr><td style='padding:2px 0; vertical-align:top;'>Alamat</td><td style='vertical-align:top;'>:</td><td>"
    "{{ alamat_calon }} RT. {{ rt_calon }} RW. {{ rw_calon }} Desa {{ village_name }} Kecamatan {{ kecamatan }}.</td></tr>"
    "</table>"
    "<p>Nama tersebut diatas adalah benar warga Desa {{ village_name }}, dan berdasarkan buku induk yang "
    "ada di Kantor kami bahwa yang bersangkutan Belum Pernah Menikah.</p>"
    "<p>Surat Keterangan ini kami berikan atas permintaan yang bersangkutan guna keperluan Persyaratan : "
    "-------MENIKAH-------</p>"
    "<p>Demikian Surat Keterangan ini kami buat dengan sebenarnya dan untuk dipergunakan sebagaimana "
    "mestinya.</p>"
)

# Registry: sub_doc_code -> (letter_title, body_template, kop_template, footer_template)
# kop/footer None means "use the standard village letterhead + A/n. Kepala
# Desa/Sekdes signature" -- the default every other letter type uses.
NA_SUB_DOCUMENTS: dict[str, tuple[str, str, str | None, str | None]] = {
    "na_n1": (
        "FORMULIR PENGANTAR NIKAH", _NA_N1_BODY, KUA_KOP, KEPALA_DESA_DIRECT_FOOTER,
    ),
    "na_n4": (
        "SURAT PERSETUJUAN PENGANTIN", _NA_N4_BODY, KUA_KOP, DUAL_SIGNATURE_FOOTER,
    ),
    "na_n5": (
        "SURAT IZIN ORANG TUA", _NA_N5_BODY, KUA_KOP, DUAL_SIGNATURE_FOOTER,
    ),
    "na_menumpang": (
        "SURAT KETERANGAN UNTUK MENUMPANG NIKAH", _NA_MENUMPANG_BODY, None, None,
    ),
    "na_belum_nikah": (
        "SURAT KETERANGAN BELUM PERNAH MENIKAH", _NA_BELUM_NIKAH_BODY, None, None,
    ),
    # Model N.6 -- only relevant for "cerai mati" scenarios (ALUR_PENGISIAN_NA.md
    # points 3/4); signed by Kepala Desa/Lurah directly, same as N.1, not
    # delegated to Sekdes. No page slot in NA_TEMPLATE.docx (that specimen's
    # 5 pages predate this sub-document) -- rendered via this HTML/Jinja
    # fallback only; see DocxLetterRenderer.supports_sub_document.
    "na_n6": (
        "SURAT KETERANGAN KEMATIAN SUAMI/ISTRI TERDAHULU", _NA_N6_BODY, KUA_KOP, KEPALA_DESA_DIRECT_FOOTER,
    ),
}

# Extra footer context per sub-document that needs it (DUAL_SIGNATURE_FOOTER
# needs left_label/right_label; every other footer/kop only needs the
# standard village_name/tanggal/data already passed by _render_document).
_FOOTER_EXTRA = {
    "na_n4": lambda data: {"left_label": data.get("nama", ""), "right_label": data.get("nama_pasangan", "")},
    "na_n5": lambda data: {"left_label": data.get("nama_ayah", ""), "right_label": data.get("nama_ibu", "")},
}


class NARenderer(BaseLetterRenderer):
    """Renders Pengantar Nikah (NA) letters.

    The NA bundle consists of 5 separate sub-documents.  Use
    ``render_sub_document()`` to produce each one individually, or
    ``render_issued()`` / ``render_preview()`` for the combined fallback.
    """

    # All valid sub-document codes for external callers
    SUB_DOCUMENT_CODES: tuple[str, ...] = tuple(NA_SUB_DOCUMENTS)

    def _render_sub(
        self, *, sub_doc_code: str, profile: VillageProfile, data: dict, nomor: str, tanggal: str,
    ) -> bytes:
        title, body, kop, footer = NA_SUB_DOCUMENTS[sub_doc_code]
        extra = _FOOTER_EXTRA.get(sub_doc_code, lambda _d: {})(data)
        return self._render_document(
            profile=profile,
            data={**data, **extra},
            nomor=nomor,
            tanggal=tanggal,
            letter_title=title,
            body_template=body,
            footer_template=footer,
            kop_template=kop,
        )

    def render_preview(
        self,
        template: LetterTemplate,
        fields: list[TemplateField],
        profile: VillageProfile,
    ) -> bytes:
        """Preview the NA bundle using N.1 (the default issued output)."""
        return self._render_sub(
            sub_doc_code="na_n1", profile=profile, data=self._sample_data(fields),
            nomor=self._preview_number(template), tanggal=format_tanggal_indonesia(date.today()),
        )

    def render_issued(
        self,
        *,
        template: LetterTemplate,
        profile: VillageProfile,
        answers: dict,
        applicant: dict,
        nomor: str,
        tanggal: str,
    ) -> bytes:
        """Render the primary NA document (N.1) as the default issued output."""
        return self._render_sub(
            sub_doc_code="na_n1", profile=profile, data={**applicant, **answers},
            nomor=f"{nomor}/N.1", tanggal=tanggal,
        )

    def render_sub_document(
        self,
        *,
        template: LetterTemplate,
        profile: VillageProfile,
        answers: dict,
        applicant: dict,
        nomor: str,
        tanggal: str,
        sub_doc_code: str,
    ) -> bytes:
        """Render a specific NA sub-document by its code.

        Raises ``AppException(400)`` for unknown codes.
        """
        if sub_doc_code not in NA_SUB_DOCUMENTS:
            raise AppException(
                f"Kode sub-dokumen tidak dikenal: {sub_doc_code!r}",
                "UNKNOWN_SUB_DOC_CODE",
                400,
            )
        return self._render_sub(
            sub_doc_code=sub_doc_code, profile=profile, data={**applicant, **answers},
            nomor=f"{nomor}/{sub_doc_code.upper()}", tanggal=tanggal,
        )
