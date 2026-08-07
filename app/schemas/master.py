"""Master data schemas: Create/Update/Read for each master-data entity."""
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class _Read(BaseModel):
    """Common base for Read schemas: allows population from ORM attributes."""

    model_config = ConfigDict(from_attributes=True)
    id: UUID


class VillageProfileRead(BaseModel):
    """The village's fixed identity data (hardcoded -- see
    ``app.models.master.VillageProfile``), no ``id``/``_Read`` since it's
    not a database row."""

    model_config = ConfigDict(from_attributes=True)

    name: str
    kecamatan: str
    kabupaten: str
    provinsi: str


class RWCreate(BaseModel):
    number: str


class RWUpdate(BaseModel):
    number: str | None = None


class RWRead(_Read):
    number: str


class RTCreate(BaseModel):
    rw_id: UUID
    number: str


class RTUpdate(BaseModel):
    number: str | None = None


class RTRead(_Read):
    rw_id: UUID
    number: str


