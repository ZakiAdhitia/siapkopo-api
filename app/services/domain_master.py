"""Read-only CRUD services for the per-letter-type domain master tables.

Each service only needs `.list()` (see app/api/v1/domain_master.py) --
these tables are written exclusively by SubmissionService._save_to_domain_master
on issuance, never through this service's `.create()`/`.update()`.
"""
import io

import openpyxl
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ValidationAppError
from app.models.master import (
    MasterDomisili,
    MasterKelahiran,
    MasterKematian,
    MasterKK,
    MasterNA,
    MasterPindah,
    MasterSKU,
    MasterUbahData,
    MasterUHC,
)
from app.services.master import _CrudService


class MasterDomisiliService(_CrudService):
    model = MasterDomisili
    name = "Master Domisili"

    @property
    def search_columns(self):
        return [MasterDomisili.nik, MasterDomisili.nama]


class MasterKelahiranService(_CrudService):
    model = MasterKelahiran
    name = "Master Kelahiran"

    @property
    def search_columns(self):
        return [MasterKelahiran.nama_anak, MasterKelahiran.nik_ayah, MasterKelahiran.nik_ibu]


class MasterKematianService(_CrudService):
    model = MasterKematian
    name = "Master Kematian"

    @property
    def search_columns(self):
        return [MasterKematian.nik, MasterKematian.nama]


class MasterSKUService(_CrudService):
    model = MasterSKU
    name = "Master SKU"

    @property
    def search_columns(self):
        return [MasterSKU.nik, MasterSKU.nama]


class MasterNAService(_CrudService):
    model = MasterNA
    name = "Master NA"

    @property
    def search_columns(self):
        return [MasterNA.nik, MasterNA.nama, MasterNA.nik_csi]


class MasterUHCService(_CrudService):
    model = MasterUHC
    name = "Master UHC"

    @property
    def search_columns(self):
        return [MasterUHC.nik_pasien, MasterUHC.nama_pasien]


class MasterPindahService(_CrudService):
    model = MasterPindah
    name = "Master Pindah"

    @property
    def search_columns(self):
        return [MasterPindah.nik_pemohon, MasterPindah.nama_pemohon]


class MasterKKService(_CrudService):
    model = MasterKK
    name = "Master KK"

    @property
    def search_columns(self):
        return [MasterKK.no_kk, MasterKK.nama_kk]


class MasterUbahDataService(_CrudService):
    model = MasterUbahData
    name = "Master Ubah Data"

    @property
    def search_columns(self):
        return [MasterUbahData.nik, MasterUbahData.nama]


# jenis (URL-friendly type code) -> service class (HASIL_UJICOBA_PERROLE.md
# kades item 5: "export excel berdasarkan jenis master data").
DOMAIN_MASTER_SERVICES: dict[str, type[_CrudService]] = {
    "domisili": MasterDomisiliService,
    "kelahiran": MasterKelahiranService,
    "kematian": MasterKematianService,
    "sku": MasterSKUService,
    "na": MasterNAService,
    "uhc": MasterUHCService,
    "pindah": MasterPindahService,
    "kk": MasterKKService,
    "ubah_data": MasterUbahDataService,
}

# LetterTemplate.code -> jenis (the DOMAIN_MASTER_SERVICES key), for the two
# places that need to go from "which letter type is this submission" to
# "which domain-master table does it feed" (SubmissionService._save_to_domain_master,
# get_missing_staff_fields).
TEMPLATE_CODE_TO_JENIS: dict[str, str] = {
    "domisili": "domisili", "lahir": "kelahiran", "mati": "kematian",
    "usaha": "sku", "na": "na", "uhc": "uhc", "pindah": "pindah",
    "kk": "kk", "ubah_data": "ubah_data",
}

