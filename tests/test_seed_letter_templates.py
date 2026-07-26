import pytest
from sqlalchemy import func, select

from app.models.letter_template import LetterTemplate, TemplateField
from app.seed.seed import seed_letter_templates


@pytest.mark.asyncio
async def test_seed_letter_templates_idempotent(db_session):
    await seed_letter_templates(db_session)
    await seed_letter_templates(db_session)

    template_count = await db_session.scalar(select(func.count()).select_from(LetterTemplate))
    assert template_count == 8

    field_count = await db_session.scalar(select(func.count()).select_from(TemplateField))
    assert field_count == 24  # kk,domisili,usaha,sktm,lahir,mati,pindah,datang=3 each (24)

    kk = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "kk"))
    assert kk.numbering_prefix == "474"
    assert kk.required_documents == ["Formulir Permohonan KK", "Kartu Keluarga Lama"]
    assert kk.category_field_key == "status_perubahan"
    assert set(kk.required_documents_by_category) == {
        "KK Baru", "Penambahan Anggota (Kelahiran)", "Penambahan Anggota (Menumpang)",
        "Pengurangan Anggota", "KK Hilang/Rusak",
    }
