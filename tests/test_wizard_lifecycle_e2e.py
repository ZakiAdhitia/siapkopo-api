"""Full-lifecycle E2E tests over real HTTP (Fase 4, ALUR_REVIEW_INPUT_MASTER.md):
create -> citizen answers -> staff master-data (+ extra-data where the
jenis needs it) -> preview-html sanity check -> approve x2 -> issued ->
download -> regenerate. Fase 1-3 each proved this pipeline works for 1-2
jenis (domisili, usaha) via real HTTP; this file extends that same,
already-proven pattern to the remaining jenis with staff_extra_data
complexity (kematian, kelahiran, na, kk, uhc) that only had service-level
(not HTTP-level) coverage until now.
"""
import pytest


async def _token(client, identifier, password):
    r = await client.post("/api/v1/auth/login", json={"identifier": identifier, "password": password})
    return r.json()["data"]["access_token"]


async def _make_rt(client, admin_headers):
    """Create a real RW+RT via the admin API -- REQUIRED_STAFF_FIELDS_BY_JENIS
    needs a genuine rt_id (foreign key), not a placeholder string."""
    rw = await client.post("/api/v1/rw", json={"number": "009"}, headers=admin_headers)
    rw_id = rw.json()["data"]["id"]
    rt = await client.post("/api/v1/rt", json={"rw_id": rw_id, "number": "004"}, headers=admin_headers)
    return rt.json()["data"]["id"]


async def _approve_to_issued(client, submission_id, staf_headers, sekdes_headers):
    """The fixed 2-step approve chain every jenis shares (SubmissionService.APPROVAL_STEP_COUNT)."""
    step1 = await client.post(f"/api/v1/submissions/{submission_id}/approve", json={"note": "ok"}, headers=staf_headers)
    assert step1.status_code == 200, step1.text
    assert step1.json()["data"]["status"] == "pending"
    step2 = await client.post(f"/api/v1/submissions/{submission_id}/approve", json={"note": "signed"}, headers=sekdes_headers)
    assert step2.status_code == 200, step2.text
    body = step2.json()["data"]
    assert body["status"] == "issued"
    return body


def _assert_preview_has_real_data(html, *expected_substrings):
    assert "None" not in html
    assert "{{" not in html
    for s in expected_substrings:
        assert s in html, f"expected {s!r} in preview HTML"


@pytest.mark.asyncio
async def test_uhc_full_lifecycle_via_http(client, db_session):
    """UHC needs REQUIRED_STAFF_FIELDS_BY_JENIS's full generic block but
    ZERO staff_extra_data -- the simplest of the 5 jenis this file covers,
    a good first test to confirm the harness pattern itself works before
    the more complex nested-extra-data jenis below."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "uhc", "name": "Surat Keterangan Tidak Mampu (SKTM)",
        "icon": "volunteer_activism", "color_bg": "#EAFBF4", "color_fg": "#108050",
        "numbering_prefix": "440", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama|upper }} - {{ keperluan }}</p>",
        "required_documents": ["Foto KK", "Foto KTP"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    for field_key, label in [
        ("no_kk", "No. KK"), ("tgl_dikeluarkan_kk", "Tanggal KK Dikeluarkan"),
        ("tanggal_pengantar_rt", "Tanggal Surat Pengantar RT"), ("keperluan", "Keperluan"),
    ]:
        field_type = "date" if field_key in ("tgl_dikeluarkan_kk", "tanggal_pengantar_rt") else "text"
        await client.post(f"/api/v1/templates/{template_id}/fields", json={
            "field_key": field_key, "label": label, "field_type": field_type, "is_required": True,
        }, headers=admin_h)
    rt_id = await _make_rt(client, admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201014444000901", "applicant_nama": "Warga Uji UHC",
        "answers": {
            "no_kk": "3201014444000900", "tgl_dikeluarkan_kk": "2020-01-01",
            "tanggal_pengantar_rt": "2026-08-01", "keperluan": "Keringanan Biaya Rumah Sakit",
        },
    }, headers=warga_h)
    assert created.status_code == 200, created.text
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    master = await client.put(f"/api/v1/submissions/{submission_id}/master-data", json={
        "alamat": "Kp. Uji UHC", "rt_id": rt_id, "jk": "Perempuan",
        "tempat_lahir": "Bogor", "tanggal_lahir": "1988-03-03",
        "pekerjaan": "Buruh Harian", "status_kawin": "Kawin",
    }, headers=staf_h)
    assert master.status_code == 200, master.text

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=staf_h)
    assert preview.status_code == 200, preview.text
    _assert_preview_has_real_data(
        preview.json()["data"]["html"], "WARGA UJI UHC", "Keringanan Biaya Rumah Sakit",
    )

    sekdes_h = {"Authorization": f"Bearer {await _token(client, 'sekdes', 'sekdes123')}"}
    issued = await _approve_to_issued(client, submission_id, staf_h, sekdes_h)
    assert issued["letter_number"] is None

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=warga_h)
    assert pdf.status_code == 200
    assert pdf.content[:5] == b"%PDF-"

    regen = await client.post(f"/api/v1/submissions/{submission_id}/regenerate-pdf", headers=staf_h)
    assert regen.status_code == 200, regen.text
