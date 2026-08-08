import pytest


@pytest.mark.asyncio
async def test_login_all_demo_accounts(client):
    for identifier, password in [
        ("staf", "staf123"), ("sekdes", "sekdes123"),
        ("kades", "kades123"), ("operator", "operator123"),
    ]:
        resp = await client.post("/api/v1/auth/login",
                                 json={"identifier": identifier, "password": password})
        assert resp.status_code == 200, identifier
        assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_login_bad_password(client):
    resp = await client.post("/api/v1/auth/login",
                             json={"identifier": "staf", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client):
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "operator", "password": "operator123"})
    token = login.json()["data"]["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "*" in resp.json()["data"]["permissions"]


@pytest.mark.asyncio
async def test_forgot_password_reset_flow(client):
    """API-level analog of the old OTP request/verify flow.

    request-otp/verify-otp are gone, but the dev_code echo behavior they used
    to cover lives on in forgot-password: request a reset code for the demo
    "warga" account (by NIK), use it to set a new password, then confirm the
    new password actually logs in.
    """
    req = await client.post("/api/v1/auth/forgot-password",
                            json={"identifier": "3516064588020003"})
    assert req.status_code == 200
    code = req.json()["data"]["dev_code"]
    assert code

    reset = await client.post("/api/v1/auth/reset-password", json={
        "identifier": "3516064588020003", "code": code, "new_password": "newwarga123",
    })
    assert reset.status_code == 200

    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "3516064588020003", "password": "newwarga123"})
    assert login.status_code == 200
    assert login.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_refresh_returns_new_token_pair(client):
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "staf", "password": "staf123"})
    assert login.status_code == 200
    old_access = login.json()["data"]["access_token"]
    old_refresh = login.json()["data"]["refresh_token"]

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["access_token"]
    assert data["refresh_token"]
    # Rotation issues a brand new pair, not the same tokens.
    assert data["access_token"] != old_access
    assert data["refresh_token"] != old_refresh


@pytest.mark.asyncio
async def test_refresh_rotation_revokes_old_token(client):
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "staf", "password": "staf123"})
    old_refresh = login.json()["data"]["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200

    # Reusing the old (now-revoked) refresh token must be rejected.
    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_logout_blacklists_access_token(client):
    """A logged-out access token is rejected on the very next request, even
    though it hasn't naturally expired yet (TokenBlacklist, replacing the
    old Redis ``bl:{jti}`` key)."""
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "staf", "password": "staf123"})
    token = login.json()["data"]["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    still_valid = await client.get("/api/v1/auth/me", headers=headers)
    assert still_valid.status_code == 200

    logout = await client.post("/api/v1/auth/logout", json={}, headers=headers)
    assert logout.status_code == 200

    after_logout = await client.get("/api/v1/auth/me", headers=headers)
    assert after_logout.status_code == 401


@pytest.mark.asyncio
async def test_logout_also_revokes_refresh_token(client):
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "staf", "password": "staf123"})
    token = login.json()["data"]["access_token"]
    refresh = login.json()["data"]["refresh_token"]

    logout = await client.post(
        "/api/v1/auth/logout", json={"refresh_token": refresh},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert logout.status_code == 200

    resp = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_staf_permissions_are_concrete_db_codes(client):
    login = await client.post("/api/v1/auth/login",
                              json={"identifier": "staf", "password": "staf123"})
    token = login.json()["data"]["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    perms = resp.json()["data"]["permissions"]
    assert "*" not in perms
    assert "master_data:read" in perms
