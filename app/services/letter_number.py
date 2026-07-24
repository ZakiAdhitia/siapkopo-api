"""Atomic per-(template, year) letter-number sequence allocation."""
import uuid

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.submission import LetterNumberCounter

logger = get_logger("letter_number")


class LetterNumberService:
    """Allocates letter sequence numbers without a SELECT-then-UPDATE race window."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def allocate(self, template_id: uuid.UUID, year: int) -> int:
        """Atomically allocate and return the next sequence number.

        Uses a single INSERT ... ON CONFLICT DO UPDATE ... RETURNING
        statement (dialect-appropriate: Postgres in production, SQLite in
        tests — both support this) so concurrent allocations for the same
        (template_id, year) can never observe or return the same number.
        No explicit row locking or application-level retry loop is needed;
        the database enforces atomicity via the unique constraint.
        """
        insert_fn = pg_insert if self.session.bind.dialect.name == "postgresql" else sqlite_insert
        stmt = (
            insert_fn(LetterNumberCounter)
            .values(template_id=template_id, year=year, last_seq=1)
            .on_conflict_do_update(
                index_elements=["template_id", "year"],
                set_={"last_seq": LetterNumberCounter.__table__.c.last_seq + 1},
            )
            .returning(LetterNumberCounter.last_seq)
        )
        result = await self.session.execute(stmt)
        seq = result.scalar_one()
        await self.session.commit()
        logger.info("Letter number allocated template_id=%s year=%d seq=%d", template_id, year, seq)
        return seq
