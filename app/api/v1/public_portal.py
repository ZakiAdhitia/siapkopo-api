"""Public, no-auth Portal Desa read endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.schemas.master import VillageProfileRead
from app.schemas.portal import GalleryPhotoRead, NewsPostRead, OrgMemberRead
from app.services.portal import PortalPublicService

router = APIRouter(prefix="/public/portal", tags=["public-portal"])


@router.get("/profile", response_model=Envelope[VillageProfileRead])
async def get_public_profile(session: AsyncSession = Depends(get_db)) -> dict:
    """Public village profile: name, contact info, kades sambutan, etc."""
    obj = await PortalPublicService(session).profile()
    return success_response(VillageProfileRead.model_validate(obj).model_dump(mode="json"))


@router.get("/news", response_model=Envelope[list[NewsPostRead]])
async def list_public_news(
    content_type: str | None = Query(None, pattern="^(berita|artikel)$"),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Public news/articles, newest first, optionally filtered by type."""
    items = await PortalPublicService(session).news(content_type)
    return success_response([NewsPostRead.model_validate(i).model_dump(mode="json") for i in items])


@router.get("/gallery", response_model=Envelope[list[GalleryPhotoRead]])
async def list_public_gallery(session: AsyncSession = Depends(get_db)) -> dict:
    """Public gallery photos, ordered by order_index."""
    items = await PortalPublicService(session).gallery()
    return success_response([GalleryPhotoRead.model_validate(i).model_dump(mode="json") for i in items])


@router.get("/organization", response_model=Envelope[list[OrgMemberRead]])
async def list_public_organization(session: AsyncSession = Depends(get_db)) -> dict:
    """Public organization structure, ordered by order_index."""
    items = await PortalPublicService(session).organization()
    return success_response([OrgMemberRead.model_validate(i).model_dump(mode="json") for i in items])
