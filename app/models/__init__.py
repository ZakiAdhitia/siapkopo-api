"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import (  # noqa: F401
    auth, lapduk, letter_template, master, notification, portal, submission,
)
