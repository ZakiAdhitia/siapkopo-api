"""Master data models: village hierarchy (RW/RT/VillageProfile) and the 9
per-letter-type domain master tables. No population registry (Resident/
FamilyCard) -- removed 2026-08-06, couldn't be kept up to date (see
SISTEM_PENGOLAHAN_DATA_WARGA.md); a submission's applicant is now just
nik+nama on Submission itself, and staff fills each letter's own domain
master row from KTP/KK photos via the submission detail page."""
import uuid
from dataclasses import dataclass
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


@dataclass(frozen=True)
class VillageProfile:
    """Fixed identity of the (single) village this system serves.

    Hardcoded, not a database table -- multi-desa support was explicitly
    removed (see CLAUDE.md), so there is nothing to configure per-tenant.
    Consumed as the letterhead/report-header data source across letter PDF
    rendering (``app.services.template_render``), dashboard export, and
    attendance report export via ``VillageProfileService.get()``.
    """

    name: str = "Kopo"
    kecamatan: str = "Cisarua"
    kabupaten: str = "Bogor"
    provinsi: str = "Jawa Barat"


class RW(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A neighborhood association (rukun warga)."""

    __tablename__ = "rw"
    number: Mapped[str] = mapped_column(String(10))


class RT(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A neighborhood unit (rukun tetangga) belonging to an RW."""

    __tablename__ = "rt"
    rw_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("rw.id"), index=True)
    number: Mapped[str] = mapped_column(String(10))


# ---------------------------------------------------------------------------
# Domain-specific master data (Bagian "Master Data per Jenis Surat")
# ---------------------------------------------------------------------------
# Column shapes below follow MASTER_COLUMN_LETTERS.md verbatim (the client's
# own canonical column list for each master table), NOT a re-derivation from
# the Excel files -- where that spec conflicts with the earlier Excel-mirror
# pass, the spec wins. Three token-level typos were normalized while
# transcribing (obvious breaks in an otherwise consistent naming pattern,
# not deliberate choices): "nik_#" -> "nik_3" (sequence nik_2/nik_3/nik_4),
# "alammat_ibu" -> "alamat_ibu", "kabupaten_atau_desa_csi" ->
# "kabupaten_atau_kota_csi" (every sibling *_ayah/*_ibu column uses
# "kabupaten_atau_kota"). `master_kematian`'s spec list omits NIK entirely;
# kept anyway (bare `nik`, matching this table's own no-suffix convention)
# since the earlier direct Excel read confirmed the real sheet has one and
# dropping identity tracking from a death record is a real regression, not
# a style choice. Every model also keeps `submission_id` plus the standard
# id/timestamp/soft-delete columns -- infrastructure, not "form input",
# which is the spec file's own stated scope.
#
# Each model also carries a `column_converted` property: a static
# {column_key: "Kepanjangan"} label map (MASTER_COLUMN_LETTERS.md item 7),
# serialized by the matching Read schema so the client can render readable
# table headers instead of raw abbreviated keys.


