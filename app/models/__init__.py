"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import (  # noqa: F401
    auth, letter_template, master, portal, submission,
)
