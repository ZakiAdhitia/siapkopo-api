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


@pytest.mark.asyncio
async def test_kematian_full_lifecycle_via_http(client, db_session):
    """Kematian's staff_extra_data is FLAT (source="extra"), not nested --
    the almarhum's identity fields live at staff_extra_data's top level,
    unlike kelahiran/na below which nest under a sesi key."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "mati", "name": "Ket. Kematian", "icon": "sentiment_very_dissatisfied",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "numbering_prefix": "472", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama_almarhum|upper }} - {{ sebab_meninggal }}</p>",
        "required_documents": ["Foto KTP"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    for field_key, label, field_type, options in [
        ("nama_almarhum", "Nama Almarhum", "text", None),
        ("nik_almarhum", "NIK Almarhum", "text", None),
        ("tgl_meninggal", "Tanggal Meninggal", "date", None),
        ("jam_meninggal", "Jam Meninggal", "text", None),
        ("tempat_meninggal", "Tempat Meninggal", "select", ["Rumah Domisili", "Rumah Sakit", "Puskesmas", "Lainnya"]),
        ("sebab_meninggal", "Sebab Kematian", "text", None),
    ]:
        body = {"field_key": field_key, "label": label, "field_type": field_type, "is_required": True}
        if options:
            body["options"] = options
        await client.post(f"/api/v1/templates/{template_id}/fields", json=body, headers=admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201015555000902", "applicant_nama": "Pelapor Uji Kematian",
        "answers": {
            "nama_almarhum": "Almarhum Uji", "nik_almarhum": "3201015555000800",
            "tgl_meninggal": "2026-07-20", "jam_meninggal": "10:00 WIB",
            "tempat_meninggal": "Rumah Domisili", "sebab_meninggal": "Sakit Biasa",
        },
    }, headers=warga_h)
    assert created.status_code == 200, created.text
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    extra = await client.put(f"/api/v1/submissions/{submission_id}/extra-data", json={
        "jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "1950-01-01",
        "usia_tahun": "76", "pekerjaan": "Pensiunan", "alamat": "Kp. Uji Kematian",
        "rt": "003", "rw": "002",
    }, headers=staf_h)
    assert extra.status_code == 200, extra.text

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=staf_h)
    assert preview.status_code == 200, preview.text
    _assert_preview_has_real_data(preview.json()["data"]["html"], "ALMARHUM UJI", "Sakit Biasa")

    sekdes_h = {"Authorization": f"Bearer {await _token(client, 'sekdes', 'sekdes123')}"}
    issued = await _approve_to_issued(client, submission_id, staf_h, sekdes_h)
    assert issued["status"] == "issued"

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=warga_h)
    assert pdf.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_kelahiran_full_lifecycle_via_http(client, db_session):
    """Kelahiran's staff_extra_data nests THREE sesi (anak/ayah/ibu), each
    source="extra_nested" -- the richest "flat vs nested" contrast against
    kematian's flat shape in the previous test."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "lahir", "name": "Ket. Kelahiran", "icon": "child_friendly",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "numbering_prefix": "471", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama_anak|upper }} anak dari {{ nama_ayah|upper }} dan {{ nama_ibu|upper }}</p>",
        "required_documents": ["Foto KTP Orang Tua"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    for field_key, label in [
        ("nama_anak", "Nama Anak"), ("nama_ayah", "Nama Ayah"), ("nik_ayah", "NIK Ayah"),
        ("nama_ibu", "Nama Ibu"), ("nik_ibu", "NIK Ibu"),
    ]:
        await client.post(f"/api/v1/templates/{template_id}/fields", json={
            "field_key": field_key, "label": label, "field_type": "text", "is_required": True,
        }, headers=admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201016666000903", "applicant_nama": "Pelapor Uji Kelahiran",
        "answers": {
            "nama_anak": "Bayi Uji", "nama_ayah": "Ayah Uji", "nik_ayah": "3201016666000801",
            "nama_ibu": "Ibu Uji", "nik_ibu": "3201016666000802",
        },
    }, headers=warga_h)
    assert created.status_code == 200, created.text
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    extra = await client.put(f"/api/v1/submissions/{submission_id}/extra-data", json={
        "anak": {"jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "2026-07-01",
                 "jam_lahir": "08:00", "anak_ke": "1"},
        "ayah": {"tempat_lahir": "Bogor", "tanggal_lahir": "1990-01-01", "pekerjaan": "Petani",
                 "alamat": "Kp. Uji Kelahiran", "rt": "001", "rw": "002"},
        "ibu": {"tempat_lahir": "Bogor", "tanggal_lahir": "1992-02-02", "pekerjaan": "Ibu Rumah Tangga",
                "alamat": "Kp. Uji Kelahiran", "rt": "001", "rw": "002"},
    }, headers=staf_h)
    assert extra.status_code == 200, extra.text

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=staf_h)
    assert preview.status_code == 200, preview.text
    _assert_preview_has_real_data(preview.json()["data"]["html"], "BAYI UJI", "AYAH UJI", "IBU UJI")

    sekdes_h = {"Authorization": f"Bearer {await _token(client, 'sekdes', 'sekdes123')}"}
    issued = await _approve_to_issued(client, submission_id, staf_h, sekdes_h)
    assert issued["status"] == "issued"

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=warga_h)
    assert pdf.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_na_full_lifecycle_via_http(client, db_session):
    """NA has 4 nested extra-data sesi (calon/ayah/ibu/csi) and its issued
    PDF/preview go through NARenderer's sub-document render path
    (_render_sub -> na_n1), not the plain single-body path every other
    jenis in this file uses -- the one test here that exercises that
    branch over real HTTP end-to-end."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "na", "name": "Pengantar Nikah (NA)", "icon": "favorite",
        "color_bg": "#FFF4EC", "color_fg": "#E06D20",
        "numbering_prefix": "473", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>unused for na</p>",
        "required_documents": ["Foto KTP Calon"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    for field_key, label, field_type, options in [
        ("status_calon", "Status Pernikahan Calon", "select", ["Jejaka", "Perawan", "Duda", "Janda"]),
        ("nama_ayah", "Nama Ayah Kandung", "text", None), ("nik_ayah", "NIK Ayah Kandung", "text", None),
        ("nama_ibu", "Nama Ibu Kandung", "text", None), ("nik_ibu", "NIK Ibu Kandung", "text", None),
        ("nama_pasangan", "Nama Calon Pasangan", "text", None), ("nik_pasangan", "NIK Calon Pasangan", "text", None),
        ("lokasi_akad", "Lokasi Pernikahan", "select", ["Di Dalam Domisili Pengaju", "Di Luar Domisili Pengaju"]),
        ("tgl_akad", "Rencana Tanggal Akad Nikah", "date", None),
    ]:
        body = {"field_key": field_key, "label": label, "field_type": field_type, "is_required": True}
        if options:
            body["options"] = options
        await client.post(f"/api/v1/templates/{template_id}/fields", json=body, headers=admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201017777000904", "applicant_nama": "Calon Uji NA",
        "answers": {
            "status_calon": "Jejaka", "nama_ayah": "Ayah Calon Uji", "nik_ayah": "3201017777000801",
            "nama_ibu": "Ibu Calon Uji", "nik_ibu": "3201017777000802",
            "nama_pasangan": "Pasangan Uji", "nik_pasangan": "3201017777000803",
            "lokasi_akad": "Di Dalam Domisili Pengaju", "tgl_akad": "2026-12-12",
        },
    }, headers=warga_h)
    assert created.status_code == 200, created.text
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    extra = await client.put(f"/api/v1/submissions/{submission_id}/extra-data", json={
        "calon": {"jk": "Laki-laki", "tempat_lahir": "Bogor", "tanggal_lahir": "2000-01-01",
                  "kewarganegaraan": "Indonesia", "agama": "Islam", "pekerjaan": "Wiraswasta",
                  "alamat": "Kp. Uji NA", "rt": "001", "rw": "002"},
        "ayah": {"tempat_lahir": "Bogor", "tanggal_lahir": "1970-01-01", "pekerjaan": "Petani",
                 "alamat": "Kp. Uji NA", "rt": "001", "rw": "002", "kel_desa": "Kopo",
                 "kec": "Cisarua", "kab_kota": "Bogor"},
        "ibu": {"tempat_lahir": "Bogor", "tanggal_lahir": "1972-01-01", "pekerjaan": "Ibu Rumah Tangga",
                "alamat": "Kp. Uji NA", "rt": "001", "rw": "002", "kel_desa": "Kopo",
                "kec": "Cisarua", "kab_kota": "Bogor"},
        "csi": {"bin_binti": "Binti Bapak Pasangan", "jk": "Perempuan", "ttl": "Bogor, 02-02-2000",
                "agama": "Islam", "pekerjaan": "Wiraswasta", "alamat": "Kp. Uji Pasangan",
                "rt": "003", "rw": "004", "kel_desa": "Kopo", "kec": "Cisarua", "kab_kota": "Bogor",
                "provinsi": "Jawa Barat", "shdk": "Kepala Keluarga"},
    }, headers=staf_h)
    assert extra.status_code == 200, extra.text

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=staf_h)
    assert preview.status_code == 200, preview.text
    _assert_preview_has_real_data(preview.json()["data"]["html"], "CALON UJI NA", "FORMULIR PENGANTAR NIKAH")

    sekdes_h = {"Authorization": f"Bearer {await _token(client, 'sekdes', 'sekdes123')}"}
    issued = await _approve_to_issued(client, submission_id, staf_h, sekdes_h)
    assert issued["status"] == "issued"

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=warga_h)
    assert pdf.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_kk_full_lifecycle_via_http(client, db_session):
    """KK's kk_header sesi is source="mixed" (alamat/rt_id in
    staff_master_data, nama_kk/dusun routed to staff_extra_data via
    per-field source overrides) and its anggota sesi is source="extra_list"
    (an array, not a flat dict or nested single block) -- the two shapes
    no other jenis in this file exercises."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "kk", "name": "Kartu Keluarga", "icon": "family_restroom",
        "color_bg": "#EEF1EE", "color_fg": "#5a6b62",
        "numbering_prefix": "474", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama|upper }} - {{ status_perubahan }}</p>",
        "required_documents": ["Foto KTP", "Foto KK Lama"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "status_perubahan", "label": "Status Perubahan", "field_type": "select",
        "options": ["Baru Menikah (Pecah KK Mandiri)"], "is_required": True,
    }, headers=admin_h)
    rt_id = await _make_rt(client, admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201018888000905", "applicant_nama": "Kepala Keluarga Uji KK",
        "answers": {"status_perubahan": "Baru Menikah (Pecah KK Mandiri)"},
    }, headers=warga_h)
    assert created.status_code == 200, created.text
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    master = await client.put(f"/api/v1/submissions/{submission_id}/master-data", json={
        "alamat": "Kp. Uji KK", "rt_id": rt_id, "no_kk": "3201018888000900",
    }, headers=staf_h)
    assert master.status_code == 200, master.text

    extra = await client.put(f"/api/v1/submissions/{submission_id}/extra-data", json={
        "nama_kk": "Kepala Keluarga Uji KK", "dusun": "Dusun Uji",
        "anggota": [
            {"nik": "3201018888000905", "nama": "Kepala Keluarga Uji KK", "jk": "Laki-laki",
             "tempat_lahir": "Bogor", "tanggal_lahir": "1985-05-05", "agama": "Islam",
             "pendidikan": "SMA", "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
             "shdk": "Kepala Keluarga", "wni_wna": "WNI"},
        ],
    }, headers=staf_h)
    assert extra.status_code == 200, extra.text

    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=staf_h)
    assert preview.status_code == 200, preview.text
    _assert_preview_has_real_data(
        preview.json()["data"]["html"], "KEPALA KELUARGA UJI KK", "Baru Menikah (Pecah KK Mandiri)",
    )

    sekdes_h = {"Authorization": f"Bearer {await _token(client, 'sekdes', 'sekdes123')}"}
    issued = await _approve_to_issued(client, submission_id, staf_h, sekdes_h)
    assert issued["status"] == "issued"

    pdf = await client.get(f"/api/v1/submissions/{submission_id}/pdf", headers=warga_h)
    assert pdf.content[:5] == b"%PDF-"


