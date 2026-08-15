import pytest


async def _token(client, identifier="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


@pytest.mark.asyncio
async def test_template_and_field_crud_flow(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}

    created = await client.post("/api/v1/templates", json={
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    assert created.status_code == 200
    template_id = created.json()["data"]["id"]

    listed = await client.get("/api/v1/templates", headers=h)
    assert listed.json()["data"]["total"] >= 1

    field = await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "lama_tinggal", "label": "Lama Tinggal", "field_type": "text",
    }, headers=h)
    assert field.status_code == 200
    field_id = field.json()["data"]["id"]
    assert field.json()["data"]["order_index"] == 0

    fields = await client.get(f"/api/v1/templates/{template_id}/fields", headers=h)
    assert len(fields.json()["data"]) == 1

    field2 = await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "tujuan", "label": "Tujuan", "field_type": "text",
    }, headers=h)
    field2_id = field2.json()["data"]["id"]

    reordered = await client.put(
        f"/api/v1/templates/{template_id}/fields/reorder",
        json={"field_ids": [field2_id, field_id]}, headers=h,
    )
    assert reordered.status_code == 200
    assert reordered.json()["data"][0]["id"] == field2_id


@pytest.mark.asyncio
async def test_template_manage_requires_permission(client):
    # staff has only template:read — creating must 403.
    staf_tok = await _token(client, "staf", "staf123")
    resp = await client.post("/api/v1/templates", json={
        "code": "x", "name": "X", "icon": "i",
        "color_bg": "#fff", "color_fg": "#000", "numbering_prefix": "1",
        "numbering_pattern": "{prefix}/{seq}/{year}", "pdf_body_template": "<p></p>",
    }, headers={"Authorization": f"Bearer {staf_tok}"})
    assert resp.status_code == 403

    # But staff CAN read.
    listed = await client.get("/api/v1/templates", headers={"Authorization": f"Bearer {staf_tok}"})
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_template_preview_returns_pdf(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    created = await client.post("/api/v1/templates", json={
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}/Ds.Kopo/{year}",
        "pdf_body_template": "<p>Nama: {{ nama }}, Lama: {{ lama_tinggal }}</p>",
    }, headers=h)
    template_id = created.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "lama_tinggal", "label": "Lama Tinggal", "field_type": "text",
    }, headers=h)

    preview = await client.get(f"/api/v1/templates/{template_id}/preview", headers=h)
    assert preview.status_code == 200
    assert preview.content[:5] == b"%PDF-"
    assert preview.headers["content-type"] == "application/pdf"


@pytest.mark.asyncio
async def test_get_template_reports_uses_docx_template(client):
    """2026-08-13 (Tahap 4 preview redesign): frontend uses this flag to
    decide between the real docx PDF viewer and the WYSIWYG HTML editor."""
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}

    docx_backed = await client.post("/api/v1/templates", json={
        "code": "domisili", "name": "Surat Domisili",
        "icon": "home_pin", "color_bg": "#EAF6FF", "color_fg": "#2B76C9",
        "numbering_prefix": "470", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    got = await client.get(f"/api/v1/templates/{docx_backed.json()['data']['id']}", headers=h)
    assert got.json()["data"]["uses_docx_template"] is True

    non_docx = await client.post("/api/v1/templates", json={
        "code": "ubah_data", "name": "Perubahan Elemen Data Kependudukan", "icon": "edit_document",
        "color_bg": "#FDF2E9", "color_fg": "#C6690B",
        "numbering_prefix": "474.1", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama }}</p>",
    }, headers=h)
    got2 = await client.get(f"/api/v1/templates/{non_docx.json()['data']['id']}", headers=h)
    assert got2.json()["data"]["uses_docx_template"] is False
