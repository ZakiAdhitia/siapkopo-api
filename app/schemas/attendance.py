"""Schemas for staff daily attendance ("Absen")."""
from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class AttendanceCheckInRequest(BaseModel):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class AttendanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID
    attendance_date: date
    status: str
    latitude: float | None = None
    longitude: float | None = None
    selfie_path: str | None = None
    created_at: datetime
    # Populated by the router (not the ORM object): who checked in, for the
    # admin "all attendance" list -- avoids a second lookup on the client.
    user_full_name: str | None = None


class AttendanceImportError(BaseModel):
    row: int
    message: str


class AttendanceImportResult(BaseModel):
    imported: int
    skipped: int = 0
    errors: list[AttendanceImportError] = []
