"""User & Position management: admin-driven CRUD over accounts, with
position-authority hierarchy enforcement (rework Part 5, spec Bagian 8)."""
# NOTE: required so annotations below are evaluated lazily (as strings)
# instead of eagerly against the enclosing class namespace. Without this,
# `list[str]`/`dict[str, Any]` annotations on methods defined AFTER this
# class's own `list()` method would resolve `list` to that method (a
# function object, not the builtin type) -- class-body statements execute
# sequentially and later ones see earlier class-level bindings -- raising
# `TypeError: 'function' object is not subscriptable` at class-definition
# time. Confirmed via a standalone repro before adding this.
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError, ValidationAppError
from app.core.logging import get_logger
from app.core.security import hash_password
from app.models.auth import Position, Role, User
from app.models.master import RT, RW
from app.repositories.base import BaseRepository
from app.services.notification import LoggingNotificationProvider

logger = get_logger("user_management")

# Position slug -> Role name assigned when a position is set through admin
# user-management. A fixed reference-data mapping (same pattern as
# AuthService._POSITION_CHOICE_MAP), not a runtime hardcoded branch --
# CLAUDE.md's "no hardcoded role/position checks" rule targets `if role ==
# "..."` authorization branches, not a static lookup table like this.
POSITION_ROLE_MAP: dict[str, str] = {
    "kepala_desa": "admin",
    "sekretaris_desa": "admin",
    "bendahara_desa": "staff",
    "staff_desa": "staff",
    "rw": "warga",
    "rt": "warga",
    "warga_desa": "warga",
}


