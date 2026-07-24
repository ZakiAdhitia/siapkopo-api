from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village
from app.services.template_render import TemplateRenderService
import uuid


def _village():
    return Village(
        id=uuid.uuid4(), name="Desa Kopo", kecamatan="Cisarua", kabupaten="Bogor", provinsi="Jawa Barat"
    )


def _template():
    return LetterTemplate(
        id=uuid.uuid4(), village_id=uuid.uuid4(), code="domisili", name="Surat Domisili",
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
    pdf_bytes = TemplateRenderService().render_preview(template, _fields(template.id), _village())
    assert pdf_bytes[:5] == b"%PDF-"


def test_render_preview_number_uses_pattern():
    svc = TemplateRenderService()
    template = _template()
    assert svc._preview_number(template) is not None
    number = svc._preview_number(template)
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
    assert svc._sample_data([field])["keperluan"] == "Beasiswa"
