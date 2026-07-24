import pytest
from sqlalchemy import func, select

from app.models.letter_template import LetterTemplate, TemplateField
from app.seed.seed import seed_master, seed_letter_templates


@pytest.mark.asyncio
async def test_seed_letter_templates_idempotent(db_session):
    await seed_master(db_session)  # creates the village seed_letter_templates depends on
    await seed_letter_templates(db_session)
    await seed_letter_templates(db_session)

    template_count = await db_session.scalar(select(func.count()).select_from(LetterTemplate))
    assert template_count == 11

    field_count = await db_session.scalar(select(func.count()).select_from(TemplateField))
    assert field_count == 32  # kk,domisili,usaha,sktm,lahir,mati,pindah,datang=3 each (24);
    # ktp,kkpengantar=2 each (4); keramaian=4 → 24+4+4=32

    kk = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "kk"))
    assert kk.numbering_prefix == "474"
    assert kk.required_documents == ["KK lama", "KTP kepala keluarga"]
