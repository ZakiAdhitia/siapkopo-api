import pytest


@pytest.mark.asyncio
async def test_health_ok(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["status"] == "ok"


@pytest.mark.asyncio
async def test_health_ready_checks_database_only(client):
    """Readiness no longer checks Redis (removed) -- just Postgres."""
    resp = await client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    assert resp.json()["data"] == {"database": True}
