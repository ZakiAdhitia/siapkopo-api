"""Tests for resident Excel import/export: service layer + endpoints."""
import io

import openpyxl
import pytest

from app.services.excel import ResidentExcelService
from app.services.master import VillageService


def _wb(rows):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(
        ["nik", "full_name", "gender", "birth_place", "birth_date", "occupation", "phone", "address"]
    )
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_import_residents(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    data = _wb(
        [
            ["3201", "Budi", "L", "Bogor", "1990-01-01", "Petani", "0812", "Jl A"],
            ["", "Invalid", "L", "", "", "", "", ""],
        ]
    )
    result = await ResidentExcelService(db_session).import_bytes(data, village.id)
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3


@pytest.mark.asyncio
async def test_export_residents(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    out = await ResidentExcelService(db_session).export_bytes({"village_id": village.id})
    assert out[:2] == b"PK"  # xlsx is a zip


@pytest.mark.asyncio
async def test_export_residents_contains_imported_rows(db_session):
    village = await VillageService(db_session).create({"name": "Desa Kopo"})
    data = _wb([["3202", "Ani", "P", "Bogor", "1991-02-02", "Guru", "0813", "Jl B"]])
    await ResidentExcelService(db_session).import_bytes(data, village.id)
    out = await ResidentExcelService(db_session).export_bytes({"village_id": village.id})
    wb = openpyxl.load_workbook(io.BytesIO(out))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "nik"
    assert any(r[0] == "3202" and r[1] == "Ani" for r in rows[1:])


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_import_export_endpoints(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    v = await client.post("/api/v1/villages", json={"name": "Desa Kopo"}, headers=h)
    vid = v.json()["data"]["id"]

    data = _wb([["9001", "Warga Satu", "L", "Bogor", "1985-05-05", "Petani", "0811", "Jl C"]])
    files = {"file": ("residents.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post(
        "/api/v1/residents/import", params={"village_id": vid}, files=files, headers=h
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["imported"] == 1
    assert body["data"]["errors"] == []

    export_resp = await client.get(
        "/api/v1/residents/export", params={"village_id": vid}, headers=h
    )
    assert export_resp.status_code == 200
    assert export_resp.content[:2] == b"PK"
    assert "attachment" in export_resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_import_requires_permission(client):
    # kades lacks resident:import
    v = await client.post(
        "/api/v1/villages",
        json={"name": "V"},
        headers={"Authorization": f"Bearer {await _token(client)}"},
    )
    vid = v.json()["data"]["id"]
    tok = await _token(client, "kades", "kades123")
    h = {"Authorization": f"Bearer {tok}"}
    data = _wb([])
    files = {"file": ("residents.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post(
        "/api/v1/residents/import", params={"village_id": vid}, files=files, headers=h
    )
    assert resp.status_code == 403