# 2026-08-06: which of SubmissionMasterDataUpdateRequest's generic fields
# (alamat/rt_id/jk/tempat_lahir/tanggal_lahir/pekerjaan/status_kawin/no_kk)
# a given jenis's domain-master row actually needs from staff, beyond the
# submission's own always-present applicant_nik/applicant_nama -- blocking
# for Approve (SubmissionService.get_missing_staff_fields). Derived by
# reading exactly which `applicant.get(...)` keys each
# SubmissionService._build_domain_master_fields branch reads (as opposed to
# `answers.get(...)`, which is the citizen's own already-required form
# input and untouched by this table) -- a lookup dict, not an if/elif
# per jenis, per CLAUDE.md's Dynamic Form/no-hardcode rule. Keep this in
# sync by hand if either that function's branches change; a mismatch would
# only under- or over-block Approve, never crash, but IS a maintenance trap
# worth a comment.
REQUIRED_STAFF_FIELDS_BY_JENIS: dict[str, list[str]] = {
    "domisili": ["jk", "tempat_lahir", "tanggal_lahir", "pekerjaan", "status_kawin"],
    "kelahiran": [],  # subject is the newborn, not the applicant -- 100% citizen answers
    "kematian": [],  # subject is the deceased -- 100% citizen answers
    "sku": ["alamat", "rt_id", "jk", "tempat_lahir", "tanggal_lahir", "pekerjaan", "status_kawin"],
    "na": [],  # NA's own form already collects jk/ttl/etc. as direct required citizen answers
    "uhc": ["alamat", "rt_id", "jk", "tempat_lahir", "tanggal_lahir", "pekerjaan", "status_kawin"],
    "pindah": ["alamat", "no_kk"],
    "kk": ["alamat", "rt_id", "jk", "tempat_lahir", "tanggal_lahir", "status_kawin"],  # not pekerjaan
    "ubah_data": ["alamat", "no_kk"],
}

# Dotted-path required fields within Submission.staff_extra_data, blocking
# for Approve just like REQUIRED_STAFF_FIELDS_BY_JENIS does for
# staff_master_data (SubmissionService.get_missing_staff_fields). KK is
# absent here -- its "at least one complete anggota row" rule doesn't fit a
# flat required-path list, so it's checked separately.
REQUIRED_EXTRA_FIELDS_BY_JENIS: dict[str, list[str]] = {
    "domisili": [
        "alamat_asal", "rt_asal", "rw_asal", "kel_desa_asal",
        "kec_asal", "kab_kota_asal", "provinsi_asal", "masa_berlaku_bulan",
    ],
    "kematian": ["jk", "pekerjaan", "alamat", "rt", "rw"],
    "kelahiran": [
        "anak.jk", "anak.tempat_lahir", "anak.tanggal_lahir", "anak.jam_lahir", "anak.anak_ke",
        "ayah.tempat_lahir", "ayah.tanggal_lahir", "ayah.pekerjaan", "ayah.alamat", "ayah.rt", "ayah.rw",
        "ibu.tempat_lahir", "ibu.tanggal_lahir", "ibu.pekerjaan", "ibu.alamat", "ibu.rt", "ibu.rw",
    ],
    "na": [
        "calon.jk", "calon.tempat_lahir", "calon.tanggal_lahir", "calon.kewarganegaraan",
        "calon.agama", "calon.pekerjaan", "calon.alamat", "calon.rt", "calon.rw",
        "ayah.tempat_lahir", "ayah.tanggal_lahir", "ayah.pekerjaan", "ayah.alamat",
        "ayah.rt", "ayah.rw", "ayah.kel_desa", "ayah.kec", "ayah.kab_kota",
        "ibu.tempat_lahir", "ibu.tanggal_lahir", "ibu.pekerjaan", "ibu.alamat",
        "ibu.rt", "ibu.rw", "ibu.kel_desa", "ibu.kec", "ibu.kab_kota",
        "csi.bin_binti", "csi.jk", "csi.ttl", "csi.agama", "csi.pekerjaan", "csi.alamat",
        "csi.rt", "csi.rw", "csi.kel_desa", "csi.kec", "csi.kab_kota", "csi.provinsi", "csi.shdk",
    ],
    "kk": ["nama_kk", "dusun"],
}

