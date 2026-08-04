import pytest
from sqlalchemy import func, select

from app.models.letter_template import LetterTemplate, TemplateField
from app.seed.seed import seed_letter_templates


@pytest.mark.asyncio
async def test_seed_letter_templates_idempotent(db_session):
    await seed_letter_templates(db_session)
    await seed_letter_templates(db_session)

    template_count = await db_session.scalar(select(func.count()).select_from(LetterTemplate))
    assert template_count == 9

    field_count = await db_session.scalar(select(func.count()).select_from(TemplateField))
    # kk=3, domisili=12, usaha=6, lahir=22, mati=14, na=61 (52 + 9 N.6/sebab_cerai
    # fields, 2026-08-03), uhc=23 (SKTM), pindah=12, ubah_data=4 (added 2026-08-03,
    # F-1.06) (157)
    assert field_count == 157

    kk = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "kk"))
    assert kk.numbering_prefix == "474"
    assert kk.required_documents == [
        "Kartu Keluarga (KK) Asli yang Lama",
        "Foto KTP-el Seluruh Anggota Keluarga yang Akan Terdaftar",
    ]
    assert kk.category_field_key == "status_perubahan"
    # Categories corrected 2026-08-03 to match ALUR_PENGISIAN_KK.md's 5
    # conditions ("Pindah Rumah dari Daerah Lain" and "Perubahan Data
    # Biodata" are gone -- the latter is now the standalone "ubah_data"
    # letter type below).
    assert set(kk.required_documents_by_category) == {
        "Baru Menikah (Pecah KK Mandiri)", "Ada Kelahiran Anak (Penambahan Anggota)",
        "Anggota Keluarga Meninggal Dunia (Pengurangan Anggota)",
        "KK Rusak atau Hilang",
        "Cerai Hidup (Pecah KK Mandiri Pasca Perceraian)",
    }

    uhc = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "uhc"))
    assert uhc.name == "Surat Keterangan Tidak Mampu (SKTM)"
    assert uhc.required_documents == ["Foto KK", "Foto KTP"]
    dtks_field = await db_session.scalar(
        select(TemplateField).where(
            TemplateField.template_id == uhc.id, TemplateField.field_key == "terdaftar_dtks"
        )
    )
    assert dtks_field.is_staff_only is True

    na = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "na"))
    assert {d["code"] for d in na.sub_documents} == {
        "na_n1", "na_n4", "na_n5", "na_menumpang", "na_belum_nikah", "na_n6",
    }

    ubah_data = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "ubah_data"))
    assert ubah_data.name == "Perubahan Elemen Data Kependudukan"
    assert ubah_data.category_field_key == "elemen_diubah"
    assert "Nama" in ubah_data.required_documents_by_category
    assert "Foto Akta Kelahiran (Asli)" in ubah_data.required_documents_by_category["Nama"]
