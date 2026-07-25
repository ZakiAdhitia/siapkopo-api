"""Schemas for dashboard aggregation endpoints."""
from pydantic import BaseModel


class DashboardStats(BaseModel):
    total: int
    pending: int
    rejected: int
    issued: int


class DashboardTrendPoint(BaseModel):
    date: str
    count: int


class DashboardPerJenis(BaseModel):
    template_name: str
    count: int


class DashboardInboxItem(BaseModel):
    id: str
    template_id: str
    current_step_index: int | None = None
    created_at: str
