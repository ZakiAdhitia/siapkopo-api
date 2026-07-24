"""Approval workflow configuration service: village-scoped ordered steps."""
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.logging import get_logger
from app.models.submission import ApprovalStepConfig, Submission, SubmissionStatus

logger = get_logger("approval_config")


class ApprovalStepConfigService:
    """Manages a village's ordered approval-step chain."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_steps(self, village_id: uuid.UUID) -> list[ApprovalStepConfig]:
        """Return a village's approval steps, ordered."""
        stmt = (
            select(ApprovalStepConfig)
            .where(
                ApprovalStepConfig.village_id == village_id,
                ApprovalStepConfig.deleted_at.is_(None),
            )
            .order_by(ApprovalStepConfig.order_index)
        )
        return list((await self.session.scalars(stmt)).all())

    async def replace_all(
        self, village_id: uuid.UUID, role_ids: list[uuid.UUID]
    ) -> list[ApprovalStepConfig]:
        """Replace a village's entire approval-step chain atomically.

        Rejected with ConflictError if any Submission for the village is
        currently PENDING — reconfiguring mid-flight would leave those
        submissions' current_step_index pointing at a step that may no
        longer exist. Reconfiguration is expected to be a rare admin
        action, not a routine one, so this simple guard is sufficient.
        """
        pending_count = await self.session.scalar(
            select(func.count()).select_from(Submission).where(
                Submission.village_id == village_id,
                Submission.status == SubmissionStatus.PENDING,
            )
        )
        if pending_count:
            raise ConflictError(
                "Tidak dapat mengubah alur persetujuan selagi ada pengajuan yang masih berjalan"
            )

        existing = await self.list_steps(village_id)
        for step in existing:
            await self.session.delete(step)
        await self.session.flush()

        new_steps = [
            ApprovalStepConfig(village_id=village_id, order_index=index, role_id=role_id)
            for index, role_id in enumerate(role_ids)
        ]
        self.session.add_all(new_steps)
        await self.session.commit()
        logger.info("Approval steps replaced village_id=%s count=%d", village_id, len(new_steps))
        return await self.list_steps(village_id)
