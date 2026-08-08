from app.models.auth import PasswordResetCode, Role, TokenBlacklist, User, RefreshToken


def test_auth_models_tables():
    assert Role.__tablename__ == "roles"
    assert User.__tablename__ == "users"
    assert RefreshToken.__tablename__ == "refresh_tokens"
    assert TokenBlacklist.__tablename__ == "token_blacklist"
    assert PasswordResetCode.__tablename__ == "password_reset_codes"
