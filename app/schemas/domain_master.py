"""Read-only schemas for the per-letter-type domain master tables.

These tables are populated automatically by SubmissionService._save_to_domain_master
on issuance (see app/models/master.py's module docstring for the
MASTER_COLUMN_LETTERS.md column-shape rationale) -- there is deliberately no
Create/Update schema here, only Read, since staff browse this data rather
than editing it directly.

Every Read schema carries `column_converted`: a static {column_key: "Label"}
map (same content as the ORM model's `column_converted` property) so the
client can render human-readable table headers.
"""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    submission_id: UUID | None = None


class MasterDomisiliRead(_Read):
    tgl_surat: date | None = None
    nama: str
    jk: str | None = None
    ttl: str | None = None
    pkj: str | None = None
    status: str | None = None
    nik: str
    almt_asal: str | None = None
    rt_asal: str | None = None
    rw_asal: str | None = None
    kelurahan_atau_desa_asal: str | None = None
    kecamatan_asal: str | None = None
    kabupaten_atau_kota_asal: str | None = None
    provinsi_asal: str | None = None
    almt_domisili: str | None = None
    rt_domisili: str | None = None
    rw_domisili: str | None = None
    persyaratan: str | None = None
    berlaku: date | None = None
    column_converted: dict[str, str]


class MasterKelahiranRead(_Read):
    jk: str | None = None
    nama_anak: str
    anak_ke: str | None = None
    lahir_hari: str | None = None
    tempat_lahir: str | None = None
    ttl_anak: str | None = None
    jam_lahir: str | None = None
    nama_ayah: str | None = None
    ttl_ayah: str | None = None
    pkj_ayah: str | None = None
    nik_ayah: str | None = None
    almt_ayah: str | None = None
    rt_almt_ayah: str | None = None
    rw_almt_ayah: str | None = None
    nama_ibu: str | None = None
    ttl_ibu: str | None = None
    pkj_ibu: str | None = None
    nik_ibu: str | None = None
    almt_ibu: str | None = None
    rt_almt_ibu: str | None = None
    rw_almt_ibu: str | None = None
    tgl_surat: date | None = None
    column_converted: dict[str, str]


class MasterKematianRead(_Read):
    tgl_surat: date | None = None
    nama: str
    jk: str | None = None
    nik: str
    usia: str | None = None
    pkj: str | None = None
    almt: str | None = None
    rt: str | None = None
    rw: str | None = None
    hari: str | None = None
    tgl_meninggal: date | None = None
    jam: str | None = None
    lokasi_meninggal: str | None = None
    alasan_meninggal: str | None = None
    column_converted: dict[str, str]


class MasterSKURead(_Read):
    nama: str
    nik: str
    ttl: str | None = None
    jk: str | None = None
    pkj: str | None = None
    status: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None
    jenis_usaha: str
    lokasi_usaha: str | None = None
    rt_lokasi_usaha: str | None = None
    rw_lokasi_usaha: str | None = None
    desa: str | None = None
    persyaratan: str | None = None
    tgl_surat: date | None = None
    column_converted: dict[str, str]


