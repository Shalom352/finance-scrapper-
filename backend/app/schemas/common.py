"""
UMOA Banking Intelligence — Common Schemas

Shared Pydantic schemas reused across multiple API responses.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool

    model_config = {"from_attributes": True}
