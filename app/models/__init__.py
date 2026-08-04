"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import (  # noqa: F401
    attendance, audit_log, auth, letter_template, master, portal, submission,
)