class MasterNARead(_Read):
    tgl_surat: date | None = None
    nama: str
    nik: str
    jk: str | None = None
    ttl: str | None = None
    kewarganegaraan: str | None = None
    agama: str | None = None
    pkj: str | None = None
    almt: str | None = None
    rt: str | None = None
    rw: str | None = None
    janda_atau_duda: str | None = None
    jumlah_istri: str | None = None
    perawan_atau_janda: str | None = None
    nomor_akta_cerai: str | None = None
    suami_atau_istri_terdahulu: str | None = None
    ayah: str | None = None
    nik_ayah: str | None = None
    ttl_ayah: str | None = None
    pkj_ayah: str | None = None
    almt_ayah: str | None = None
    rt_almt_ayah: str | None = None
    rw_almt_ayah: str | None = None
    kelurahan_atau_desa_ayah: str | None = None
    kecamatan_ayah: str | None = None
    kabupaten_atau_kota_ayah: str | None = None
    ibu: str | None = None
    nik_ibu: str | None = None
    ttl_ibu: str | None = None
    pkj_ibu: str | None = None
    alamat_ibu: str | None = None
    rt_almt_ibu: str | None = None
    rw_almt_ibu: str | None = None
    kelurahan_atau_desa_ibu: str | None = None
    kecamatan_ibu: str | None = None
    kabupaten_atau_kota_ibu: str | None = None
    calon_suami_atau_istri: str | None = None
    bin_atau_binti: str | None = None
    nik_csi: str | None = None
    jk_csi: str | None = None
    ttl_csi: str | None = None
    agama_csi: str | None = None
    pkj_csi: str | None = None
    almt_csi: str | None = None
    rt_csi: str | None = None
    rw_csi: str | None = None
    kelurahan_atau_desa_csi: str | None = None
    kecamatan_csi: str | None = None
    kabupaten_atau_kota_csi: str | None = None
    provinsi_csi: str | None = None
    shdk: str | None = None
    hari: str | None = None
    column_converted: dict[str, str]


class MasterUHCRead(_Read):
    tgl_surat: date | None = None
    nama_pasien: str
    nik_pasien: str
    ttl_pasien: str | None = None
    jk: str | None = None
    status: str | None = None
    pekerjaan: str | None = None
    nama_kepala_keluarga: str | None = None
    nik_kepala_keluarga: str | None = None
    nama_pemohon: str | None = None
    nik_pemohon: str | None = None
    no_kk: str | None = None
    tgl_dikeluarkan_kk: date | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None
    terdaftar_dtks: str | None = None
    peruntukan: str | None = None
    rujukan: str | None = None
    nama_2: str | None = None
    nik_2: str | None = None
    nama_3: str | None = None
    nik_3: str | None = None
    nama_4: str | None = None
    nik_4: str | None = None
    nama_5: str | None = None
    nik_5: str | None = None
    nama_6: str | None = None
    nik_6: str | None = None
    nama_7: str | None = None
    nik_7: str | None = None
    nama_8: str | None = None
    nik_8: str | None = None
    nama_9: str | None = None
    nik_9: str | None = None
    nama_10: str | None = None
    nik_10: str | None = None
    nama_ketua_rt: str | None = None
    column_converted: dict[str, str]


