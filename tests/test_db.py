import uuid
from datetime import datetime

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


def test_mixins_present():
    assert hasattr(Base, "metadata")
    for mixin in (UUIDMixin, TimestampMixin, SoftDeleteMixin):
        assert mixin is not None


class _Widget(Base, UUIDMixin, TimestampMixin, SoftDeleteMixin):
    """Throwaway model used only to exercise the mixins end-to-end."""

    __tablename__ = "test_widgets"

    name: Mapped[str] = mapped_column(default="widget")


@pytest.mark.asyncio
async def test_guid_and_mixins_roundtrip():
    """Insert a row via the GUID/Timestamp/SoftDelete mixins and read it back."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        original_id = uuid.uuid4()
        async with session_factory() as session:
            widget = _Widget(id=original_id, name="chair")
            session.add(widget)
            await session.commit()
            # The in-memory object is not expired (expire_on_commit=False), so
            # this still reflects the tz-aware value produced by the
            # TimestampMixin's Python-side `default=` callable at flush time.
            assert widget.created_at.tzinfo is not None
            assert widget.updated_at.tzinfo is not None

        # Read back from a fresh session to exercise the GUID TypeDecorator's
        # process_bind_param/process_result_value round trip end to end.
        async with session_factory() as session:
            result = await session.execute(select(_Widget).where(_Widget.id == original_id))
            row = result.scalar_one()

        assert isinstance(row.id, uuid.UUID)
        assert row.id == original_id
        assert isinstance(row.created_at, datetime)
        assert isinstance(row.updated_at, datetime)
        assert row.deleted_at is None
    finally:
        await engine.dispose()
