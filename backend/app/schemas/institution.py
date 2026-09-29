"""UMOA Banking Intelligence — Institution Schemas"""

from datetime import datetime

from pydantic import BaseModel

from app.schemas.banking_group import BankingGroupList
from app.schemas.country import CountryList
from app.schemas.source import SourceList


class InstitutionRead(BaseModel):
    """Full institution response schema."""

    id: str
    name_official: str
    name_commercial: str | None = None
    institution_type: str
    country_id: str
    country: CountryList | None = None
    banking_group_id: str | None = None
    banking_group: BankingGroupList | None = None
    regulatory_id: str | None = None
    website_url: str | None = None
    status: str
    description: str | None = None
    data_notes: str | None = None
    source_id: str | None = None
    source: SourceList | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class InstitutionList(BaseModel):
    """Lightweight institution for list views."""

    id: str
    name_official: str
    name_commercial: str | None = None
    institution_type: str
    country_id: str
    country: CountryList | None = None
    banking_group: BankingGroupList | None = None
    status: str

    model_config = {"from_attributes": True}
