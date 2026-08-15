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
    """One staff attendance record for one calendar day."""

    __tablename__ = "attendance"

    user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"), index=True)
    attendance_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[AttendanceStatus] = mapped_column(
        SAEnum(AttendanceStatus, native_enum=False, length=10, values_callable=_values_callable),
        default=AttendanceStatus.HADIR,
    )
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    location_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    selfie_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