class MasterKKRead(_Read):
    no_kk: str | None = None
    nama_kk: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None
    dusun: str | None = None
    nama1: str | None = None
    nama2: str | None = None
    nama3: str | None = None
    nama4: str | None = None
    nama5: str | None = None
    nama6: str | None = None
    nama7: str | None = None
    nama8: str | None = None
    nama9: str | None = None
    nama10: str | None = None
    nik1: str | None = None
    nik2: str | None = None
    nik3: str | None = None
    nik4: str | None = None
    nik5: str | None = None
    nik6: str | None = None
    nik7: str | None = None
    nik8: str | None = None
    nik9: str | None = None
    nik10: str | None = None
    jkel1: str | None = None
    jkel2: str | None = None
    jkel3: str | None = None
    jkel4: str | None = None
    jkel5: str | None = None
    jkel6: str | None = None
    jkel7: str | None = None
    jkel8: str | None = None
    jkel9: str | None = None
    jkel10: str | None = None
    tmpLahir1: str | None = None
    tmpLahir2: str | None = None
    tmpLahir3: str | None = None
    tmpLahir4: str | None = None
    tmpLahir5: str | None = None
    tmpLahir6: str | None = None
    tmpLahir7: str | None = None
    tmpLahir8: str | None = None
    tmpLahir9: str | None = None
    tmpLahir10: str | None = None
    tglLahir1: date | None = None
    tglLahir2: date | None = None
    tglLahir3: date | None = None
    tglLahir4: date | None = None
    tglLahir5: date | None = None
    tglLahir6: date | None = None
    tglLahir7: date | None = None
    tglLahir8: date | None = None
    tglLahir9: date | None = None
    tglLahir10: date | None = None
    agama1: str | None = None
    agama2: str | None = None
    agama3: str | None = None
    agama4: str | None = None
    agama5: str | None = None
    agama6: str | None = None
    agama7: str | None = None
    agama8: str | None = None
    agama9: str | None = None
    agama10: str | None = None
    pend1: str | None = None
    pend2: str | None = None
    pend3: str | None = None
    pend4: str | None = None
    pend5: str | None = None
    pend6: str | None = None
    pend7: str | None = None
    pend8: str | None = None
    pend9: str | None = None
    pend10: str | None = None
    pekrj1: str | None = None
    pekrj2: str | None = None
    pekrj3: str | None = None
    pekrj4: str | None = None
    pekrj5: str | None = None
    pekrj6: str | None = None
    pekrj7: str | None = None
    pekrj8: str | None = None
    pekrj9: str | None = None
    pekrj10: str | None = None
    status1: str | None = None
    status2: str | None = None
    status3: str | None = None
    status4: str | None = None
    status5: str | None = None
    status6: str | None = None
    status7: str | None = None
    status8: str | None = None
    status9: str | None = None
    status10: str | None = None
    shdk1: str | None = None
    shdk2: str | None = None
    shdk3: str | None = None
    shdk4: str | None = None
    shdk5: str | None = None
    shdk6: str | None = None
    shdk7: str | None = None
    shdk8: str | None = None
    shdk9: str | None = None
    shdk10: str | None = None
    wnia1: str | None = None
    wnia2: str | None = None
    wnia3: str | None = None
    wnia4: str | None = None
    wnia5: str | None = None
    wnia6: str | None = None
    wnia7: str | None = None
    wnia8: str | None = None
    wnia9: str | None = None
    wnia10: str | None = None
    namaAyah1: str | None = None
    namaAyah2: str | None = None
    namaAyah3: str | None = None
    namaAyah4: str | None = None
    namaAyah5: str | None = None
    namaAyah6: str | None = None
    namaAyah7: str | None = None
    namaAyah8: str | None = None
    namaAyah9: str | None = None
    namaAyah10: str | None = None
    namaIbu1: str | None = None
    namaIbu2: str | None = None
    namaIbu3: str | None = None
    namaIbu4: str | None = None
    namaIbu5: str | None = None
    namaIbu6: str | None = None
    namaIbu7: str | None = None
    namaIbu8: str | None = None
    namaIbu9: str | None = None
    namaIbu10: str | None = None
    tgl_surat: date | None = None
    nama_rt: str | None = None
    nama_rw: str | None = None
    column_converted: dict[str, str]


class MasterPindahRead(_Read):
    tgl_surat: date | None = None
    nama_pemohon: str
    nik_pemohon: str
    no_kk: str | None = None
    alamat_asal: str | None = None
    alamat_tujuan: str | None = None
    rt_tujuan: str | None = None
    rw_tujuan: str | None = None
    kel_desa_tujuan: str | None = None
    kec_tujuan: str | None = None
    kab_kota_tujuan: str | None = None
    provinsi_tujuan: str | None = None
    klasifikasi_kepindahan: str | None = None
    alasan_pindah: str | None = None
    jenis_kepindahan: str | None = None
    anggota_yang_ikut: int | None = None
    daftar_anggota_pindah: str | None = None


class MasterUbahDataRead(_Read):
    tgl_surat: date | None = None
    nama: str
    nik: str
    no_kk: str | None = None
    alamat: str | None = None
    elemen_diubah: str | None = None
    data_lama: str | None = None
    data_baru: str | None = None
    alasan_perubahan: str | None = None