class MasterDomisili(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for domicile certificate applications.

    Column set per MASTER_COLUMN_LETTERS.md item 1.
    """

    __tablename__ = "master_domisili"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama: Mapped[str] = mapped_column(String(150))
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttl: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pkj: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    nik: Mapped[str] = mapped_column(String(20), index=True)
    # Alamat asal (sesuai KTP/KK) -- often outside Desa Kopo entirely (the
    # whole point of a domicile letter), so this is always form input, never
    # looked up from VillageProfile.
    almt_asal: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_asal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_asal: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kelurahan_atau_desa_asal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kecamatan_asal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten_atau_kota_asal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi_asal: Mapped[str | None] = mapped_column(String(100), nullable=True)
    almt_domisili: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_domisili: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_domisili: Mapped[str | None] = mapped_column(String(10), nullable=True)
    persyaratan: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Actual computed expiry date (issued_at + masa_berlaku_bulan), matching
    # the sheet's "BERLAKU" column -- not the raw duration picked on the form.
    berlaku: Mapped[date | None] = mapped_column(Date, nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "tgl_surat": "Tanggal Surat", "nama": "Nama", "jk": "Jenis Kelamin",
        "ttl": "Tempat Tanggal Lahir", "pkj": "Pekerjaan", "status": "Status Perkawinan",
        "nik": "Nomor Induk Kependudukan", "almt_asal": "Alamat Asal",
        "rt_asal": "RT Asal", "rw_asal": "RW Asal",
        "kelurahan_atau_desa_asal": "Kelurahan/Desa Asal", "kecamatan_asal": "Kecamatan Asal",
        "kabupaten_atau_kota_asal": "Kabupaten/Kota Asal", "provinsi_asal": "Provinsi Asal",
        "almt_domisili": "Alamat Domisili", "rt_domisili": "RT Domisili",
        "rw_domisili": "RW Domisili", "persyaratan": "Persyaratan",
        "berlaku": "Berlaku Sampai Dengan",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterKelahiran(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for birth certificate applications.

    Column set per MASTER_COLUMN_LETTERS.md item 2.
    """

    __tablename__ = "master_kelahiran"
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_anak: Mapped[str] = mapped_column(String(150), index=True)
    anak_ke: Mapped[str | None] = mapped_column(String(50), nullable=True)
    lahir_hari: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tempat_lahir: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ttl_anak: Mapped[str | None] = mapped_column(String(150), nullable=True)
    jam_lahir: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_ayah: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ttl_ayah: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pkj_ayah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nik_ayah: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    almt_ayah: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_almt_ayah: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_almt_ayah: Mapped[str | None] = mapped_column(String(10), nullable=True)
    nama_ibu: Mapped[str | None] = mapped_column(String(150), nullable=True)
    ttl_ibu: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pkj_ibu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nik_ibu: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    almt_ibu: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_almt_ibu: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_almt_ibu: Mapped[str | None] = mapped_column(String(10), nullable=True)
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "jk": "Jenis Kelamin Anak", "nama_anak": "Nama Anak", "anak_ke": "Anak Ke",
        "lahir_hari": "Hari Lahir", "tempat_lahir": "Tempat Lahir",
        "ttl_anak": "Tempat Tanggal Lahir Anak", "jam_lahir": "Jam Lahir",
        "nama_ayah": "Nama Ayah", "ttl_ayah": "Tempat Tanggal Lahir Ayah",
        "pkj_ayah": "Pekerjaan Ayah", "nik_ayah": "NIK Ayah", "almt_ayah": "Alamat Ayah",
        "rt_almt_ayah": "RT Alamat Ayah", "rw_almt_ayah": "RW Alamat Ayah",
        "nama_ibu": "Nama Ibu", "ttl_ibu": "Tempat Tanggal Lahir Ibu",
        "pkj_ibu": "Pekerjaan Ibu", "nik_ibu": "NIK Ibu", "almt_ibu": "Alamat Ibu",
        "rt_almt_ibu": "RT Alamat Ibu", "rw_almt_ibu": "RW Alamat Ibu",
        "tgl_surat": "Tanggal Surat",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterKematian(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for death certificate applications.

    Column set per MASTER_COLUMN_LETTERS.md item 3 (plus `nik`, see module
    docstring).
    """

    __tablename__ = "master_kematian"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama: Mapped[str] = mapped_column(String(150))
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik: Mapped[str] = mapped_column(String(20), index=True)
    usia: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pkj: Mapped[str | None] = mapped_column(String(100), nullable=True)
    almt: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    hari: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tgl_meninggal: Mapped[date | None] = mapped_column(Date, nullable=True)
    jam: Mapped[str | None] = mapped_column(String(20), nullable=True)
    lokasi_meninggal: Mapped[str | None] = mapped_column(String(150), nullable=True)
    alasan_meninggal: Mapped[str | None] = mapped_column(String(255), nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "tgl_surat": "Tanggal Surat", "nama": "Nama Almarhum/Almarhumah",
        "jk": "Jenis Kelamin", "nik": "Nomor Induk Kependudukan", "usia": "Usia",
        "pkj": "Pekerjaan", "almt": "Alamat", "rt": "RT", "rw": "RW",
        "hari": "Hari Meninggal", "tgl_meninggal": "Tanggal Meninggal",
        "jam": "Jam Meninggal", "lokasi_meninggal": "Lokasi Meninggal",
        "alasan_meninggal": "Alasan/Sebab Meninggal",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterSKU(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for business certificate (SKU) applications.

    Column set per MASTER_COLUMN_LETTERS.md item 5.
    """

    __tablename__ = "master_sku"
    nama: Mapped[str] = mapped_column(String(150))
    nik: Mapped[str] = mapped_column(String(20), index=True)
    ttl: Mapped[str | None] = mapped_column(String(150), nullable=True)
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    pkj: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    alamat: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    jenis_usaha: Mapped[str] = mapped_column(String(150))
    lokasi_usaha: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_lokasi_usaha: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_lokasi_usaha: Mapped[str | None] = mapped_column(String(10), nullable=True)
    desa: Mapped[str | None] = mapped_column(String(100), nullable=True)
    persyaratan: Mapped[str | None] = mapped_column(Text, nullable=True)
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "nama": "Nama Pemohon", "nik": "NIK Pemohon", "ttl": "Tempat Tanggal Lahir",
        "jk": "Jenis Kelamin", "pkj": "Pekerjaan", "status": "Status Perkawinan",
        "alamat": "Alamat", "rt": "RT", "rw": "RW", "jenis_usaha": "Jenis Usaha",
        "lokasi_usaha": "Lokasi Usaha", "rt_lokasi_usaha": "RT Lokasi Usaha",
        "rw_lokasi_usaha": "RW Lokasi Usaha", "desa": "Desa",
        "persyaratan": "Persyaratan", "tgl_surat": "Tanggal Surat",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterNA(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for marriage recommendation (NA) applications.

    Column set per MASTER_COLUMN_LETTERS.md item 4 -- calon + both parents +
    the intended spouse (csi = "calon suami/istri"), each with their own
    address breakdown.
    """

    __tablename__ = "master_na"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    # --- Calon (pemohon) ---
    nama: Mapped[str] = mapped_column(String(150))
    nik: Mapped[str] = mapped_column(String(20), index=True)
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttl: Mapped[str | None] = mapped_column(String(150), nullable=True)
    kewarganegaraan: Mapped[str | None] = mapped_column(String(50), nullable=True)
    agama: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pkj: Mapped[str | None] = mapped_column(String(100), nullable=True)
    almt: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    janda_atau_duda: Mapped[str | None] = mapped_column(String(50), nullable=True)
    jumlah_istri: Mapped[str | None] = mapped_column(String(50), nullable=True)
    perawan_atau_janda: Mapped[str | None] = mapped_column(String(50), nullable=True)
    nomor_akta_cerai: Mapped[str | None] = mapped_column(String(100), nullable=True)
    suami_atau_istri_terdahulu: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # --- Ayah kandung ---
    ayah: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_ayah: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttl_ayah: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pkj_ayah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    almt_ayah: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_almt_ayah: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_almt_ayah: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kelurahan_atau_desa_ayah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kecamatan_ayah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten_atau_kota_ayah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # --- Ibu kandung ---
    ibu: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_ibu: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttl_ibu: Mapped[str | None] = mapped_column(String(150), nullable=True)
    pkj_ibu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alamat_ibu: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_almt_ibu: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_almt_ibu: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kelurahan_atau_desa_ibu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kecamatan_ibu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten_atau_kota_ibu: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # --- Calon Suami/Istri (pasangan, boleh dari desa lain) ---
    calon_suami_atau_istri: Mapped[str | None] = mapped_column(String(150), nullable=True)
    bin_atau_binti: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_csi: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    jk_csi: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ttl_csi: Mapped[str | None] = mapped_column(String(150), nullable=True)
    agama_csi: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pkj_csi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    almt_csi: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_csi: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_csi: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kelurahan_atau_desa_csi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kecamatan_csi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten_atau_kota_csi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi_csi: Mapped[str | None] = mapped_column(String(100), nullable=True)
    shdk: Mapped[str | None] = mapped_column(String(50), nullable=True)
    hari: Mapped[str | None] = mapped_column(String(20), nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "tgl_surat": "Tanggal Surat", "nama": "Nama Calon", "nik": "NIK Calon",
        "jk": "Jenis Kelamin", "ttl": "Tempat Tanggal Lahir",
        "kewarganegaraan": "Kewarganegaraan", "agama": "Agama", "pkj": "Pekerjaan",
        "almt": "Alamat", "rt": "RT", "rw": "RW",
        "janda_atau_duda": "Jejaka/Duda", "jumlah_istri": "Jumlah Istri",
        "perawan_atau_janda": "Perawan/Janda", "nomor_akta_cerai": "Nomor Akta Cerai",
        "suami_atau_istri_terdahulu": "Suami/Istri Terdahulu",
        "ayah": "Nama Ayah", "nik_ayah": "NIK Ayah", "ttl_ayah": "Tempat Tanggal Lahir Ayah",
        "pkj_ayah": "Pekerjaan Ayah", "almt_ayah": "Alamat Ayah",
        "rt_almt_ayah": "RT Alamat Ayah", "rw_almt_ayah": "RW Alamat Ayah",
        "kelurahan_atau_desa_ayah": "Kelurahan/Desa Ayah", "kecamatan_ayah": "Kecamatan Ayah",
        "kabupaten_atau_kota_ayah": "Kabupaten/Kota Ayah",
        "ibu": "Nama Ibu", "nik_ibu": "NIK Ibu", "ttl_ibu": "Tempat Tanggal Lahir Ibu",
        "pkj_ibu": "Pekerjaan Ibu", "alamat_ibu": "Alamat Ibu",
        "rt_almt_ibu": "RT Alamat Ibu", "rw_almt_ibu": "RW Alamat Ibu",
        "kelurahan_atau_desa_ibu": "Kelurahan/Desa Ibu", "kecamatan_ibu": "Kecamatan Ibu",
        "kabupaten_atau_kota_ibu": "Kabupaten/Kota Ibu",
        "calon_suami_atau_istri": "Calon Suami/Istri", "bin_atau_binti": "Bin/Binti",
        "nik_csi": "NIK Calon Suami/Istri", "jk_csi": "Jenis Kelamin Calon Suami/Istri",
        "ttl_csi": "Tempat Tanggal Lahir Calon Suami/Istri", "agama_csi": "Agama Calon Suami/Istri",
        "pkj_csi": "Pekerjaan Calon Suami/Istri", "almt_csi": "Alamat Calon Suami/Istri",
        "rt_csi": "RT Calon Suami/Istri", "rw_csi": "RW Calon Suami/Istri",
        "kelurahan_atau_desa_csi": "Kelurahan/Desa Calon Suami/Istri",
        "kecamatan_csi": "Kecamatan Calon Suami/Istri",
        "kabupaten_atau_kota_csi": "Kabupaten/Kota Calon Suami/Istri",
        "provinsi_csi": "Provinsi Calon Suami/Istri",
        "shdk": "Status Hubungan Dalam Keluarga", "hari": "Hari",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterUHC(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for UHC (BPJS PBI/DTKS) referral applications.

    Column set per MASTER_COLUMN_LETTERS.md item 6: patient, applicant, and
    head-of-family are three potentially different people, plus up to 9
    other family members as discrete nama_N/nik_N column pairs (2..10).
    """

    __tablename__ = "master_uhc"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama_pasien: Mapped[str] = mapped_column(String(150))
    nik_pasien: Mapped[str] = mapped_column(String(20), index=True)
    ttl_pasien: Mapped[str | None] = mapped_column(String(150), nullable=True)
    jk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pekerjaan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nama_kepala_keluarga: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_kepala_keluarga: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_pemohon: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_pemohon: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    no_kk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tgl_dikeluarkan_kk: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Added Fase 1 (2026-08-08): the citizen form has always asked these two
    # (see letter_template_data.py's "uhc" fields), but _save_to_domain_master
    # never had a column to save them into -- silent data loss, fixed here.
    tanggal_pengantar_rt: Mapped[date | None] = mapped_column(Date, nullable=True)
    keperluan: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alamat: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    terdaftar_dtks: Mapped[str | None] = mapped_column(String(10), nullable=True)
    peruntukan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rujukan: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama_2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_2: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_3: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_3: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_4: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_4: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_5: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_5: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_6: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_6: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_7: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_7: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_8: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_8: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_9: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_9: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_10: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik_10: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_ketua_rt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _LABELS = {
        "tgl_surat": "Tanggal Surat", "nama_pasien": "Nama Pasien", "nik_pasien": "NIK Pasien",
        "ttl_pasien": "Tempat Tanggal Lahir Pasien", "jk": "Jenis Kelamin", "status": "Status Perkawinan",
        "pekerjaan": "Pekerjaan", "nama_kepala_keluarga": "Nama Kepala Keluarga",
        "nik_kepala_keluarga": "NIK Kepala Keluarga", "nama_pemohon": "Nama Pemohon",
        "nik_pemohon": "NIK Pemohon", "no_kk": "Nomor KK",
        "tgl_dikeluarkan_kk": "Tanggal Dikeluarkan KK", "tanggal_pengantar_rt": "Tanggal Surat Pengantar RT", "keperluan": "Keperluan", "alamat": "Alamat", "rt": "RT", "rw": "RW",
        "terdaftar_dtks": "Terdaftar DTKS", "peruntukan": "Peruntukan", "rujukan": "Rujukan",
        **{f"nama_{i}": f"Nama Anggota Keluarga {i}" for i in range(2, 11)},
        **{f"nik_{i}": f"NIK Anggota Keluarga {i}" for i in range(2, 11)},
        "nama_ketua_rt": "Nama Ketua RT",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterKK(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for family card (KK) applications.

    Column set per MASTER_COLUMN_LETTERS.md item 7 (added 2026-08-01,
    F1.02/F1.06 format) -- up to 10 family members, each with 13 attributes
    (nama/nik/jkel/tmpLahir/tglLahir/agama/pend/pekrj/status/shdk/wnia/
    namaAyah/namaIbu). Column names for the per-member fields intentionally
    keep the spec's own camelCase-with-trailing-index convention (not this
    codebase's usual snake_case) since it mirrors the source form's own
    field naming; only the one clear typo ("namaAayah" -> "namaAyah") was
    normalized. KK's real per-member data COLLECTION (the actual F1.02/F1.06
    submission form) is still deferred -- this table is schema-ready and
    mapped best-effort from what the current (simplified) KK form already
    asks; the memberN columns stay null until that form is built.
    """

    __tablename__ = "master_kk"
    no_kk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nama_kk: Mapped[str | None] = mapped_column(String(150), nullable=True)
    alamat: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    dusun: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nama1: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama3: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama4: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama5: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama6: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama7: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama8: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama9: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama10: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nik1: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik2: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik3: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik4: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik5: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik6: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik7: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik8: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik9: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nik10: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel1: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel2: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel3: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel4: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel5: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel6: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel7: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel8: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel9: Mapped[str | None] = mapped_column(String(20), nullable=True)
    jkel10: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tmpLahir1: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir2: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir3: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir4: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir5: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir6: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir7: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir8: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir9: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tmpLahir10: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tglLahir1: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir2: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir3: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir4: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir5: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir6: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir7: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir8: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir9: Mapped[date | None] = mapped_column(Date, nullable=True)
    tglLahir10: Mapped[date | None] = mapped_column(Date, nullable=True)
    agama1: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama2: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama3: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama4: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama5: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama6: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama7: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama8: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama9: Mapped[str | None] = mapped_column(String(30), nullable=True)
    agama10: Mapped[str | None] = mapped_column(String(30), nullable=True)
    pend1: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend2: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend3: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend4: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend5: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend6: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend7: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend8: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend9: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pend10: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pekrj1: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj2: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj3: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj4: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj5: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj6: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj7: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj8: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj9: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pekrj10: Mapped[str | None] = mapped_column(String(100), nullable=True)
    status1: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status2: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status3: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status4: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status5: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status6: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status7: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status8: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status9: Mapped[str | None] = mapped_column(String(30), nullable=True)
    status10: Mapped[str | None] = mapped_column(String(30), nullable=True)
    shdk1: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk2: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk3: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk4: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk5: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk6: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk7: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk8: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk9: Mapped[str | None] = mapped_column(String(50), nullable=True)
    shdk10: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia1: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia2: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia3: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia4: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia5: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia6: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia7: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia8: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia9: Mapped[str | None] = mapped_column(String(50), nullable=True)
    wnia10: Mapped[str | None] = mapped_column(String(50), nullable=True)
    namaAyah1: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah3: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah4: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah5: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah6: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah7: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah8: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah9: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaAyah10: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu1: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu2: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu3: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu4: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu5: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu6: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu7: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu8: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu9: Mapped[str | None] = mapped_column(String(150), nullable=True)
    namaIbu10: Mapped[str | None] = mapped_column(String(150), nullable=True)
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama_rt: Mapped[str | None] = mapped_column(String(150), nullable=True)
    nama_rw: Mapped[str | None] = mapped_column(String(150), nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

    _MEMBER_LABELS = {
        "nama": "Nama", "nik": "NIK", "jkel": "Jenis Kelamin", "tmpLahir": "Tempat Lahir",
        "tglLahir": "Tanggal Lahir", "agama": "Agama", "pend": "Pendidikan", "pekrj": "Pekerjaan",
        "status": "Status Perkawinan", "shdk": "Status Hubungan Dalam Keluarga",
        "wnia": "Kewarganegaraan", "namaAyah": "Nama Ayah", "namaIbu": "Nama Ibu",
    }
    _LABELS = {
        "no_kk": "Nomor KK", "nama_kk": "Nama Kepala Keluarga", "alamat": "Alamat",
        "rt": "RT", "rw": "RW", "dusun": "Dusun",
        **{
            f"{prefix}{i}": f"{label} Anggota {i}"
            for prefix, label in _MEMBER_LABELS.items()
            for i in range(1, 11)
        },
        "tgl_surat": "Tanggal Surat", "nama_rt": "Nama Ketua RT", "nama_rw": "Nama Ketua RW",
    }

    @property
    def column_converted(self) -> dict[str, str]:
        return self._LABELS


class MasterPindah(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for outbound move (pindah) cover letters.

    The real Disdukcapil form (F-1.03) has far more checkbox classification
    than a village pengantar needs; this keeps the village-relevant subset
    (structured destination address + why/how + who's moving) rather than
    replicating every Disdukcapil checkbox as its own column.
    """

    __tablename__ = "master_pindah"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama_pemohon: Mapped[str] = mapped_column(String(150))
    nik_pemohon: Mapped[str] = mapped_column(String(20), index=True)
    no_kk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alamat_asal: Mapped[str | None] = mapped_column(Text, nullable=True)
    alamat_tujuan: Mapped[str | None] = mapped_column(Text, nullable=True)
    rt_tujuan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    rw_tujuan: Mapped[str | None] = mapped_column(String(10), nullable=True)
    kel_desa_tujuan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kec_tujuan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kab_kota_tujuan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi_tujuan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    klasifikasi_kepindahan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    alasan_pindah: Mapped[str | None] = mapped_column(String(100), nullable=True)
    jenis_kepindahan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    anggota_yang_ikut: Mapped[int | None] = mapped_column(nullable=True)
    # "Nama - NIK - SHDK" per line -- one free-text field instead of discrete
    # columns per member, since this table isn't covered by
    # MASTER_COLUMN_LETTERS.md (pindah/kk are the two tables it omits).
    daftar_anggota_pindah: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)


class MasterUbahData(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Domain-specific master data for population-data-element change
    (F-1.06 "Surat Pernyataan Perubahan Elemen Data Kependudukan") requests.

    Not covered by MASTER_COLUMN_LETTERS.md (a later addition, 2026-08-03,
    per ALUR_PENGAJUAN_UBAH_DATA.md) -- kept as a flat one-change-per-
    submission record like MasterPindah rather than MasterKK's per-member
    column style, since the citizen form only asks for a single elemen/data
    lama/data baru per submission, not a whole family table.
    """

    __tablename__ = "master_ubah_data"
    tgl_surat: Mapped[date | None] = mapped_column(Date, nullable=True)
    nama: Mapped[str] = mapped_column(String(150))
    nik: Mapped[str] = mapped_column(String(20), index=True)
    no_kk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alamat: Mapped[str | None] = mapped_column(Text, nullable=True)
    elemen_diubah: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_lama: Mapped[str | None] = mapped_column(String(255), nullable=True)
    data_baru: Mapped[str | None] = mapped_column(String(255), nullable=True)
    alasan_perubahan: Mapped[str | None] = mapped_column(Text, nullable=True)
    submission_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True, index=True)

