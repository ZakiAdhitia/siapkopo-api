from app.models.letter_template import FieldType, LetterTemplate, TemplateField


def test_letter_template_tables():
    assert LetterTemplate.__tablename__ == "letter_templates"
    assert TemplateField.__tablename__ == "template_fields"
    assert FieldType.SELECT == "select"
