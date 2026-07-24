import pytest
from sqlalchemy import select

from app.core.exceptions import NotFoundError, ValidationAppError
from app.models.auth import Role, User
from app.services.letter_template import LetterTemplateService
from app.services.master import VillageService
from app.services.submission import SubmissionService


async def _make_template_with_fields(session, village_id):
    svc = LetterTemplateService(session)
    template = await svc.create({
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ alamat_tinggal_saat_ini }}</p>",
    })
    await svc.add_field(template.id, {
        "field_key": "alamat_tinggal_saat_ini", "label": "Alamat Tinggal Saat Ini",
        "field_type": "text", "is_required": True,
    })
    await svc.add_field(template.id, {
        "field_key": "keperluan", "label": "Keperluan", "field_type": "select",
        "options": ["Bank", "Sekolah"], "is_required": True,
    })
    return template


async def _make_warga_user(session, username: str) -> User:
    """Create a warga-role User for a test, using the seeded 'warga' Role row."""
    role = (await session.scalars(select(Role).where(Role.name == "warga"))).first()
    user = User(username=username, full_name="Warga Test", hashed_password="x", role_id=role.id)
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_create_validates_required_fields(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {"alamat_tinggal_saat_ini": ""})  # missing keperluan


@pytest.mark.asyncio
async def test_create_validates_select_options(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test2")

    svc = SubmissionService(seeded_session)
    with pytest.raises(ValidationAppError):
        await svc.create(user, template.id, {
            "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "NotAnOption",
        })


@pytest.mark.asyncio
async def test_create_succeeds_with_valid_answers(seeded_session):
    village = await VillageService(seeded_session).create({"name": "Desa Kopo"})
    template = await _make_template_with_fields(seeded_session, village.id)
    user = await _make_warga_user(seeded_session, "warga_test3")

    svc = SubmissionService(seeded_session)
    obj = await svc.create(user, template.id, {
        "alamat_tinggal_saat_ini": "Jl. A", "keperluan": "Bank",
    })
    assert obj.status.value == "pending"
    assert obj.current_step_index == 0

    got = await svc.get_or_404(obj.id)
    assert got.answers["keperluan"] == "Bank"
