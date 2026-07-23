"""Import all models so Alembic autogenerate and Base.metadata see them."""
from app.models import auth, master  # noqa: F401
