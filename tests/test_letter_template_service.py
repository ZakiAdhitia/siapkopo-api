"""Tests for LetterTemplateService: template CRUD (Task 5), field CRUD + reorder (Task 6)."""
import pytest
from app.core.exceptions import NotFoundError
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService


@pytest.mark.asyncio
async def test_template_crud(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    svc = LetterTemplateService(db_session)
    obj = await svc.create({
        "village_id": village.id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    })
    assert obj.code == "domisili"

    got = await svc.get_or_404(obj.id)
    assert got.name == "Surat Domisili"

    await svc.update(obj.id, {"name": "Surat Domisili (Updated)"})
    items, total = await svc.list(search="Domisili")
    assert total == 1
    assert items[0].name == "Surat Domisili (Updated)"

    await svc.delete(obj.id)
    with pytest.raises(NotFoundError):
        await svc.get_or_404(obj.id)
