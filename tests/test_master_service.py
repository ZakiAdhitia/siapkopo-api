"""Tests for master-data CRUD services."""
import pytest

from app.core.exceptions import NotFoundError
from app.services.master import ResidentService


@pytest.mark.asyncio
async def test_resident_crud(db_session):
    """ResidentService supports create/get/update/search/delete end-to-end."""
    svc = ResidentService(db_session)
    r = await svc.create({"nik": "1", "full_name": "Budi"})
    assert r.full_name == "Budi"
    got = await svc.get_or_404(r.id)
    assert got.nik == "1"
    await svc.update(r.id, {"occupation": "Petani"})
    items, total = await svc.list(page=1, size=10, search="Budi")
    assert total == 1
    await svc.delete(r.id)
    with pytest.raises(NotFoundError):
        await svc.get_or_404(r.id)
