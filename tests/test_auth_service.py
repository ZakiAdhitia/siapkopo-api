import pytest
from app.services.auth import AuthService
from app.core.exceptions import UnauthorizedError


@pytest.mark.asyncio
async def test_login_password_success(seeded_session):
    svc = AuthService(seeded_session)
    pair = await svc.login_password("staf", "staf123")
    assert pair["access_token"]
    assert pair["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_password_wrong(seeded_session):
    svc = AuthService(seeded_session)
    with pytest.raises(UnauthorizedError):
        await svc.login_password("staf", "wrong")
