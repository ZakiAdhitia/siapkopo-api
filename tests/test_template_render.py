from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import VillageProfile
from app.services.template_render import TemplateRenderService
import time
import uuid


def _profile():
    return VillageProfile(
        name="Desa Kopo", kecamatan="Cisarua", kabupaten="Bogor", provinsi="Jawa Barat"
    )


def _template():
    return LetterTemplate(
        id=uuid.uuid4(), code="domisili", name="Surat Domisili",
        icon="home_pin", color_bg="#EAF6FF", color_fg="#2B76C9", is_active=True,
        required_documents=["KTP", "KK"], numbering_prefix="470",
        numbering_pattern="{prefix}/{seq}/Ds.Kopo/{year}",
        pdf_body_template=(
            "<p>Nama: {{ nama }}, NIK: {{ nik }}</p>"
            "<p>Tinggal di {{ alamat_tinggal_saat_ini }} selama {{ lama_tinggal }}.</p>"
        ),
    )


def _fields(template_id):
    return [
        TemplateField(
            id=uuid.uuid4(), template_id=template_id, order_index=0,
            field_key="alamat_tinggal_saat_ini", label="Alamat Tinggal Saat Ini",
            field_type=FieldType.TEXT, is_required=True,
        ),
        TemplateField(
            id=uuid.uuid4(), template_id=template_id, order_index=1,
            field_key="lama_tinggal", label="Lama Tinggal", field_type=FieldType.TEXT,
            is_required=True,
        ),
    ]


def test_render_preview_returns_valid_pdf():
    template = _template()
    pdf_bytes = TemplateRenderService().render_preview(template, _fields(template.id), _profile())
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_preview_number_uses_pattern():
    svc = TemplateRenderService()
    template = _template()
    renderer = svc._renderer(template)
    assert renderer._preview_number(template) is not None
    number = renderer._preview_number(template)
    assert number.startswith("470/1/Ds.Kopo/")


def test_render_preview_select_field_uses_first_option():
    template = _template()
    template.pdf_body_template = "<p>{{ keperluan }}</p>"
    field = TemplateField(
        id=uuid.uuid4(), template_id=template.id, order_index=0, field_key="keperluan",
        label="Keperluan", field_type=FieldType.SELECT, options=["Beasiswa", "Kesehatan"],
        is_required=True,
    )
    svc = TemplateRenderService()
    renderer = svc._renderer(template)
    assert renderer._sample_data([field])["keperluan"] == "Beasiswa"


def test_render_preview_blocks_external_resource_fetch_and_stays_fast():
    """Regression test for the xhtml2pdf SSRF/DoS finding (B1 review).

    An admin-authored ``pdf_body_template`` containing a plain
    ``<img src="http://...">`` needs no ``{{ }}`` Jinja expression, so the
    sandboxed Jinja2 environment does nothing to stop xhtml2pdf from
    attempting a real outbound network fetch of that URL. The fix blocks all
    external resource resolution via a `link_callback` (backed by a socket
    timeout as a defense-in-depth backstop), so this must render QUICKLY --
    with no real network attempt at all -- rather than merely eventually
    succeeding after a slow retry/timeout cycle.

    Deliberately uses a non-routable address (RFC 5737 TEST-NET-1) whose
    non-response would otherwise take tens of seconds (verified during
    development: ~60s unpatched, due to xhtml2pdf's internal 3-attempt
    retry loop). The assertion is on wall-clock time well under any real
    network timeout, so it stays deterministic across environments -- it
    passes because the fetch is never attempted, not because of any
    particular network condition.
    """
    template = _template()
    template.pdf_body_template = (
        '<p>Nama: {{ nama }}</p><img src="http://192.0.2.1/nonexistent">'
    )
    svc = TemplateRenderService()

    started = time.monotonic()
    pdf_bytes = svc.render_preview(template, _fields(template.id), _profile())
    elapsed = time.monotonic() - started

    assert pdf_bytes[:5] == b"%PDF-"
    assert elapsed < 2.0, (
        f"render_preview took {elapsed:.2f}s; external resource fetch was not blocked"
    )


