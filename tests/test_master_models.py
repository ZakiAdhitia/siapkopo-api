"""Tests for master-data SQLAlchemy models."""
from app.models.master import RT, RW, Dusun, FamilyCard, Resident, VillageProfile


def test_master_tables():
    """Each master-data model maps to its expected table name."""
    assert VillageProfile.__tablename__ == "village_profile"
    assert Dusun.__tablename__ == "dusun"
    assert RW.__tablename__ == "rw"
    assert RT.__tablename__ == "rt"
    assert FamilyCard.__tablename__ == "family_cards"
    assert Resident.__tablename__ == "residents"
