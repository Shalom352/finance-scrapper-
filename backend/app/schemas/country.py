"""UMOA Banking Intelligence — Country Schemas"""

from datetime import datetime

from pydantic import BaseModel, Field


class CountryRead(BaseModel):
    """Country response schema."""

    id: str
    code: str = Field(description="ISO 3166-1 alpha-2 country code")
    name_fr: str
    name_en: str
    flag_emoji: str | None = None
    capital_fr: str | None = None
    capital_en: str | None = None
    is_active: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CountryList(BaseModel):
    """Lightweight country representation for lists."""

    id: str
    code: str
    name_fr: str
    name_en: str
    flag_emoji: str | None = None
    is_active: bool

    model_config = {"from_attributes": True}
