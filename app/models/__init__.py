"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import auth, lapduk, letter_template, master, notification, submission  # noqa: F401
