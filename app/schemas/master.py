"""Master data schemas: Create/Update/Read for each master-data entity."""
from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class VillageCreate(BaseModel):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class VillageUpdate(BaseModel):
    name: str | None = None
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class VillageRead(_Read):
    name: str
    slogan: str | None = None
    kecamatan: str | None = None
    kabupaten: str | None = None
    provinsi: str | None = None


class DusunCreate(BaseModel):
    village_id: UUID
    name: str


class DusunUpdate(BaseModel):
    name: str | None = None


class DusunRead(_Read):
    village_id: UUID
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
    village_id: UUID
    kk_number: str
    address: str | None = None


class FamilyCardUpdate(BaseModel):
    kk_number: str | None = None
    address: str | None = None


class FamilyCardRead(_Read):
    village_id: UUID
    kk_number: str
    address: str | None = None


class ResidentCreate(BaseModel):
    village_id: UUID
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
    village_id: UUID
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