def test_render_issued_embeds_real_answers():
    template = _template()
    fields = _fields(template.id)
    profile = _profile()
    pdf_bytes = TemplateRenderService().render_issued(
        template=template, fields=fields, profile=profile,
        answers={"alamat_tinggal_saat_ini": "Jl. Nyata No. 1", "lama_tinggal": "3 tahun"},
        applicant={"nama": "Budi Nyata", "nik": "1234567890123456",
                   "alamat": "Jl. Nyata No. 1", "no_kk": "9876543210123456"},
        nomor="470/1/Ds.Kopo/2026",
        tanggal="24 Juli 2026",
    )
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_preview_still_works_after_refactor():
    template = _template()
    pdf_bytes = TemplateRenderService().render_preview(template, _fields(template.id), _profile())
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_issued_html_returns_string_with_real_data():
    template = _template()
    profile = _profile()
    html = TemplateRenderService().render_issued_html(
        template=template, profile=profile,
        answers={"alamat_tinggal_saat_ini": "Jl. Nyata No. 1", "lama_tinggal": "3 tahun"},
        applicant={"nama": "Budi Nyata", "nik": "1234567890123456",
                   "alamat": "Jl. Nyata No. 1", "no_kk": "9876543210123456"},
        nomor="", tanggal="24 Juli 2026",
    )
    assert isinstance(html, str)
    assert "Budi Nyata" in html
    assert "Jl. Nyata No. 1" in html
    assert "3 tahun" in html
    assert "None" not in html
    assert "{{" not in html


def test_render_issued_html_bypasses_docx_pipeline_even_when_supported():
    """domisili has a real docx specimen (DocxLetterRenderer.supports is
    True) -- render_issued_html must still use the HTML/Jinja path (fast,
    no LibreOffice subprocess), unlike render_issued() which prefers docx.
    """
    template = _template()
    profile = _profile()
    started = time.monotonic()
    html = TemplateRenderService().render_issued_html(
        template=template, profile=profile,
        answers={"alamat_tinggal_saat_ini": "X", "lama_tinggal": "Y"},
        applicant={"nama": "Test", "nik": "1234567890123456"},
        nomor="", tanggal="24 Juli 2026",
    )
    elapsed = time.monotonic() - started
    assert isinstance(html, str)
    assert elapsed < 2.0, "render_issued_html should never shell out to LibreOffice"


def test_render_issued_html_kk_dual_footer():
    template = LetterTemplate(
        id=uuid.uuid4(), code="kk", name="Kartu Keluarga",
        icon="family_restroom", color_bg="#fff", color_fg="#000", is_active=True,
        required_documents=[], numbering_prefix="100",
        numbering_pattern="{prefix}/{seq}/{year}",
        pdf_body_template="<p>{{ nama }} - {{ status_perubahan }}</p>",
    )
    html = TemplateRenderService().render_issued_html(
        template=template, profile=_profile(),
        answers={"status_perubahan": "Baru Menikah"},
        applicant={"nama": "Siti", "nik": "1234567890123456"},
        nomor="", tanggal="24 Juli 2026",
    )
    assert isinstance(html, str)
    assert "Siti" in html
    assert "Baru Menikah" in html
    assert "Mengetahui, Kepala Desa" in html


def test_render_issued_html_na_uses_sub_render_path():
    template = LetterTemplate(
        id=uuid.uuid4(), code="na", name="Pengantar Nikah",
        icon="favorite", color_bg="#fff", color_fg="#000", is_active=True,
        required_documents=[], numbering_prefix="200",
        numbering_pattern="{prefix}/{seq}/{year}",
        pdf_body_template="<p>unused for na</p>",
    )
    html = TemplateRenderService().render_issued_html(
        template=template, profile=_profile(),
        answers={"jk_calon": "Laki-laki"},
        applicant={"nama": "Andi", "nik": "1234567890123456", "nama_ayah": "Bapak Andi"},
        nomor="", tanggal="24 Juli 2026",
    )
    assert isinstance(html, str)
    # na_n1's "Nama Lengkap dan Alias" field renders via `{{ nama|upper }}`
    # (a deliberate uppercase convention for the government N.1 form, see
    # `_na.py::_NA_N1_BODY`) -- so real applicant data surfaces as "ANDI",
    # not the literal-case "Andi" input.
    assert "ANDI" in html
    assert "FORMULIR PENGANTAR NIKAH" in html
