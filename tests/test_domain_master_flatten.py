from datetime import date

from app.services.domain_master import _flatten_extra_data


def test_flatten_domisili():
    flat = _flatten_extra_data("domisili", {"alamat_asal": "Kp. Lama", "rt_asal": "003"})
    assert flat["alamat_asal"] == "Kp. Lama"
    assert flat["rt_asal"] == "003"


def test_flatten_kematian():
    flat = _flatten_extra_data("kematian", {"jk": "Laki-laki", "alamat": "Kp. X"})
    assert flat["jk_almarhum"] == "Laki-laki"
    assert flat["alamat_almarhum"] == "Kp. X"


def test_flatten_na_handles_missing_nested_blocks():
    flat = _flatten_extra_data("na", {"calon": {"jk": "Perempuan"}})
    assert flat["jk_calon"] == "Perempuan"
    assert flat["tempat_lahir_ayah"] is None


def test_flatten_kelahiran():
    # The child's own attributes are citizen-input (`answers`) now, not
    # staff_extra_data -- only ayah/ibu still live in `extra`.
    flat = _flatten_extra_data(
        "kelahiran",
        {"ayah": {"pekerjaan": "Petani"}},
        {"jk_anak": "Laki-laki", "tanggal_lahir_anak": date(2026, 1, 1)},
    )
    assert flat["gender_anak"] == "Laki-laki"
    assert flat["tgl_lahir_anak"] == date(2026, 1, 1)
    assert flat["pekerjaan_ayah"] == "Petani"


def test_flatten_kelahiran_without_answers_defaults_to_none():
    flat = _flatten_extra_data("kelahiran", {"ayah": {"pekerjaan": "Petani"}})
    assert flat["gender_anak"] is None
    assert flat["pekerjaan_ayah"] == "Petani"


def test_flatten_pindah():
    flat = _flatten_extra_data("pindah", {"alamat_asal": "Kp. Asal", "rt_asal": "003", "rw_asal": "009"})
    assert flat == {"alamat_asal": "Kp. Asal", "rt_asal": "003", "rw_asal": "009"}


def test_flatten_kk():
    flat = _flatten_extra_data("kk", {"nama_kk": "Budi", "dusun": "Dusun 1"})
    assert flat == {"nama_kk": "Budi", "dusun": "Dusun 1"}


def test_flatten_unknown_jenis_returns_empty_dict():
    assert _flatten_extra_data("sku", {}) == {}
