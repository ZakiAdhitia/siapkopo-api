"""Portal Desa admin CRUD endpoints: news/articles, gallery, organization."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page, build_page
from app.schemas.portal import (
    GalleryPhotoCreate, GalleryPhotoRead, GalleryPhotoUpdate,
    NewsPostCreate, NewsPostRead, NewsPostUpdate,
    OrgMemberCreate, OrgMemberRead, OrgMemberUpdate,
)
from app.services.portal import GalleryPhotoService, NewsPostService, OrgMemberService

router = APIRouter(tags=["portal-admin"])


# ---- News/Articles ----
@router.post("/portal/news", response_model=Envelope[NewsPostRead])
async def create_news_post(
    body: NewsPostCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Create a news post or article."""
    obj = await NewsPostService(session).create(body.model_dump(exclude_unset=True))
    return success_response(NewsPostRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/portal/news", response_model=Envelope[Page[NewsPostRead]])
async def list_news_posts(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """List news posts/articles, paginated."""
    items, total = await NewsPostService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, NewsPostRead))


@router.get("/portal/news/{item_id}", response_model=Envelope[NewsPostRead])
async def get_news_post(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Get a single news post/article by id."""
    obj = await NewsPostService(session).get_or_404(item_id)
    return success_response(NewsPostRead.model_validate(obj).model_dump(mode="json"))


@router.put("/portal/news/{item_id}", response_model=Envelope[NewsPostRead])
async def update_news_post(
    item_id: UUID,
    body: NewsPostUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Update a news post/article."""
    obj = await NewsPostService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(NewsPostRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/portal/news/{item_id}", response_model=Envelope[None])
async def delete_news_post(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Soft-delete a news post/article."""
    await NewsPostService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- Gallery ----
@router.post("/portal/gallery", response_model=Envelope[GalleryPhotoRead])
async def create_gallery_photo(
    body: GalleryPhotoCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Add a photo to the public gallery."""
    obj = await GalleryPhotoService(session).create(body.model_dump(exclude_unset=True))
    return success_response(GalleryPhotoRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/portal/gallery", response_model=Envelope[Page[GalleryPhotoRead]])
async def list_gallery_photos(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """List gallery photos, paginated."""
    items, total = await GalleryPhotoService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, GalleryPhotoRead))


@router.get("/portal/gallery/{item_id}", response_model=Envelope[GalleryPhotoRead])
async def get_gallery_photo(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Get a single gallery photo by id."""
    obj = await GalleryPhotoService(session).get_or_404(item_id)
    return success_response(GalleryPhotoRead.model_validate(obj).model_dump(mode="json"))


@router.put("/portal/gallery/{item_id}", response_model=Envelope[GalleryPhotoRead])
async def update_gallery_photo(
    item_id: UUID,
    body: GalleryPhotoUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Update a gallery photo."""
    obj = await GalleryPhotoService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(GalleryPhotoRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/portal/gallery/{item_id}", response_model=Envelope[None])
async def delete_gallery_photo(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Soft-delete a gallery photo."""
    await GalleryPhotoService(session).delete(item_id)
    return success_response(None, "Dihapus")


# ---- Organization structure ----
@router.post("/portal/organization", response_model=Envelope[OrgMemberRead])
async def create_org_member(
    body: OrgMemberCreate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Add a member to the public organization structure."""
    obj = await OrgMemberService(session).create(body.model_dump(exclude_unset=True))
    return success_response(OrgMemberRead.model_validate(obj).model_dump(mode="json"), "Tersimpan")


@router.get("/portal/organization", response_model=Envelope[Page[OrgMemberRead]])
async def list_org_members(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """List organization members, paginated."""
    items, total = await OrgMemberService(session).list(p.page, p.size)
    return success_response(build_page(items, total, p.page, p.size, OrgMemberRead))


@router.get("/portal/organization/{item_id}", response_model=Envelope[OrgMemberRead])
async def get_org_member(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Get a single organization member by id."""
    obj = await OrgMemberService(session).get_or_404(item_id)
    return success_response(OrgMemberRead.model_validate(obj).model_dump(mode="json"))


@router.put("/portal/organization/{item_id}", response_model=Envelope[OrgMemberRead])
async def update_org_member(
    item_id: UUID,
    body: OrgMemberUpdate,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Update an organization member."""
    obj = await OrgMemberService(session).update(item_id, body.model_dump(exclude_unset=True))
    return success_response(OrgMemberRead.model_validate(obj).model_dump(mode="json"), "Diperbarui")


@router.delete("/portal/organization/{item_id}", response_model=Envelope[None])
async def delete_org_member(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _=Depends(require_permission("portal:manage")),
) -> dict:
    """Soft-delete an organization member."""
    await OrgMemberService(session).delete(item_id)
    return success_response(None, "Dihapus")
