"""In-app notification endpoints: list own, mark read, mark all read."""
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.schemas.common import Page
from app.schemas.notification import NotificationRead
from app.services.notification import NotificationService

router = APIRouter(tags=["notifications"])


@router.get("/notifications", response_model=Envelope[Page[NotificationRead]])
async def list_notifications(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    current: CurrentUser = Depends(require_permission("notification:read")),
) -> dict:
    """List the caller's own notifications, newest first."""
    items, total = await NotificationService(session).list(UUID(current.id), p.page, p.size)
    return success_response({
        "items": [NotificationRead.model_validate(i).model_dump(mode="json") for i in items],
        "total": total, "page": p.page, "size": p.size,
    })


@router.post("/notifications/{item_id}/read", response_model=Envelope[NotificationRead])
async def mark_notification_read(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("notification:read")),
) -> dict:
    """Mark one of the caller's own notifications as read."""
    obj = await NotificationService(session).mark_read(UUID(current.id), item_id)
    return success_response(NotificationRead.model_validate(obj).model_dump(mode="json"), "Ditandai dibaca")


@router.post("/notifications/read-all", response_model=Envelope[None])
async def mark_all_notifications_read(
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("notification:read")),
) -> dict:
    """Mark all of the caller's unread notifications as read."""
    count = await NotificationService(session).mark_all_read(UUID(current.id))
    return success_response(None, f"{count} notifikasi ditandai dibaca")
