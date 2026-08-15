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


def test_kk_header_fields_have_correct_effective_source():
    sesi = STAFF_SESI_SCHEMA_BY_JENIS["kk"]
    kk_header = next(s for s in sesi if s["key"] == "kk_header")
    by_key = {f["key"]: f for f in kk_header["fields"]}
    assert "source" not in by_key["no_kk"]
    assert "source" not in by_key["alamat"]
    assert "source" not in by_key["rt_id"]
    assert by_key["nama_kk"]["source"] == "extra"
    assert by_key["dusun"]["source"] == "extra"


def test_pindah_has_single_mixed_sesi():
    """2026-08-13 (susulan): dulu 2 sesi terpisah (Data Pemohon 1 field +
    Alamat Asal 3 field) digabung jadi 1 sesi "mixed", pola sama seperti
    KK's kk_header -- no_kk generic, alamat_asal/rt_asal/rw_asal extra."""
    sesi = STAFF_SESI_SCHEMA_BY_JENIS["pindah"]
    assert len(sesi) == 1
    assert sesi[0]["source"] == "mixed"
    by_key = {f["key"]: f for f in sesi[0]["fields"]}
    assert set(by_key) == {"no_kk", "alamat_asal", "rt_asal", "rw_asal"}
    assert "source" not in by_key["no_kk"]
    assert by_key["alamat_asal"]["source"] == "extra"
    assert by_key["rt_asal"]["source"] == "extra"
    assert by_key["rw_asal"]["source"] == "extra"
