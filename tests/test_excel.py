"""Tests for resident Excel import/export: service layer + endpoints."""
import io

import openpyxl
import pytest

from app.services.excel import ResidentExcelService
from app.services.master import ResidentService


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
    data = _wb(
        [
            ["3201000000000001", "Budi", "L", "Bogor", "1990-01-01", "Petani", "0812", "Jl A"],
            ["", "Invalid", "L", "", "", "", "", ""],
        ]
    )
    result = await ResidentExcelService(db_session).import_bytes(data)
    assert result["imported"] == 1
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3


@pytest.mark.asyncio
async def test_import_duplicate_nik_isolated_by_savepoint(db_session):
    """A duplicate-NIK row must not poison the transaction or lose other rows.

    The 2nd data row reuses the 1st row's NIK, which violates the DB-level
    unique constraint on Resident.nik during flush. That row's failure must
    be isolated to its own SAVEPOINT so the 1st (valid) and 3rd (valid,
    distinct NIK) rows still import and commit, with no exception escaping
    and the duplicate reported in errors.
    """
    data = _wb(
        [
            ["3301000000000001", "Warga Pertama", "L", "Bogor", "1990-01-01", "Petani", "0812", "Jl A"],
            ["3301000000000001", "Warga Duplikat", "L", "Bogor", "1991-01-01", "Guru", "0813", "Jl B"],
            ["3301000000000002", "Warga Ketiga", "P", "Bogor", "1992-01-01", "Guru", "0814", "Jl C"],
        ]
    )
    result = await ResidentExcelService(db_session).import_bytes(data)

    assert result["imported"] == 2
    assert len(result["errors"]) == 1
    assert result["errors"][0]["row"] == 3

    residents, total = await ResidentService(db_session).list(page=1, size=100)
    assert total == 2
    assert {r.nik for r in residents} == {"3301000000000001", "3301000000000002"}


@pytest.mark.asyncio
async def test_export_residents(db_session):
    out = await ResidentExcelService(db_session).export_bytes()
    assert out[:2] == b"PK"  # xlsx is a zip


@pytest.mark.asyncio
async def test_export_residents_contains_imported_rows(db_session):
    data = _wb([["3202000000000001", "Ani", "P", "Bogor", "1991-02-02", "Guru", "0813", "Jl B"]])
    await ResidentExcelService(db_session).import_bytes(data)
    out = await ResidentExcelService(db_session).export_bytes()
    wb = openpyxl.load_workbook(io.BytesIO(out))
    ws = wb.active
    rows = list(ws.iter_rows(values_only=True))
    assert rows[0][0] == "nik"
    assert any(r[0] == "3202000000000001" and r[1] == "Ani" for r in rows[1:])


async def _token(client, identifier="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_import_export_endpoints(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}

    data = _wb([["9001000000000001", "Warga Satu", "L", "Bogor", "1985-05-05", "Petani", "0811", "Jl C"]])
    files = {"file": ("residents.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post("/api/v1/residents/import", files=files, headers=h)
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["data"]["imported"] == 1
    assert body["data"]["errors"] == []

    export_resp = await client.get("/api/v1/residents/export", headers=h)
    assert export_resp.status_code == 200
    assert export_resp.content[:2] == b"PK"
    assert "attachment" in export_resp.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_import_requires_permission(client):
    # kades lacks resident:import
    tok = await _token(client, "kades", "kades123")
    h = {"Authorization": f"Bearer {tok}"}
    data = _wb([])
    files = {"file": ("residents.xlsx", data, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    resp = await client.post("/api/v1/residents/import", files=files, headers=h)
    assert resp.status_code == 403