EXTRA_FIELD_LABELS: dict[str, str] = {
    "alamat_asal": "Alamat Asal (Data Master)", "rt_asal": "RT Asal (Data Master)",
    "rw_asal": "RW Asal (Data Master)", "kel_desa_asal": "Desa/Kelurahan Asal (Data Master)",
    "kec_asal": "Kecamatan Asal (Data Master)", "kab_kota_asal": "Kabupaten/Kota Asal (Data Master)",
    "provinsi_asal": "Provinsi Asal (Data Master)", "masa_berlaku_bulan": "Masa Berlaku (Data Master)",
    "jk": "Jenis Kelamin (Data Master)", "pekerjaan": "Pekerjaan (Data Master)",
    "alamat": "Alamat (Data Master)", "rt": "RT (Data Master)", "rw": "RW (Data Master)",
    "anak.jk": "Jenis Kelamin Anak (Data Master)", "anak.tempat_lahir": "Tempat Lahir Anak (Data Master)",
    "anak.tanggal_lahir": "Tanggal Lahir Anak (Data Master)", "anak.jam_lahir": "Jam Lahir Anak (Data Master)",
    "anak.anak_ke": "Anak Ke- (Data Master)",
    "ayah.tempat_lahir": "Tempat Lahir Ayah (Data Master)", "ayah.tanggal_lahir": "Tanggal Lahir Ayah (Data Master)",
    "ayah.pekerjaan": "Pekerjaan Ayah (Data Master)", "ayah.alamat": "Alamat Ayah (Data Master)",
    "ayah.rt": "RT Ayah (Data Master)", "ayah.rw": "RW Ayah (Data Master)",
    "ayah.kel_desa": "Desa/Kel Ayah (Data Master)", "ayah.kec": "Kecamatan Ayah (Data Master)",
    "ayah.kab_kota": "Kabupaten/Kota Ayah (Data Master)",
    "ibu.tempat_lahir": "Tempat Lahir Ibu (Data Master)", "ibu.tanggal_lahir": "Tanggal Lahir Ibu (Data Master)",
    "ibu.pekerjaan": "Pekerjaan Ibu (Data Master)", "ibu.alamat": "Alamat Ibu (Data Master)",
    "ibu.rt": "RT Ibu (Data Master)", "ibu.rw": "RW Ibu (Data Master)",
    "ibu.kel_desa": "Desa/Kel Ibu (Data Master)", "ibu.kec": "Kecamatan Ibu (Data Master)",
    "ibu.kab_kota": "Kabupaten/Kota Ibu (Data Master)",
    "calon.jk": "Jenis Kelamin Calon (Data Master)", "calon.tempat_lahir": "Tempat Lahir Calon (Data Master)",
    "calon.tanggal_lahir": "Tanggal Lahir Calon (Data Master)",
    "calon.kewarganegaraan": "Kewarganegaraan Calon (Data Master)",
    "calon.agama": "Agama Calon (Data Master)", "calon.pekerjaan": "Pekerjaan Calon (Data Master)",
    "calon.alamat": "Alamat Calon (Data Master)", "calon.rt": "RT Calon (Data Master)",
    "calon.rw": "RW Calon (Data Master)",
    "csi.bin_binti": "Bin/Binti Calon Pasangan (Data Master)",
    "csi.jk": "Jenis Kelamin Calon Pasangan (Data Master)",
    "csi.ttl": "TTL Calon Pasangan (Data Master)", "csi.agama": "Agama Calon Pasangan (Data Master)",
    "csi.pekerjaan": "Pekerjaan Calon Pasangan (Data Master)", "csi.alamat": "Alamat Calon Pasangan (Data Master)",
    "csi.rt": "RT Calon Pasangan (Data Master)", "csi.rw": "RW Calon Pasangan (Data Master)",
    "csi.kel_desa": "Desa/Kel Calon Pasangan (Data Master)", "csi.kec": "Kecamatan Calon Pasangan (Data Master)",
    "csi.kab_kota": "Kabupaten/Kota Calon Pasangan (Data Master)",
    "csi.provinsi": "Provinsi Calon Pasangan (Data Master)", "csi.shdk": "SHDK Calon Pasangan (Data Master)",
    "nama_kk": "Nama Kepala Keluarga (Data Master)", "dusun": "Dusun (Data Master)",
}


def _get_nested(data: dict, dotted_path: str) -> object | None:
    """Resolve a dotted path ("ayah.tempat_lahir") against a nested dict,
    returning None if any segment along the way is missing."""
    value: object = data
    for part in dotted_path.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