class UserManagementService:
    """CRUD over User accounts with position-level hierarchy enforcement."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, User)

    async def _authorize_against_level(
        self, actor: User, actor_permissions: list[str], target_level: int
    ) -> None:
        """Enforce: actor may only act on a target whose position `level` is
        STRICTLY GREATER (lower authority) than the actor's own.

        `"*"` (administrator-it) bypasses this entirely. A target/actor with
        no position (`position is None`) is treated as level 0 -- the
        highest possible authority -- so only an unrestricted actor can
        manage a position-less account, and a position-less actor can never
        pass this check for anyone.
        """
        if "*" in actor_permissions:
            return
        if actor.position is None:
            raise ForbiddenError("Akun Anda tidak memiliki jabatan, tidak dapat mengelola user")
        if actor.position.level >= target_level:
            raise ForbiddenError("Anda tidak berwenang mengelola user dengan jabatan ini")

    async def _resolve_position(self, position_id: uuid.UUID) -> Position:
        position = await self.session.get(Position, position_id)
        if position is None:
            raise ValidationAppError("Posisi tidak ditemukan")
        return position

    async def _resolve_role_for_position(self, position: Position) -> Role:
        role_name = POSITION_ROLE_MAP[position.slug]
        role = await self.session.scalar(select(Role).where(Role.name == role_name))
        if role is None:
            raise ValidationAppError(f"Role '{role_name}' belum di-seed")
        return role

    async def get_or_404(self, id_: uuid.UUID) -> User:
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError("User tidak ditemukan")
        return obj

    async def list(
        self, page: int, size: int, position_id: uuid.UUID | None,
        search: str | None, include_warga: bool,
    ) -> tuple[list[User], int]:
        """List users, sorted by position level then name, paginated.

        No hierarchy filtering here -- any actor with `user:manage` may see
        the full roster; the hierarchy rule only gates mutation (create/
        update/delete/approve/reject).
        """
        stmt = (
            select(User)
            .where(User.deleted_at.is_(None))
            .outerjoin(Position, User.position_id == Position.id)
        )
        if position_id is not None:
            stmt = stmt.where(User.position_id == position_id)
        if not include_warga:
            stmt = stmt.where(or_(Position.slug.is_(None), Position.slug != "warga_desa"))
        if search:
            term = f"%{search}%"
            stmt = stmt.where(
                or_(User.full_name.ilike(term), User.username.ilike(term), User.nik.ilike(term))
            )
        total = await self.session.scalar(select(func.count()).select_from(stmt.subquery()))
        stmt = (
            stmt.order_by(Position.level.asc(), User.full_name.asc())
            .offset((page - 1) * size)
            .limit(size)
        )
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def create(
        self, actor: User, actor_permissions: list[str], data: dict[str, Any]
    ) -> User:
        position = await self._resolve_position(data["position_id"])
        await self._authorize_against_level(actor, actor_permissions, position.level)

        username = data["username"].strip().lower()
        if await self.session.scalar(
            select(User).where(User.username == username, User.deleted_at.is_(None))
        ):
            raise ConflictError("Username sudah digunakan")
        if await self.session.scalar(
            select(User).where(User.email == data["email"], User.deleted_at.is_(None))
        ):
            raise ConflictError("Email sudah digunakan")

        rt_id, rw_id = None, None
        if position.slug == "rt":
            if not data.get("rt_id"):
                raise ValidationAppError("rt_id wajib diisi untuk posisi RT")
            rt = await self.session.get(RT, data["rt_id"])
            if rt is None:
                raise ValidationAppError("RT tidak ditemukan")
            rt_id = rt.id
        elif position.slug == "rw":
            if not data.get("rw_id"):
                raise ValidationAppError("rw_id wajib diisi untuk posisi RW")
            rw = await self.session.get(RW, data["rw_id"])
            if rw is None:
                raise ValidationAppError("RW tidak ditemukan")
            rw_id = rw.id

        role = await self._resolve_role_for_position(position)
        user = User(
            username=username, nik=data.get("nik"), full_name=data["full_name"],
            hashed_password=hash_password(data["password"]), email=data["email"],
            phone=data.get("phone"), role_id=role.id, position_id=position.id,
            resident_id=data.get("resident_id"), rt_id=rt_id, rw_id=rw_id,
            is_active=True, pending_approval=False,
        )
        # See AuthService.register's identical comment: a freshly constructed
        # instance has unloaded lazy="selectin" relationships, so assign the
        # already-fetched ORM objects directly to avoid a MissingGreenlet on
        # the first synchronous `.role`/`.position` access after this returns.
        user.role = role
        user.position = position
        self.session.add(user)
        await self.session.commit()
        logger.info(
            "User created by admin actor_id=%s new_user_id=%s position=%s",
            actor.id, user.id, position.slug,
        )
        return user

    async def update(
        self, actor: User, actor_permissions: list[str],
        target_id: uuid.UUID, data: dict[str, Any],
    ) -> User:
        target = await self.get_or_404(target_id)
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)

        if "email" in data and data["email"] is not None:
            existing = await self.session.scalar(
                select(User).where(
                    User.email == data["email"], User.id != target.id,
                    User.deleted_at.is_(None),
                )
            )
            if existing:
                raise ConflictError("Email sudah digunakan")
            target.email = data["email"]
        if data.get("full_name") is not None:
            target.full_name = data["full_name"]
        if data.get("phone") is not None:
            target.phone = data["phone"]
        if data.get("password"):
            target.hashed_password = hash_password(data["password"])
        if data.get("is_active") is not None:
            target.is_active = data["is_active"]

        if data.get("position_id") is not None:
            new_position = await self._resolve_position(data["position_id"])
            await self._authorize_against_level(actor, actor_permissions, new_position.level)
            new_role = await self._resolve_role_for_position(new_position)
            target.position = new_position
            target.position_id = new_position.id
            target.role = new_role
            target.role_id = new_role.id

        if "rt_id" in data:
            target.rt_id = data["rt_id"]
        if "rw_id" in data:
            target.rw_id = data["rw_id"]

        await self.session.commit()
        logger.info("User updated by admin actor_id=%s target_id=%s", actor.id, target.id)
        return target

    async def delete(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> None:
        target = await self.get_or_404(target_id)
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("User soft-deleted by admin actor_id=%s target_id=%s", actor.id, target.id)

    async def approve(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> User:
        target = await self.get_or_404(target_id)
        if not target.pending_approval:
            raise ValidationAppError("User ini tidak sedang menunggu approval")
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.is_active = True
        target.pending_approval = False
        await self.session.commit()
        logger.info("Registration approved by actor_id=%s target_id=%s", actor.id, target.id)
        if target.email:
            LoggingNotificationProvider().send_email(
                target.email, "Registrasi Disetujui",
                "Akun Anda telah disetujui dan sekarang dapat digunakan untuk login.",
            )
        return target

    async def reject(
        self, actor: User, actor_permissions: list[str], target_id: uuid.UUID
    ) -> None:
        target = await self.get_or_404(target_id)
        if not target.pending_approval:
            raise ValidationAppError("User ini tidak sedang menunggu approval")
        current_level = target.position.level if target.position else 0
        await self._authorize_against_level(actor, actor_permissions, current_level)
        target.deleted_at = datetime.now(timezone.utc)
        await self.session.commit()
        logger.info("Registration rejected by actor_id=%s target_id=%s", actor.id, target.id)
        if target.email:
            LoggingNotificationProvider().send_email(
                target.email, "Registrasi Ditolak",
                "Registrasi akun Anda tidak dapat disetujui. Hubungi kantor desa untuk informasi lebih lanjut.",
            )
