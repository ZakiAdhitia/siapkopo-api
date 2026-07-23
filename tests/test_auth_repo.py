import pytest
from app.repositories.auth import UserRepository, RefreshTokenRepository


@pytest.mark.asyncio
async def test_get_by_username_none(db_session):
    repo = UserRepository(db_session)
    assert await repo.get_by_username("nobody") is None
