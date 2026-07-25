"""LAPDUK (Laporan Penduduk): monthly per-RT population report."""
import uuid

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, GUID, SoftDeleteMixin, TimestampMixin, UUIDMixin


class LapdukReport(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """One RT's population report for a given month (upsert per rt_id+period)."""

    __tablename__ = "lapduk_reports"
    __table_args__ = (
        UniqueConstraint("rt_id", "period", name="uq_lapduk_reports_rt_period"),
    )

    rt_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("rt.id"), index=True)
    period: Mapped[str] = mapped_column(String(7), index=True)  # "YYYY-MM"
    jumlah_kk: Mapped[int] = mapped_column(default=0)
    laki_laki: Mapped[int] = mapped_column(default=0)
    perempuan: Mapped[int] = mapped_column(default=0)
    pindah: Mapped[int] = mapped_column(default=0)
    datang: Mapped[int] = mapped_column(default=0)
    lahir: Mapped[int] = mapped_column(default=0)
    meninggal: Mapped[int] = mapped_column(default=0)
    submitted_by_user_id: Mapped[uuid.UUID] = mapped_column(GUID(), ForeignKey("users.id"))
