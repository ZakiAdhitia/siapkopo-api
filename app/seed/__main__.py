"""CLI entry: ``python -m app.seed`` — seed the configured database.

Runs ``seed_all`` (RBAC + demo users, then village hierarchy + residents)
against whatever ``DATABASE_URL`` is configured in the environment/.env.
Idempotent: safe to re-run.
"""
import asyncio

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.seed.seed import seed_all

logger = get_logger("seed.cli")


async def _run() -> None:
    """Open a session and run all seeders."""
    async with AsyncSessionLocal() as session:
        await seed_all(session)
    logger.info("Seeding complete.")
    print("Seeding complete.")


if __name__ == "__main__":
    configure_logging()
    asyncio.run(_run())
