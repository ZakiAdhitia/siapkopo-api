import pytest
from pydantic import ValidationError

from app.schemas.staff_extra_data import (
    STAFF_EXTRA_DATA_SCHEMA_BY_JENIS, DomisiliExtraData, KKExtraData, NAExtraData,
)


def test_schema_registry_covers_all_nine_jenis():
    assert set(STAFF_EXTRA_DATA_SCHEMA_BY_JENIS) == {
        "domisili", "kelahiran", "kematian", "sku", "na", "uhc", "pindah", "kk", "ubah_data",
    }


def test_jenis_without_extra_sesi_map_to_none():
    assert STAFF_EXTRA_DATA_SCHEMA_BY_JENIS["sku"] is None
    assert STAFF_EXTRA_DATA_SCHEMA_BY_JENIS["uhc"] is None
    assert STAFF_EXTRA_DATA_SCHEMA_BY_JENIS["pindah"] is None
    assert STAFF_EXTRA_DATA_SCHEMA_BY_JENIS["ubah_data"] is None


def test_domisili_extra_data_defaults_all_none():
    data = DomisiliExtraData()
    assert data.alamat_asal is None
    assert data.masa_berlaku_bulan is None


def test_na_extra_data_nested_blocks():
    data = NAExtraData.model_validate({"ayah": {"pekerjaan": "Petani", "rt": "003"}})
    assert data.ayah.pekerjaan == "Petani"
    assert data.calon.jk is None


def test_kk_extra_data_rejects_more_than_10_anggota():
    payload = {"anggota": [{"nama": f"Anggota {i}"} for i in range(11)]}
    with pytest.raises(ValidationError):
        KKExtraData.model_validate(payload)
