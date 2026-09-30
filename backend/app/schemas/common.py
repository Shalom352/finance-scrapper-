"""
UMOA Banking Intelligence — Common Schemas

Shared Pydantic schemas reused across multiple API responses.
"""

from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, StringConstraints

T = TypeVar("T")

# Declared human author of a decision (no authentication in the platform: documented limit).
# Mandatory, trimmed, never blank, bounded by the audit column size (255).
ACTOR_MAX_LENGTH = 255
Actor = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=ACTOR_MAX_LENGTH)]


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response wrapper."""

    items: list[T]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool

    model_config = {"from_attributes": True}
