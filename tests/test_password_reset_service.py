import pytest

from app.services.password_reset import PasswordResetService


@pytest.mark.asyncio
async def test_request_reset_then_verify_succeeds(_fake_redis):
    from app.models.auth import User
    user = User(id="11111111-1111-1111-1111-111111111111", full_name="Test User")
    svc = PasswordResetService()
    code = await svc.request_reset(user)
    assert len(code) == svc.settings.password_reset_code_length
    assert await svc.verify_and_consume(user.id, code) is True


@pytest.mark.asyncio
async def test_verify_wrong_code_fails(_fake_redis):
    from app.models.auth import User
    user = User(id="22222222-2222-2222-2222-222222222222", full_name="Test User")
    svc = PasswordResetService()
    await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, "000000") is False


@pytest.mark.asyncio
async def test_verify_consumes_code(_fake_redis):
    """A code can only be used once."""
    from app.models.auth import User
    user = User(id="33333333-3333-3333-3333-333333333333", full_name="Test User")
    svc = PasswordResetService()
    code = await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, code) is True
    assert await svc.verify_and_consume(user.id, code) is False
