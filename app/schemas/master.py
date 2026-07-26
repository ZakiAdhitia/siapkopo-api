"""Master data schemas: Create/Update/Read for each master-data entity."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class VillageProfileUpdate(BaseModel):
    name: str | None = None
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None
    description: str | None = None
    photo_path: str | None = None
    kades_name: str | None = None
    kades_photo_path: str | None = None
    sambutan_text: str | None = None
    kontak_alamat: str | None = None
    kontak_telp: str | None = None
    kontak_email: str | None = None
    kontak_jam: str | None = None
    jumlah_jiwa: int | None = None
    jumlah_kk: int | None = None
    luas_wilayah: str | None = None


class VillageProfileRead(_Read):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None
    description: str | None = None
    photo_path: str | None = None
    kades_name: str | None = None
    kades_photo_path: str | None = None
    sambutan_text: str | None = None
    kontak_alamat: str | None = None
    kontak_telp: str | None = None
    kontak_email: str | None = None
    kontak_jam: str | None = None
    jumlah_jiwa: int | None = None
    jumlah_kk: int | None = None
    luas_wilayah: str | None = None


class DusunCreate(BaseModel):
    name: str


class DusunUpdate(BaseModel):
    name: str | None = None


class DusunRead(_Read):
    name: str


class RWCreate(BaseModel):
    dusun_id: UUID
    number: str


class RWUpdate(BaseModel):
    number: str | None = None


class RWRead(_Read):
    dusun_id: UUID
    number: str


class RTCreate(BaseModel):
    rw_id: UUID
    number: str


class RTUpdate(BaseModel):
    number: str | None = None


class RTRead(_Read):
    rw_id: UUID
    number: str


class FamilyCardCreate(BaseModel):
    kk_number: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    address: str | None = None


class FamilyCardUpdate(BaseModel):
    kk_number: str | None = Field(default=None, min_length=16, max_length=16, pattern=r"^\d{16}$")
    address: str | None = None


class FamilyCardRead(_Read):
    kk_number: str
    address: str | None = None


class ResidentCreate(BaseModel):
    nik: str = Field(min_length=16, max_length=16, pattern=r"^\d{16}$")
    full_name: str
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None


class ResidentUpdate(BaseModel):
    full_name: str | None = None
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None


class ResidentRead(_Read):
    nik: str
    full_name: str
    family_card_id: UUID | None = None
    rt_id: UUID | None = None
    gender: str | None = None
    birth_place: str | None = None
    birth_date: date | None = None
    occupation: str | None = None
    phone: str | None = None
    address: str | None = None
    # Populated by the router (not the ORM object): denormalized display
    # fields so resident:read (staff) doesn't need rt:manage/rw:manage/
    # family_card:manage (admin-only) just to show where someone lives --
    # see the master-data screen's requirements. Dusun is deliberately NOT
    # included here (Master Data rework: dusun column dropped from the
    # resident master-data screen).
    kk_number: str | None = None
    rt_number: str | None = None
    rw_number: str | None = None


class ResidentImportError(BaseModel):
    """A single row-level failure from a resident Excel import."""

    row: int
    message: str


class ResidentImportResult(BaseModel):
    """Outcome of a resident Excel import: counts + per-row errors."""

    imported: int
    errors: list[ResidentImportError] = []
