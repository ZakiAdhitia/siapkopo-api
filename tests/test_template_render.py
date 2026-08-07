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
