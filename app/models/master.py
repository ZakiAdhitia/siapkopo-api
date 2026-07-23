"""Master data models: village hierarchy, family cards, residents."""
import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class Village(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A single administered village (tenant root for future multi-village support)."""

    __tablename__ = "villages"
    name: Mapped[str] = mapped_column(String(150), index=True)
    slogan: Mapped[str | None] = mapped_column(String(255), nullable=True)
    kecamatan: Mapped[str | None] = mapped_column(String(100), nullable=True)
    kabupaten: Mapped[str | None] = mapped_column(String(100), nullable=True)
    provinsi: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Dusun(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A hamlet (dusun) belonging to a village."""

    __tablename__ = "dusun"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    name: Mapped[str] = mapped_column(String(100), index=True)


class RW(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A neighborhood association (rukun warga) belonging to a dusun."""

    __tablename__ = "rw"
    dusun_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("dusun.id"), index=True)
    number: Mapped[str] = mapped_column(String(10))


class RT(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A neighborhood unit (rukun tetangga) belonging to an RW."""

    __tablename__ = "rt"
    rw_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("rw.id"), index=True)
    number: Mapped[str] = mapped_column(String(10))


class FamilyCard(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A family card (kartu keluarga) grouping residents under one household."""

    __tablename__ = "family_cards"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    kk_number: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Plain column (no FK) to avoid a circular dependency with residents.id.
    head_resident_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), nullable=True)


class Resident(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A citizen record identified by NIK, optionally linked to a family card and RT."""

    __tablename__ = "residents"
    village_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("villages.id"), index=True)
    nik: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(150), index=True)
    family_card_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(), ForeignKey("family_cards.id"), nullable=True, index=True
    )
    rt_id: Mapped[uuid.UUID | None] = mapped_column(GUID(), ForeignKey("rt.id"), nullable=True)
    gender: Mapped[str | None] = mapped_column(String(1), nullable=True)  # L/P
    birth_place: Mapped[str | None] = mapped_column(String(100), nullable=True)
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    occupation: Mapped[str | None] = mapped_column(String(100), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
