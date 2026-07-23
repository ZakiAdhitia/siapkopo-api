"""Generic repository with soft-delete-aware CRUD and pagination."""
import uuid
from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from sqlalchemy import Column, Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Reusable async CRUD scoped to non-soft-deleted rows.

    Intended to be composed by feature-specific services; it holds no
    business logic, only data access for a single SQLAlchemy model.
    """

    def __init__(self, session: AsyncSession, model: type[ModelT]) -> None:
        self.session = session
        self.model = model

    def _base_stmt(self) -> Select:
        """Return a SELECT for the model, excluding soft-deleted rows."""
        return select(self.model).where(self.model.deleted_at.is_(None))

    async def get(self, id_: uuid.UUID) -> ModelT | None:
        """Return the non-deleted row with the given id, or None."""
        stmt = self._base_stmt().where(self.model.id == id_)
        return await self.session.scalar(stmt)

    async def list(
        self,
        page: int = 1,
        size: int = 20,
        filters: dict[str, Any] | None = None,
        search: tuple[list[Column], str] | None = None,
    ) -> tuple[list[ModelT], int]:
        """Return a page of non-deleted rows plus the total matching count.

        ``filters`` is an exact-match column=value mapping. ``search`` is a
        ``(columns, term)`` pair applied as a case-insensitive OR across the
        given columns.
        """
        stmt = self._base_stmt()
        if filters:
            for field, value in filters.items():
                if value is not None:
                    stmt = stmt.where(getattr(self.model, field) == value)
        if search:
            columns, term = search
            if term:
                stmt = stmt.where(or_(*[c.ilike(f"%{term}%") for c in columns]))
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        stmt = stmt.order_by(self.model.created_at.desc()).offset((page - 1) * size).limit(size)
        rows = list((await self.session.scalars(stmt)).all())
        return rows, int(total or 0)

    async def create(self, **data: Any) -> ModelT:
        """Instantiate and flush a new row."""
        obj = self.model(**data)
        self.session.add(obj)
        await self.session.flush()
        return obj

    async def update(self, obj: ModelT, **data: Any) -> ModelT:
        """Apply non-None field updates to an existing row and flush."""
        for k, v in data.items():
            if v is not None:
                setattr(obj, k, v)
        await self.session.flush()
        return obj

    async def soft_delete(self, obj: ModelT) -> None:
        """Mark a row as deleted by stamping ``deleted_at``."""
        obj.deleted_at = datetime.now(timezone.utc)
        await self.session.flush()
