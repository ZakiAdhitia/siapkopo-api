import pytest


@pytest.mark.asyncio
async def test_login_all_demo_accounts(client):
    for username, password in [
        ("staf", "staf123"), ("sekdes", "sekdes123"),
        ("kades", "kades123"), ("operator", "operator123"),
    ]:
        resp = await client.post("/api/v1/auth/login",
                                 json={"username": username, "password": password})
        assert resp.status_code == 200, username
        assert resp.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_login_bad_password(client):
    resp = await client.post("/api/v1/auth/login",
                             json={"username": "staf", "password": "x"})
    assert resp.status_code == 401
    assert resp.json()["error_code"] == "UNAUTHORIZED"


@pytest.mark.asyncio
async def test_me_requires_token(client):
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_with_token(client):
    login = await client.post("/api/v1/auth/login",
                              json={"username": "operator", "password": "operator123"})
    token = login.json()["data"]["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert "*" in resp.json()["data"]["permissions"]


@pytest.mark.asyncio
async def test_otp_flow(client):
    req = await client.post("/api/v1/auth/request-otp", json={"nik": "3516064588020003"})
    assert req.status_code == 200
    code = req.json()["data"]["dev_code"]
    verify = await client.post("/api/v1/auth/verify-otp",
                               json={"nik": "3516064588020003", "code": code})
    assert verify.status_code == 200
    assert verify.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_refresh_returns_new_token_pair(client):
    login = await client.post("/api/v1/auth/login",
                              json={"username": "staf", "password": "staf123"})
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
                              json={"username": "staf", "password": "staf123"})
    old_refresh = login.json()["data"]["refresh_token"]

    first = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert first.status_code == 200

    # Reusing the old (now-revoked) refresh token must be rejected.
    second = await client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert second.status_code == 401


@pytest.mark.asyncio
async def test_staf_permissions_are_concrete_db_codes(client):
    login = await client.post("/api/v1/auth/login",
                              json={"username": "staf", "password": "staf123"})
    token = login.json()["data"]["access_token"]
    resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    perms = resp.json()["data"]["permissions"]
    assert "*" not in perms
    assert "resident:read" in perms
