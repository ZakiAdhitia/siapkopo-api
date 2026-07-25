"""Schemas for LAPDUK (monthly per-RT population report)."""
import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

_PERIOD_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


class LapdukUpsert(BaseModel):
    """Create-or-update payload for a single RT+period report."""

    rt_id: UUID
    period: str = Field(min_length=7, max_length=7)
    jumlah_kk: int = Field(default=0, ge=0)
    laki_laki: int = Field(default=0, ge=0)
    perempuan: int = Field(default=0, ge=0)
    pindah: int = Field(default=0, ge=0)
    datang: int = Field(default=0, ge=0)
    lahir: int = Field(default=0, ge=0)
    meninggal: int = Field(default=0, ge=0)

    @field_validator("period")
    @classmethod
    def _check_period(cls, v: str) -> str:
        if not re.match(_PERIOD_PATTERN, v):
            raise ValueError("Format periode harus YYYY-MM")
        return v


class LapdukRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rt_id: UUID
    period: str
    jumlah_kk: int
    laki_laki: int
    perempuan: int
    pindah: int
    datang: int
    lahir: int
    meninggal: int
    submitted_by_user_id: UUID
    created_at: datetime
    updated_at: datetime


class LapdukImportError(BaseModel):
    row: int
    message: str


class LapdukImportResult(BaseModel):
    """Outcome of a LAPDUK Excel import: counts + per-row errors."""

    imported: int
    errors: list[LapdukImportError] = []
