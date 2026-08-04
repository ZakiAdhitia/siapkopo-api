"""Portal Desa content models: news/articles, gallery, organization structure.

VillageProfile (the singleton village profile) already lives in
app/models/master.py (built in the multi-village-removal rework part) --
not duplicated here.
"""
from datetime import date

from sqlalchemy import Date, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDMixin


class NewsPost(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A public news item or article ("berita"/"artikel")."""

    __tablename__ = "news_posts"
    content_type: Mapped[str] = mapped_column(String(20), index=True)  # "berita" | "artikel"
    kategori: Mapped[str | None] = mapped_column(String(100), nullable=True)
    judul: Mapped[str] = mapped_column(String(255))
    tanggal: Mapped[date] = mapped_column(Date)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    icon: Mapped[str | None] = mapped_column(String(100), nullable=True)


class GalleryPhoto(UUIDMixin, TimestampMixin, SoftDeleteMixin, Base):
    """A single photo in the public village gallery."""

    __tablename__ = "gallery_photos"
    photo_path: Mapped[str] = mapped_column(String(500))
    caption: Mapped[str | None] = mapped_column(String(255), nullable=True)
    order_index: Mapped[int] = mapped_column(default=0)
