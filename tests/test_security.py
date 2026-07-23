import pytest
from app.core.security import (
    hash_password, verify_password, create_access_token, decode_token, hash_token,
)
from app.core.exceptions import UnauthorizedError


def test_password_roundtrip():
    h = hash_password("secret123")
    assert verify_password("secret123", h)
    assert not verify_password("wrong", h)


def test_access_token_roundtrip():
    token = create_access_token("user-1", "staf", ["resident:read"], "jti-1")
    payload = decode_token(token)
    assert payload["sub"] == "user-1"
    assert payload["role"] == "staf"
    assert "resident:read" in payload["permissions"]
    assert payload["jti"] == "jti-1"


def test_decode_invalid_raises():
    with pytest.raises(UnauthorizedError):
        decode_token("not-a-token")


def test_hash_token_stable():
    assert hash_token("abc") == hash_token("abc")
