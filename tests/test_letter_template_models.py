import pytest
from sqlalchemy import text

from app.models.letter_template import FieldType, LetterTemplate, TemplateField
from app.models.master import Village


def test_letter_template_tables():
    assert LetterTemplate.__tablename__ == "letter_templates"
    assert TemplateField.__tablename__ == "template_fields"
    assert FieldType.SELECT == "select"


@pytest.mark.asyncio
async def test_field_type_persisted_as_lower_case_value(db_session):
    """field_type must round-trip as its declared value ("select"), not the
    Python enum member name ("SELECT") — verified against the raw stored
    column, not just the ORM-mapped attribute, since SQLAlchemy's Enum type
    defaults to storing member names unless values_callable is set."""
    village = Village(name="Desa Kopo")
    db_session.add(village)
    await db_session.flush()
    template = LetterTemplate(
        village_id=village.id, code="domisili", name="Surat Domisili", icon="home_pin",
        color_bg="#EAF6FF", color_fg="#2B76C9", numbering_prefix="470",
        numbering_pattern="{prefix}/{seq}/Ds.Kopo/{year}", pdf_body_template="<p></p>",
    )
    db_session.add(template)
    await db_session.flush()
    field = TemplateField(
        template_id=template.id, order_index=0, field_key="keperluan", label="Keperluan",
        field_type=FieldType.SELECT, options=["A", "B"], is_required=True,
    )
    db_session.add(field)
    await db_session.commit()

    raw = await db_session.scalar(
        text("SELECT field_type FROM template_fields WHERE id = :id"), {"id": str(field.id)}
    )
    assert raw == "select"
