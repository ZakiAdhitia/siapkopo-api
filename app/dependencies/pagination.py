"""Pagination query params dependency."""
from dataclasses import dataclass

from fastapi import Query


@dataclass
class PaginationParams:
    """Parsed and clamped pagination query parameters."""

    page: int
    size: int


def pagination_params(
    page: int = Query(1, ge=1), size: int = Query(20, ge=1, le=100)
) -> PaginationParams:
    """Parse and clamp pagination query params (size capped at 100)."""
    return PaginationParams(page=page, size=size)
