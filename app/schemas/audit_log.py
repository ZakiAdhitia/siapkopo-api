"""Schemas for audit log listing."""
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AuditLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    actor_user_id: UUID | None = None
    actor_name: str
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    description: str
    created_at: datetime
