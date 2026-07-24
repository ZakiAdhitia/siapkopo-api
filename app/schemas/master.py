"""Master data schemas: Create/Update/Read for each master-data entity."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


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
    kk_number: str
    address: str | None = None


class FamilyCardUpdate(BaseModel):
    kk_number: str | None = None
    address: str | None = None


class FamilyCardRead(_Read):
    kk_number: str
    address: str | None = None


class ResidentCreate(BaseModel):
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


class ResidentImportError(BaseModel):
    """A single row-level failure from a resident Excel import."""

    row: int
    message: str


class ResidentImportResult(BaseModel):
    """Outcome of a resident Excel import: counts + per-row errors."""

    imported: int
    errors: list[ResidentImportError] = []