@pytest.mark.asyncio
async def test_kades_can_view_preview_html_but_not_approve(client, db_session):
    """Fase 3's final-review fix widened preview-html's permission gate to
    submission:approve OR submission:read_all so Kepala Desa (admin role,
    holds read_all but not approve) isn't locked out of this read-only
    view. That fix was verified by reading the permission registry; this
    test is the first to actually drive a real kades-authenticated request
    through the live endpoint."""
    admin_h = {"Authorization": f"Bearer {await _token(client, 'operator', 'operator123')}"}
    template = await client.post("/api/v1/templates", json={
        "code": "usaha", "name": "Ket. Usaha (SKU)", "icon": "storefront",
        "color_bg": "#FDEFE7", "color_fg": "#C2582A",
        "numbering_prefix": "475", "numbering_pattern": "{prefix}/{seq}",
        "pdf_body_template": "<p>{{ nama|upper }} - {{ jenis_usaha }}</p>",
        "required_documents": ["Foto KTP"],
    }, headers=admin_h)
    template_id = template.json()["data"]["id"]
    await client.post(f"/api/v1/templates/{template_id}/fields", json={
        "field_key": "jenis_usaha", "label": "Jenis Usaha", "field_type": "text", "is_required": True,
    }, headers=admin_h)
    rt_id = await _make_rt(client, admin_h)

    warga_h = {"Authorization": f"Bearer {await _token(client, 'warga', 'warga123')}"}
    created = await client.post("/api/v1/submissions", json={
        "template_id": template_id,
        "applicant_nik": "3201019999000906", "applicant_nama": "Warga Uji Kades",
        "answers": {"jenis_usaha": "Warung Uji"},
    }, headers=warga_h)
    submission_id = created.json()["data"]["id"]

    staf_h = {"Authorization": f"Bearer {await _token(client, 'staf', 'staf123')}"}
    await client.put(f"/api/v1/submissions/{submission_id}/master-data", json={
        "alamat": "Kp. Uji Kades", "rt_id": rt_id, "jk": "Laki-laki",
        "tempat_lahir": "Bogor", "tanggal_lahir": "1980-01-01",
        "pekerjaan": "Wiraswasta", "status_kawin": "Kawin",
    }, headers=staf_h)

    kades_h = {"Authorization": f"Bearer {await _token(client, 'kades', 'kades123')}"}
    preview = await client.get(f"/api/v1/submissions/{submission_id}/preview-html", headers=kades_h)
    assert preview.status_code == 200, preview.text
    assert "WARGA UJI KADES" in preview.json()["data"]["html"]

    # Kades genuinely cannot approve (staff/sekdes-only chain, HASIL_UJICOBA_PERROLE.md
    # kades item 2) -- the permission widening must not have accidentally
    # granted this too.
    approve_attempt = await client.post(
        f"/api/v1/submissions/{submission_id}/approve", json={"note": "x"}, headers=kades_h,
    )
    assert approve_attempt.status_code == 403
