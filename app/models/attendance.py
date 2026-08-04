"""Staff daily attendance ("Absen") model."""
import enum
import uuid
from datetime import date

from sqlalchemy import Date, Float, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class AttendanceStatus(str, enum.Enum):
    """Daily presence status -- mirrors the "I/S/A" codes on the paper
    "Daftar Hadir" roster (Izin/Sakit/Alfa), plus HADIR for present."""

    HADIR = "hadir"
    IZIN = "izin"
    SAKIT = "sakit"
    ALFA = "alfa"


def _values_callable(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist enum VALUES ("hadir"), not member NAMES ("HADIR")."""
    return [member.value for member in enum_cls]


class Attendance(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One staff attendance record for one calendar day.

    Two ways a row is created:
    - Live check-in (the "Absen" button): `attendance_date` is today,
      `status` is always HADIR, `latitude`/`longitude`/`selfie_path` are
      always populated (GPS + selfie proof).
    - Excel import (digitizing a paper "Daftar Hadir" roster, or backfilling
      a month the digital check-in wasn't used yet): `attendance_date` is
      whatever day column the cell came from, `status` reflects the I/S/A
      code (or HADIR for a plain signature mark), and there is no GPS/selfie
      to attach -- those three columns stay null for imported rows.

    `created_at` (TimestampMixin) is when the ROW was written, which for a
    live check-in coincides with `attendance_date` but for an import (or a
    correction) does not -- `attendance_date` is the one that means
    "which day is this attendance FOR".
    """

    __tablename__ = "attendance"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus, native_enum=False, length=10, values_callable=_values_callable),
        default=AttendanceStatus.HADIR,
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    selfie_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
