from app.models.auth import Role, User, RefreshToken


def test_auth_models_tables():
    assert Role.__tablename__ == "roles"
    assert User.__tablename__ == "users"
    assert RefreshToken.__tablename__ == "refresh_tokens"
