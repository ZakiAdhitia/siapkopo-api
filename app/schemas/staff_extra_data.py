"""Per-jenis validation schemas for Submission.staff_extra_data -- the
letter-specific staff-filled blocks that don't fit the generic 8-field
identity shape (SubmissionMasterDataUpdateRequest, which every jenis still
uses for the identity fields it needs). Registered in
STAFF_EXTRA_DATA_SCHEMA_BY_JENIS, keyed exactly like TEMPLATE_CODE_TO_JENIS's
values (app.services.domain_master)."""
from datetime import date

from pydantic import BaseModel, field_validator


class DomisiliExtraData(BaseModel):
    alamat_asal: str | None = None
    rt_asal: str | None = None
    rw_asal: str | None = None
    kel_desa_asal: str | None = None
    kec_asal: str | None = None
    kab_kota_asal: str | None = None
    provinsi_asal: str | None = None
    masa_berlaku_bulan: str | None = None


class KematianExtraData(BaseModel):
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    usia_tahun: str | None = None
    pekerjaan: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None


class _KelahiranAnak(BaseModel):
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    jam_lahir: str | None = None
    anak_ke: str | None = None


class _OrangTuaBlock(BaseModel):
    """Shape shared by Kelahiran's ayah/ibu blocks."""

    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    pekerjaan: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None


class KelahiranExtraData(BaseModel):
    anak: _KelahiranAnak = _KelahiranAnak()
    ayah: _OrangTuaBlock = _OrangTuaBlock()
    ibu: _OrangTuaBlock = _OrangTuaBlock()


class _NACalon(BaseModel):
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    kewarganegaraan: str | None = None
    agama: str | None = None
    pekerjaan: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None


class _NAOrangTuaBlock(BaseModel):
    """Shape shared by NA's ayah/ibu blocks (adds kel_desa/kec/kab_kota vs.
    Kelahiran's simpler _OrangTuaBlock)."""

    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    pekerjaan: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None
    kel_desa: str | None = None
    kec: str | None = None
    kab_kota: str | None = None


class _NACsi(BaseModel):
    bin_binti: str | None = None
    jk: str | None = None
    ttl: str | None = None
    agama: str | None = None
    pekerjaan: str | None = None
    alamat: str | None = None
    rt: str | None = None
    rw: str | None = None
    kel_desa: str | None = None
    kec: str | None = None
    kab_kota: str | None = None
    provinsi: str | None = None
    shdk: str | None = None


class NAExtraData(BaseModel):
    calon: _NACalon = _NACalon()
    ayah: _NAOrangTuaBlock = _NAOrangTuaBlock()
    ibu: _NAOrangTuaBlock = _NAOrangTuaBlock()
    csi: _NACsi = _NACsi()


class _KKAnggota(BaseModel):
    nik: str | None = None
    nama: str | None = None
    jk: str | None = None
    tempat_lahir: str | None = None
    tanggal_lahir: date | None = None
    agama: str | None = None
    pendidikan: str | None = None
    pekerjaan: str | None = None
    status_kawin: str | None = None
    shdk: str | None = None
    wni_wna: str | None = None


class KKExtraData(BaseModel):
    nama_kk: str | None = None
    dusun: str | None = None
    anggota: list[_KKAnggota] = []
    nama_ayah: str | None = None
    nama_ibu: str | None = None

    @field_validator("anggota")
    @classmethod
    def _max_10_anggota(cls, value: list[_KKAnggota]) -> list[_KKAnggota]:
        if len(value) > 10:
            raise ValueError("Maksimal 10 anggota keluarga")
        return value


STAFF_EXTRA_DATA_SCHEMA_BY_JENIS: dict[str, type[BaseModel] | None] = {
    "domisili": DomisiliExtraData,
    "kematian": KematianExtraData,
    "kelahiran": KelahiranExtraData,
    "na": NAExtraData,
    "kk": KKExtraData,
    "sku": None,
    "uhc": None,
    "pindah": None,
    "ubah_data": None,
}
