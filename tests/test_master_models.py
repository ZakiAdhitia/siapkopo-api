"""Tests for master-data SQLAlchemy models."""
from app.models.master import RT, RW, VillageProfile


def test_master_tables():
    """Each master-data model maps to its expected table name."""
    assert RW.__tablename__ == "rw"
    assert RT.__tablename__ == "rt"


def test_village_profile_is_hardcoded_not_a_table():
    """VillageProfile is a plain dataclass now (no DB table) -- fixed
    single-desa identity, see its docstring."""
    assert not hasattr(VillageProfile, "__tablename__")
    assert VillageProfile().name == "Kopo"
