import pytest


async def _token(client, username="operator", password="operator123"):
    r = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    return r.json()["data"]["access_token"]


async def _village(client, token):
    r = await client.post("/api/v1/villages", json={"name": "Desa Kopo"},
                          headers={"Authorization": f"Bearer {token}"})
    return r.json()["data"]["id"]


@pytest.mark.asyncio
async def test_template_and_field_crud_flow(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village_id = await _village(client, tok)

    created = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
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
    # kades has only template:read — creating must 403.
    admin_tok = await _token(client)
    village_id = await _village(client, admin_tok)
    kades_tok = await _token(client, "kades", "kades123")
    resp = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "x", "name": "X", "icon": "i",
        "color_bg": "#fff", "color_fg": "#000", "numbering_prefix": "1",
        "numbering_pattern": "{prefix}/{seq}/{year}", "pdf_body_template": "<p></p>",
    }, headers={"Authorization": f"Bearer {kades_tok}"})
    assert resp.status_code == 403

    # But kades CAN read.
    listed = await client.get("/api/v1/templates", headers={"Authorization": f"Bearer {kades_tok}"})
    assert listed.status_code == 200


@pytest.mark.asyncio
async def test_template_preview_returns_pdf(client):
    tok = await _token(client)
    h = {"Authorization": f"Bearer {tok}"}
    village_id = await _village(client, tok)
    created = await client.post("/api/v1/templates", json={
        "village_id": village_id, "code": "domisili", "name": "Surat Domisili",
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
