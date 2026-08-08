from app.services.domain_master import STAFF_SESI_SCHEMA_BY_JENIS, TEMPLATE_CODE_TO_JENIS


def test_sesi_schema_covers_every_jenis():
    assert set(STAFF_SESI_SCHEMA_BY_JENIS) == set(TEMPLATE_CODE_TO_JENIS.values())


def test_kk_has_three_sesi_with_repeatable_anggota():
    sesi = STAFF_SESI_SCHEMA_BY_JENIS["kk"]
    keys = [s["key"] for s in sesi]
    assert keys == ["kk_header", "anggota", "orang_tua"]
    anggota_sesi = next(s for s in sesi if s["key"] == "anggota")
    assert anggota_sesi["repeatable"] is True
    assert anggota_sesi["max_items"] == 10
    assert {f["key"] for f in anggota_sesi["fields"]} == {
        "nik", "nama", "jk", "tempat_lahir", "tanggal_lahir", "agama",
        "pendidikan", "pekerjaan", "status_kawin", "shdk", "wni_wna",
    }


def test_na_has_four_sesi():
    sesi = STAFF_SESI_SCHEMA_BY_JENIS["na"]
    assert [s["key"] for s in sesi] == ["calon", "ayah", "ibu", "csi"]


def test_sku_has_single_generic_sesi():
    sesi = STAFF_SESI_SCHEMA_BY_JENIS["sku"]
    assert len(sesi) == 1
    assert sesi[0]["source"] == "generic"
