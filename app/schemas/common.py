"""Shared schemas: pagination page and query params."""
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    size: int


def build_page(
    items: list[Any], total: int, page: int, size: int, schema: type[BaseModel]
) -> dict:
    """Build a Page-shaped dict from ORM rows for the response envelope."""
    return {
        "items": [schema.model_validate(i).model_dump(mode="json") for i in items],
        "total": total, "page": page, "size": size,
    }
