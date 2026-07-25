"""Portal Desa content services: admin CRUD (reusing _CrudService) + a
public read-only aggregator for the no-auth portal endpoints (Bagian 11)."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.master import VillageProfile
from app.models.portal import GalleryPhoto, NewsPost, OrgMember
from app.services.master import VillageProfileService, _CrudService


class NewsPostService(_CrudService):
    """CRUD service for NewsPost (berita/artikel)."""

    model = NewsPost
    name = "Berita/Artikel"


class GalleryPhotoService(_CrudService):
    """CRUD service for GalleryPhoto."""

    model = GalleryPhoto
    name = "Foto Galeri"


class OrgMemberService(_CrudService):
    """CRUD service for OrgMember."""

    model = OrgMember
    name = "Struktur Organisasi"


class PortalPublicService:
    """Read-only, no-auth aggregation for the public Portal Desa pages."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def profile(self) -> VillageProfile:
        return await VillageProfileService(self.session).get()

    async def news(self, content_type: str | None = None) -> list[NewsPost]:
        stmt = select(NewsPost).where(NewsPost.deleted_at.is_(None))
        if content_type:
            stmt = stmt.where(NewsPost.content_type == content_type)
        stmt = stmt.order_by(NewsPost.tanggal.desc())
        return list((await self.session.scalars(stmt)).all())

    async def gallery(self) -> list[GalleryPhoto]:
        stmt = (
            select(GalleryPhoto)
            .where(GalleryPhoto.deleted_at.is_(None))
            .order_by(GalleryPhoto.order_index.asc())
        )
        return list((await self.session.scalars(stmt)).all())

    async def organization(self) -> list[OrgMember]:
        stmt = (
            select(OrgMember)
            .where(OrgMember.deleted_at.is_(None))
            .order_by(OrgMember.order_index.asc())
        )
        return list((await self.session.scalars(stmt)).all())
