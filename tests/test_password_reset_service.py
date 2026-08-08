import pytest

from app.models.auth import User
from app.services.password_reset import PasswordResetService


@pytest.mark.asyncio
async def test_request_reset_then_verify_succeeds(db_session):
    user = User(id="11111111-1111-1111-1111-111111111111", full_name="Test User")
    svc = PasswordResetService(db_session)
    code = await svc.request_reset(user)
    assert len(code) == svc.settings.password_reset_code_length
    assert await svc.verify_and_consume(user.id, code) is True


@pytest.mark.asyncio
async def test_verify_wrong_code_fails(db_session):
    user = User(id="22222222-2222-2222-2222-222222222222", full_name="Test User")
    svc = PasswordResetService(db_session)
    await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, "000000") is False


@pytest.mark.asyncio
async def test_verify_consumes_code(db_session):
    """A code can only be used once."""
    user = User(id="33333333-3333-3333-3333-333333333333", full_name="Test User")
    svc = PasswordResetService(db_session)
    code = await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, code) is True
    assert await svc.verify_and_consume(user.id, code) is False


@pytest.mark.asyncio
async def test_request_reset_replaces_existing_code(db_session):
    """A second request_reset for the same user invalidates the first code
    (at most one active code per user)."""
    user = User(id="44444444-4444-4444-4444-444444444444", full_name="Test User")
    svc = PasswordResetService(db_session)
    first_code = await svc.request_reset(user)
    second_code = await svc.request_reset(user)
    assert await svc.verify_and_consume(user.id, first_code) is False
    assert await svc.verify_and_consume(user.id, second_code) is True
