"""Admin-driven user & position management endpoints (Bagian 8)."""
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.response import Envelope, success_response
from app.db.session import get_db
from app.dependencies.auth import CurrentUser, require_permission
from app.dependencies.pagination import PaginationParams, pagination_params
from app.models.auth import Position, User
from app.repositories.auth import UserRepository
from app.schemas.common import Page
from app.schemas.user_management import PositionRead, UserCreate, UserRead, UserUpdate
from app.services.user_management import UserManagementService

router = APIRouter(tags=["users"])


@router.get("/positions", response_model=Envelope[list[PositionRead]])
async def list_positions(
    session: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """List the fixed Position catalog, ordered by hierarchy level."""
    positions = (
        await session.scalars(select(Position).order_by(Position.level))
    ).all()
    return success_response(
        [PositionRead.model_validate(p).model_dump(mode="json") for p in positions]
    )


def _user_read(user: User) -> dict:
    """Build a UserRead-shaped dict, deriving role/position display fields
    from the already-loaded (lazy="selectin") relationships."""
    return UserRead(
        id=user.id, username=user.username, nik=user.nik, full_name=user.full_name,
        email=user.email, phone=user.phone, is_active=user.is_active,
        pending_approval=user.pending_approval, role_id=user.role_id,
        role_name=user.role.name, position_id=user.position_id,
        position_name=user.position.display_name if user.position else None,
        position_level=user.position.level if user.position else None,
        resident_id=user.resident_id, rt_id=user.rt_id, rw_id=user.rw_id,
        created_at=user.created_at,
    ).model_dump(mode="json")


async def _load_actor(session: AsyncSession, current: CurrentUser) -> User:
    """Resolve the full User ORM row (with .role/.position loaded) for the
    authenticated principal -- CurrentUser only carries id/role/permissions."""
    actor = await UserRepository(session).get_by_id(UUID(current.id))
    return actor


@router.post("/users", response_model=Envelope[UserRead])
async def create_user(
    body: UserCreate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Create a user account, assigning any Position (admin-only path)."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).create(
        actor, current.permissions, body.model_dump(exclude_unset=True)
    )
    return success_response(_user_read(obj), "Tersimpan")


@router.get("/users", response_model=Envelope[Page[UserRead]])
async def list_users(
    session: AsyncSession = Depends(get_db),
    p: PaginationParams = Depends(pagination_params),
    position_id: UUID | None = Query(None),
    search: str | None = Query(None),
    include_warga: bool = Query(False),
    _: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """List users, paginated, filtered by position/search, warga hidden by default."""
    items, total = await UserManagementService(session).list(
        p.page, p.size, position_id, search, include_warga
    )
    return success_response({
        "items": [_user_read(u) for u in items], "total": total, "page": p.page, "size": p.size,
    })


@router.get("/users/{item_id}", response_model=Envelope[UserRead])
async def get_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    _: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Get a single user by id."""
    obj = await UserManagementService(session).get_or_404(item_id)
    return success_response(_user_read(obj))


@router.put("/users/{item_id}", response_model=Envelope[UserRead])
async def update_user(
    item_id: UUID,
    body: UserUpdate,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Update a user, gated by the position-hierarchy rule."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).update(
        actor, current.permissions, item_id, body.model_dump(exclude_unset=True)
    )
    return success_response(_user_read(obj), "Diperbarui")


@router.delete("/users/{item_id}", response_model=Envelope[None])
async def delete_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Soft-delete a user, gated by the position-hierarchy rule."""
    actor = await _load_actor(session, current)
    await UserManagementService(session).delete(actor, current.permissions, item_id)
    return success_response(None, "Dihapus")


@router.post("/users/{item_id}/approve", response_model=Envelope[UserRead])
async def approve_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Approve a pending self-registration (staff/rt/rw)."""
    actor = await _load_actor(session, current)
    obj = await UserManagementService(session).approve(actor, current.permissions, item_id)
    return success_response(_user_read(obj), "Registrasi disetujui")


@router.post("/users/{item_id}/reject", response_model=Envelope[None])
async def reject_user(
    item_id: UUID,
    session: AsyncSession = Depends(get_db),
    current: CurrentUser = Depends(require_permission("user:manage")),
) -> dict:
    """Reject a pending self-registration (staff/rt/rw) -- soft-deletes it."""
    actor = await _load_actor(session, current)
    await UserManagementService(session).reject(actor, current.permissions, item_id)
    return success_response(None, "Registrasi ditolak")
