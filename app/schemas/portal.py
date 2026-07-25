"""Schemas for Portal Desa content: news/articles, gallery, organization."""
from datetime import date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _Read(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID


class NewsPostCreate(BaseModel):
    content_type: Literal["berita", "artikel"]
    kategori: str | None = None
    judul: str = Field(min_length=1, max_length=255)
    tanggal: date
    excerpt: str | None = None
    photo_path: str | None = None
    icon: str | None = None


class NewsPostUpdate(BaseModel):
    content_type: Literal["berita", "artikel"] | None = None
    kategori: str | None = None
    judul: str | None = None
    tanggal: date | None = None
    excerpt: str | None = None
    photo_path: str | None = None
    icon: str | None = None


class NewsPostRead(_Read):
    content_type: str
    kategori: str | None = None
    judul: str
    tanggal: date
    excerpt: str | None = None
    photo_path: str | None = None
    icon: str | None = None


class GalleryPhotoCreate(BaseModel):
    photo_path: str = Field(min_length=1)
    caption: str | None = None
    order_index: int = 0


class GalleryPhotoUpdate(BaseModel):
    photo_path: str | None = None
    caption: str | None = None
    order_index: int | None = None


class GalleryPhotoRead(_Read):
    photo_path: str
    caption: str | None = None
    order_index: int


class OrgMemberCreate(BaseModel):
    jabatan: str = Field(min_length=1, max_length=150)
    nama: str = Field(min_length=1, max_length=150)
    order_index: int = 0
    photo_path: str | None = None


class OrgMemberUpdate(BaseModel):
    jabatan: str | None = None
    nama: str | None = None
    order_index: int | None = None
    photo_path: str | None = None


class OrgMemberRead(_Read):
    jabatan: str
    nama: str
    order_index: int
    photo_path: str | None = None
