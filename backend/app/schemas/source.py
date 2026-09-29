"""UMOA Banking Intelligence — Source Schemas"""

from datetime import datetime

from pydantic import BaseModel, Field


class SourceRead(BaseModel):
    """Source response schema."""

    id: str
    name: str
    short_name: str | None = None
    publisher: str | None = None
    url: str | None = None
    source_type: str = Field(description="Type: regulatory, central_bank, bank, etc.")
    priority: int = Field(description="1=highest (official), 3=secondary")
    country_code: str | None = None
    language: str | None = None
    description: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SourceList(BaseModel):
    """Lightweight source for lists."""

    id: str
    name: str
    short_name: str | None = None
    source_type: str
    priority: int
    country_code: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}
