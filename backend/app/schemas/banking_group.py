"""UMOA Banking Intelligence — Banking Group Schemas"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.source import SourceList


class BankingGroupRead(BaseModel):
    """Banking group response schema."""

    id: str
    name: str
    short_name: str | None = None
    headquarter_country_code: str | None = None
    headquarter_city: str | None = None
    website_url: str | None = None
    description: str | None = None
    source_id: str | None = None
    source: SourceList | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class BankingGroupList(BaseModel):
    """Lightweight banking group for lists."""

    id: str
    name: str
    short_name: str | None = None
    headquarter_country_code: str | None = None

    model_config = {"from_attributes": True}
