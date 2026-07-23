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
