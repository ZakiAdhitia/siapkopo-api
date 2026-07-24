"""Tests for LetterTemplateService: template CRUD (Task 5), field CRUD + reorder (Task 6)."""
import pytest
from app.core.exceptions import NotFoundError, ValidationAppError
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


@pytest.mark.asyncio
async def test_field_crud_and_reorder(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    svc = LetterTemplateService(db_session)
    template = await svc.create({
        "village_id": village.id, "code": "sktm", "name": "SKTM",
        "icon": "volunteer_activism", "color_bg": "#F3EAFB", "color_fg": "#7B4BC0",
        "numbering_prefix": "460", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ keperluan }}</p>",
    })

    f1 = await svc.add_field(template.id, {
        "field_key": "keperluan", "label": "Keperluan", "field_type": "select",
        "options": ["Beasiswa", "Kesehatan"], "is_required": True,
    })
    f2 = await svc.add_field(template.id, {
        "field_key": "penghasilan", "label": "Penghasilan", "field_type": "text",
        "is_required": True,
    })
    assert f1.order_index == 0
    assert f2.order_index == 1

    fields = await svc.list_fields(template.id)
    assert [f.id for f in fields] == [f1.id, f2.id]

    await svc.update_field(template.id, f2.id, {"label": "Penghasilan / Bulan"})
    updated = await svc.get_field_or_404(template.id, f2.id)
    assert updated.label == "Penghasilan / Bulan"

    reordered = await svc.reorder_fields(template.id, [f2.id, f1.id])
    assert [f.id for f in reordered] == [f2.id, f1.id]
    assert reordered[0].order_index == 0
    assert reordered[1].order_index == 1

    with pytest.raises(ValidationAppError):
        await svc.reorder_fields(template.id, [f1.id])  # missing f2.id

    await svc.delete_field(template.id, f1.id)
    remaining = await svc.list_fields(template.id)
    assert [f.id for f in remaining] == [f2.id]
