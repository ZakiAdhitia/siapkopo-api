from app.db.base import Base, UUIDMixin, TimestampMixin, SoftDeleteMixin


def test_mixins_present():
    assert hasattr(Base, "metadata")
    for mixin in (UUIDMixin, TimestampMixin, SoftDeleteMixin):
        assert mixin is not None
