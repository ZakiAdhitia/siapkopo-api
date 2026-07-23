"""Master data services wrapping BaseRepository with common CRUD orchestration."""
import uuid
from typing import Any, ClassVar

from sqlalchemy import Column
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.core.logging import get_logger
from app.models.master import RT, RW, Dusun, FamilyCard, Resident, Village
from app.repositories.base import BaseRepository

logger = get_logger("master")


class _CrudService:
    """Common CRUD orchestration for a single master-data model.

    Subclasses set ``model`` (the SQLAlchemy model) and ``name`` (a
    human-readable label used in not-found messages). Subclasses that
    support free-text search also define ``search_columns``.
    """

    model: ClassVar[type]
    name: ClassVar[str] = "Resource"

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = BaseRepository(session, self.model)

    async def create(self, data: dict[str, Any]) -> Any:
        """Create and persist a new row from validated input data."""
        obj = await self.repo.create(**data)
        await self.session.commit()
        logger.info("%s created id=%s", self.name, obj.id)
        return obj

    async def get_or_404(self, id_: uuid.UUID) -> Any:
        """Return the row with the given id, or raise NotFoundError."""
        obj = await self.repo.get(id_)
        if obj is None:
            raise NotFoundError(f"{self.name} tidak ditemukan")
        return obj

    async def list(
        self,
        page: int = 1,
        size: int = 20,
        filters: dict[str, Any] | None = None,
        search: str | None = None,
    ) -> tuple[list[Any], int]:
        """Return a page of rows plus the total matching count."""
        search_arg: tuple[list[Column], str] | None = None
        if search and getattr(self, "search_columns", None):
            search_arg = (self.search_columns, search)
        return await self.repo.list(page=page, size=size, filters=filters, search=search_arg)

    async def update(self, id_: uuid.UUID, data: dict[str, Any]) -> Any:
        """Update the row with the given id and persist the change."""
        obj = await self.get_or_404(id_)
        obj = await self.repo.update(obj, **data)
        await self.session.commit()
        logger.info("%s updated id=%s", self.name, id_)
        return obj

    async def delete(self, id_: uuid.UUID) -> None:
        """Soft-delete the row with the given id."""
        obj = await self.get_or_404(id_)
        await self.repo.soft_delete(obj)
        await self.session.commit()
        logger.info("%s deleted id=%s", self.name, id_)


class VillageService(_CrudService):
    """CRUD service for Village."""

    model = Village
    name = "Village"


class DusunService(_CrudService):
    """CRUD service for Dusun."""

    model = Dusun
    name = "Dusun"


class RWService(_CrudService):
    """CRUD service for RW."""

    model = RW
    name = "RW"


class RTService(_CrudService):
    """CRUD service for RT."""

    model = RT
    name = "RT"


class FamilyCardService(_CrudService):
    """CRUD service for FamilyCard."""

    model = FamilyCard
    name = "Kartu Keluarga"


class ResidentService(_CrudService):
    """CRUD service for Resident, with search over NIK and full name."""

    model = Resident
    name = "Penduduk"

    @property
    def search_columns(self) -> list[Column]:
        return [Resident.nik, Resident.full_name]