# Static sesi/field metadata per jenis for the Tahap 3 wizard (Fase 2 of
# ALUR_REVIEW_INPUT_MASTER.md) to render data-driven, plus the
# GET .../master-data-schema endpoint (SubmissionService.get_master_data_schema).
# "source" tells the reader where a sesi's values live:
#   "generic"      -> Submission.staff_master_data (existing flat 8-field block)
#   "extra"        -> Submission.staff_extra_data, flat top-level keys
#   "extra_nested" -> Submission.staff_extra_data[sesi_key], a nested block
#   "extra_list"   -> Submission.staff_extra_data[sesi_key], a list of blocks
#   "mixed"        -> some fields from staff_master_data, some from staff_extra_data
_GENERIC_IDENTITY_SESI = {
    "key": "pemohon", "label": "Data Pemohon", "source": "generic",
    "fields": [
        {"key": "alamat", "label": "Alamat"}, {"key": "rt_id", "label": "RT/RW"},
        {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
        {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "pekerjaan", "label": "Pekerjaan"},
        {"key": "status_kawin", "label": "Status Kawin"}, {"key": "no_kk", "label": "No. KK"},
    ],
}

STAFF_SESI_SCHEMA_BY_JENIS: dict[str, list[dict]] = {
    "domisili": [
        {"key": "pemohon", "label": "Data Pemohon", "source": "generic", "fields": [
            {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
            {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "pekerjaan", "label": "Pekerjaan"},
            {"key": "status_kawin", "label": "Status Kawin"},
        ]},
        {"key": "alamat_asal", "label": "Alamat Asal", "source": "extra", "fields": [
            {"key": "alamat_asal", "label": "Alamat Asal"}, {"key": "rt_asal", "label": "RT Asal"},
            {"key": "rw_asal", "label": "RW Asal"}, {"key": "kel_desa_asal", "label": "Desa/Kelurahan Asal"},
            {"key": "kec_asal", "label": "Kecamatan Asal"}, {"key": "kab_kota_asal", "label": "Kabupaten/Kota Asal"},
            {"key": "provinsi_asal", "label": "Provinsi Asal"},
        ]},
        {"key": "berlaku", "label": "Berlaku", "source": "extra", "fields": [
            {"key": "masa_berlaku_bulan", "label": "Masa Berlaku (Bulan)"},
        ]},
    ],
    "kematian": [
        {"key": "almarhum", "label": "Data Almarhum/Almarhumah", "source": "extra", "fields": [
            {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
            {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "usia_tahun", "label": "Usia (Tahun)"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"},
        ]},
    ],
    "kelahiran": [
        {"key": "anak", "label": "Data Anak", "source": "extra_nested", "fields": [
            {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
            {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "jam_lahir", "label": "Jam Lahir"},
            {"key": "anak_ke", "label": "Anak Ke-"},
        ]},
        {"key": "ayah", "label": "Data Ayah", "source": "extra_nested", "fields": [
            {"key": "tempat_lahir", "label": "Tempat Lahir"}, {"key": "tanggal_lahir", "label": "Tanggal Lahir"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"},
        ]},
        {"key": "ibu", "label": "Data Ibu", "source": "extra_nested", "fields": [
            {"key": "tempat_lahir", "label": "Tempat Lahir"}, {"key": "tanggal_lahir", "label": "Tanggal Lahir"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"},
        ]},
    ],
    "na": [
        {"key": "calon", "label": "Data Calon", "source": "extra_nested", "fields": [
            {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
            {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "kewarganegaraan", "label": "Kewarganegaraan"},
            {"key": "agama", "label": "Agama"}, {"key": "pekerjaan", "label": "Pekerjaan"},
            {"key": "alamat", "label": "Alamat"}, {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"},
        ]},
        {"key": "ayah", "label": "Data Ayah", "source": "extra_nested", "fields": [
            {"key": "tempat_lahir", "label": "Tempat Lahir"}, {"key": "tanggal_lahir", "label": "Tanggal Lahir"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"}, {"key": "kel_desa", "label": "Desa/Kel"},
            {"key": "kec", "label": "Kecamatan"}, {"key": "kab_kota", "label": "Kabupaten/Kota"},
        ]},
        {"key": "ibu", "label": "Data Ibu", "source": "extra_nested", "fields": [
            {"key": "tempat_lahir", "label": "Tempat Lahir"}, {"key": "tanggal_lahir", "label": "Tanggal Lahir"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"}, {"key": "kel_desa", "label": "Desa/Kel"},
            {"key": "kec", "label": "Kecamatan"}, {"key": "kab_kota", "label": "Kabupaten/Kota"},
        ]},
        {"key": "csi", "label": "Data Calon Suami/Istri", "source": "extra_nested", "fields": [
            {"key": "bin_binti", "label": "Bin/Binti"}, {"key": "jk", "label": "Jenis Kelamin"},
            {"key": "ttl", "label": "Tempat Tanggal Lahir"}, {"key": "agama", "label": "Agama"},
            {"key": "pekerjaan", "label": "Pekerjaan"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt", "label": "RT"}, {"key": "rw", "label": "RW"}, {"key": "kel_desa", "label": "Desa/Kel"},
            {"key": "kec", "label": "Kecamatan"}, {"key": "kab_kota", "label": "Kabupaten/Kota"},
            {"key": "provinsi", "label": "Provinsi"}, {"key": "shdk", "label": "Status Hubungan Dalam Keluarga"},
        ]},
    ],
    "kk": [
        {"key": "kk_header", "label": "Data KK", "source": "mixed", "fields": [
            {"key": "no_kk", "label": "No. KK"}, {"key": "alamat", "label": "Alamat"},
            {"key": "rt_id", "label": "RT/RW"}, {"key": "nama_kk", "label": "Nama Kepala Keluarga"},
            {"key": "dusun", "label": "Dusun"},
        ]},
        {"key": "anggota", "label": "Data Anggota Keluarga", "source": "extra_list",
         "repeatable": True, "max_items": 10, "fields": [
            {"key": "nik", "label": "NIK"}, {"key": "nama", "label": "Nama"},
            {"key": "jk", "label": "Jenis Kelamin"}, {"key": "tempat_lahir", "label": "Tempat Lahir"},
            {"key": "tanggal_lahir", "label": "Tanggal Lahir"}, {"key": "agama", "label": "Agama"},
            {"key": "pendidikan", "label": "Pendidikan"}, {"key": "pekerjaan", "label": "Pekerjaan"},
            {"key": "status_kawin", "label": "Status Perkawinan"}, {"key": "shdk", "label": "SHDK"},
            {"key": "wni_wna", "label": "Status Kependudukan (WNI/WNA)"},
        ]},
        {"key": "orang_tua", "label": "Data Orang Tua", "source": "extra", "fields": [
            {"key": "nama_ayah", "label": "Nama Ayah"}, {"key": "nama_ibu", "label": "Nama Ibu"},
        ]},
    ],
    "sku": [_GENERIC_IDENTITY_SESI],
    "uhc": [_GENERIC_IDENTITY_SESI],
    "pindah": [{"key": "pemohon", "label": "Data Pemohon", "source": "generic", "fields": [
        {"key": "alamat", "label": "Alamat Asal"}, {"key": "no_kk", "label": "No. KK"},
    ]}],
    "ubah_data": [{"key": "pemohon", "label": "Data Pemohon", "source": "generic", "fields": [
        {"key": "alamat", "label": "Alamat"}, {"key": "no_kk", "label": "No. KK"},
    ]}],
}


def _flatten_extra_data(jenis: str, extra: dict) -> dict:
    """Flatten Submission.staff_extra_data's nested per-jenis shape back
    into the flat field-key names the docx/HTML letter templates and
    SubmissionService._save_to_domain_master already expect -- these were
    previously supplied by the citizen's own `answers` before Fase 1 of
    ALUR_REVIEW_INPUT_MASTER.md moved them to staff sesi input. Called from
    SubmissionService.build_applicant_snapshot so every existing consumer of
    the `applicant` dict picks these up with zero further changes."""
    if jenis == "domisili":
        return {
            "alamat_asal": extra.get("alamat_asal"), "rt_asal": extra.get("rt_asal"),
            "rw_asal": extra.get("rw_asal"), "kel_desa_asal": extra.get("kel_desa_asal"),
            "kec_asal": extra.get("kec_asal"), "kab_kota_asal": extra.get("kab_kota_asal"),
            "provinsi_asal": extra.get("provinsi_asal"), "masa_berlaku_bulan": extra.get("masa_berlaku_bulan"),
        }
    if jenis == "kematian":
        return {
            "jk_almarhum": extra.get("jk"), "tempat_lahir_almarhum": extra.get("tempat_lahir"),
            "tanggal_lahir_almarhum": extra.get("tanggal_lahir"), "usia_tahun": extra.get("usia_tahun"),
            "pekerjaan_almarhum": extra.get("pekerjaan"), "alamat_almarhum": extra.get("alamat"),
            "rt_almarhum": extra.get("rt"), "rw_almarhum": extra.get("rw"),
        }
    if jenis == "kelahiran":
        anak, ayah, ibu = extra.get("anak") or {}, extra.get("ayah") or {}, extra.get("ibu") or {}
        return {
            "gender_anak": anak.get("jk"), "tempat_lahir_anak": anak.get("tempat_lahir"),
            "tgl_lahir_anak": anak.get("tanggal_lahir"), "jam_lahir_anak": anak.get("jam_lahir"),
            "anak_ke": anak.get("anak_ke"),
            "tempat_lahir_ayah": ayah.get("tempat_lahir"), "tanggal_lahir_ayah": ayah.get("tanggal_lahir"),
            "pekerjaan_ayah": ayah.get("pekerjaan"), "alamat_ayah": ayah.get("alamat"),
            "rt_ayah": ayah.get("rt"), "rw_ayah": ayah.get("rw"),
            "tempat_lahir_ibu": ibu.get("tempat_lahir"), "tanggal_lahir_ibu": ibu.get("tanggal_lahir"),
            "pekerjaan_ibu": ibu.get("pekerjaan"), "alamat_ibu": ibu.get("alamat"),
            "rt_ibu": ibu.get("rt"), "rw_ibu": ibu.get("rw"),
        }
    if jenis == "na":
        calon, ayah = extra.get("calon") or {}, extra.get("ayah") or {}
        ibu, csi = extra.get("ibu") or {}, extra.get("csi") or {}
        return {
            "jk_calon": calon.get("jk"), "tempat_lahir_calon": calon.get("tempat_lahir"),
            "tanggal_lahir_calon": calon.get("tanggal_lahir"), "kewarganegaraan": calon.get("kewarganegaraan"),
            "agama_calon": calon.get("agama"), "pekerjaan_calon": calon.get("pekerjaan"),
            "alamat_calon": calon.get("alamat"), "rt_calon": calon.get("rt"), "rw_calon": calon.get("rw"),
            "tempat_lahir_ayah": ayah.get("tempat_lahir"), "tanggal_lahir_ayah": ayah.get("tanggal_lahir"),
            "pekerjaan_ayah": ayah.get("pekerjaan"), "alamat_ayah": ayah.get("alamat"),
            "rt_ayah": ayah.get("rt"), "rw_ayah": ayah.get("rw"), "kel_desa_ayah": ayah.get("kel_desa"),
            "kec_ayah": ayah.get("kec"), "kab_kota_ayah": ayah.get("kab_kota"),
            "tempat_lahir_ibu": ibu.get("tempat_lahir"), "tanggal_lahir_ibu": ibu.get("tanggal_lahir"),
            "pekerjaan_ibu": ibu.get("pekerjaan"), "alamat_ibu": ibu.get("alamat"),
            "rt_ibu": ibu.get("rt"), "rw_ibu": ibu.get("rw"), "kel_desa_ibu": ibu.get("kel_desa"),
            "kec_ibu": ibu.get("kec"), "kab_kota_ibu": ibu.get("kab_kota"),
            "bin_binti_pasangan": csi.get("bin_binti"), "jk_pasangan": csi.get("jk"),
            "ttl_pasangan": csi.get("ttl"), "agama_pasangan": csi.get("agama"),
            "pekerjaan_pasangan": csi.get("pekerjaan"), "alamat_pasangan": csi.get("alamat"),
            "rt_pasangan": csi.get("rt"), "rw_pasangan": csi.get("rw"),
            "kel_desa_pasangan": csi.get("kel_desa"), "kec_pasangan": csi.get("kec"),
            "kab_kota_pasangan": csi.get("kab_kota"), "provinsi_pasangan": csi.get("provinsi"),
            "shdk": csi.get("shdk"),
        }
    if jenis == "kk":
        return {"nama_kk": extra.get("nama_kk"), "dusun": extra.get("dusun")}
    return {}


# Internal bookkeeping columns not useful in an exported spreadsheet.
_EXPORT_SKIP_COLUMNS = {"id", "created_at", "updated_at", "deleted_at"}


async def export_domain_master_excel(session: AsyncSession, jenis: str) -> bytes:
    """Export one domain master-data table to xlsx bytes.

    Columns are introspected from the model (`__table__.columns`) rather
    than hand-listed per type -- each of the 9 domain tables has its own
    column set (MASTER_COLUMN_LETTERS.md), and this avoids 9 near-duplicate
    column lists that would silently drift out of sync whenever a model
    gains a field.
    """
    service_cls = DOMAIN_MASTER_SERVICES.get(jenis)
    if service_cls is None:
        raise ValidationAppError(f"Jenis master data tidak dikenal: {jenis}")
    service = service_cls(session)
    items, _ = await service.list(page=1, size=100000)
    columns = [c.name for c in service.model.__table__.columns if c.name not in _EXPORT_SKIP_COLUMNS]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = service.name[:31]
    ws.append(columns)
    for item in items:
        row = []
        for col in columns:
            value = getattr(item, col)
            if hasattr(value, "isoformat"):
                value = value.isoformat()
            elif value is not None and not isinstance(value, (str, int, float, bool)):
                value = str(value)
            row.append(value)
        ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()
