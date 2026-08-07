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
    # kk=1 (06/08/2026 susulan: dropped jumlah_anggota_keluarga +
    # keterangan_perubahan, was 3), domisili=12, usaha=6, lahir=22, mati=14,
    # na=62 (NA restructure, 06/08/2026: added lokasi_akad (was 61); 8
    # N.6-detail pasangan_terdahulu fields were briefly dropped then
    # restored, gated to sebab_cerai=="Cerai Mati" only (Cerai Hidup still
    # just needs the name) per the final 06/08/2026 decision -- needed to
    # issue N.6), uhc=23 (SKTM), pindah=36 (F-1.03 restructure, 06/08/2026:
    # alamat_asal/rt_asal/rw_asal + status_kk_tujuan + 7 numbered
    # anggota_<n>_{nik,nama,shdk} slots replacing the old single free-text
    # daftar_anggota_pindah, was 12), ubah_data=4 (added 2026-08-03, F-1.06)
    # (180)
    assert field_count == 180

    kk = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "kk"))
    assert kk.numbering_prefix == "474"
    assert kk.required_documents == [
        "Kartu Keluarga (KK) Asli yang Lama",
        "Foto KTP-el Seluruh Anggota Keluarga yang Akan Terdaftar",
    ]
    assert kk.category_field_key == "status_perubahan"
    # Categories corrected 06/08/2026 (susulan) per HASIL_UJICOBA_PENGAJUAN_
    # PER_SURAT.md's "Kartu Keluarga" item 2: each category's attachments are
    # now self-contained/granular, and "KK Rusak atau Hilang" is split into
    # two distinct status_perubahan options ("KK Rusak"/"KK Hilang") since
    # ALUR_PENGISIAN_KK.md bagian C.4 requires different lampiran for each
    # (no second-level category field invented -- reuses the same
    # single-level category_field_key mechanism).
    assert set(kk.required_documents_by_category) == {
        "Baru Menikah (Pecah KK Mandiri)", "Ada Kelahiran Anak (Penambahan Anggota)",
        "Anggota Keluarga Meninggal Dunia (Pengurangan Anggota)",
        "KK Rusak", "KK Hilang",
        "Cerai Hidup (Pecah KK Mandiri Pasca Perceraian)",
    }
    assert kk.required_documents_by_category["KK Rusak"] == [
        "Foto Fisik Lembar KK Lama yang Rusak", "Foto KTP-el Kepala Keluarga (Asli)",
    ]
    assert kk.required_documents_by_category["KK Hilang"] == [
        "Foto Surat Keterangan Kehilangan dari Polsek Setempat",
        "Fotokopi KK Lama yang Hilang (jika ada)", "Foto KTP-el Kepala Keluarga",
    ]
    kk_fields = (await db_session.scalars(
        select(TemplateField).where(TemplateField.template_id == kk.id)
    )).all()
    assert {f.field_key for f in kk_fields} == {"status_perubahan"}

    uhc = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "uhc"))
    assert uhc.name == "Surat Keterangan Tidak Mampu (SKTM)"
    assert uhc.required_documents == ["Foto KK", "Foto KTP"]
    dtks_field = await db_session.scalar(
        select(TemplateField).where(
            TemplateField.template_id == uhc.id, TemplateField.field_key == "terdaftar_dtks"
        )
    )
    # 2026-08-05 TAMBAHAN item 6: no more is_staff_only fields anywhere --
    # warga self-reports it (optionally) at submission time instead of
    # staff completing it afterward.
    assert dtks_field.is_staff_only is False

    na = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "na"))
    assert {d["code"] for d in na.sub_documents} == {
        "na_n1", "na_n4", "na_n5", "na_menumpang", "na_belum_nikah", "na_n6",
    }

    ubah_data = await db_session.scalar(select(LetterTemplate).where(LetterTemplate.code == "ubah_data"))
    assert ubah_data.name == "Perubahan Elemen Data Kependudukan"
    assert ubah_data.category_field_key == "elemen_diubah"
    assert "Nama" in ubah_data.required_documents_by_category
    assert "Foto Akta Kelahiran (Asli)" in ubah_data.required_documents_by_category["Nama"]
