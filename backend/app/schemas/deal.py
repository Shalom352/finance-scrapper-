"""UMOA Banking Intelligence — Deal Intelligence schemas (Phase 13).

Read models expose NULL as null (never 0). Amount totals are always given per
(currency, unit): no conversion and no sum across currencies or units.
"""
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.constants.deals import DUPLICATE_DECISIONS
from app.schemas.common import ACTOR_MAX_LENGTH


class DealParticipantRead(BaseModel):
    id: str
    participant_name: str
    institution_id: str | None = None
    institution_name: str | None = None
    role: str
    commitment_amount: Decimal | None = None
    commitment_currency: str | None = None
    deal_source_id: str


class DealSourceRead(BaseModel):
    id: str
    deal_id: str
    document_id: str
    document_title: str | None = None
    document_url: str | None = None
    source_id: str
    source_name: str | None = None
    page_number: int
    excerpt: str | None = None
    fields: list[str] = Field(default_factory=list)


class DealDuplicateRead(BaseModel):
    id: str
    other_deal_id: str
    other_deal_title: str | None = None
    other_deal_status: str | None = None
    matched_criteria: list[str]
    state: str
    primary_deal_id: str | None = None
    decided_by: str | None = None
    decided_at: datetime | None = None
    decision_reason: str | None = None


class DealListItem(BaseModel):
    id: str
    title: str
    deal_type: str | None = None
    status: str
    country_code: str | None = None
    sector: str | None = None
    project_name: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    unit: str | None = None
    announcement_date: date | None = None
    signing_date: date | None = None
    borrowers: list[str] = Field(default_factory=list)
    arrangers: list[str] = Field(default_factory=list)
    duplicate_candidates: int = 0
    merged_into_deal_id: str | None = None
    updated_at: datetime


class MergedDealRead(BaseModel):
    id: str
    title: str
    status: str
    sources: list[DealSourceRead]
    participants: list[DealParticipantRead]


class DealDetail(DealListItem):
    amount_original: str | None = None
    interest_rate: Decimal | None = None
    interest_rate_type: str | None = None
    benchmark: str | None = None
    spread_bps: Decimal | None = None
    maturity_months: int | None = None
    grace_period_months: int | None = None
    fees: str | None = None
    guarantees: str | None = None
    financial_close_date: date | None = None
    closing_date: date | None = None
    notes: str | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    created_at: datetime
    participants: list[DealParticipantRead]
    sources: list[DealSourceRead]
    # field name -> ids of the deal sources attesting it
    field_provenance: dict[str, list[str]]
    duplicates: list[DealDuplicateRead]
    merged_deals: list[MergedDealRead]
    allowed_actions: list[str]


class CurrencyTotal(BaseModel):
    currency: str
    unit: str | None = None
    total: Decimal
    deals: int


class DealAnalyticsRow(BaseModel):
    key: str | None
    label: str | None = None
    deals: int
    by_status: dict[str, int]
    # Only reviewed / verified deals with a published amount, per currency AND unit.
    amounts: list[CurrencyTotal]
    deals_without_amount: int


class DealAnalytics(BaseModel):
    dimension: str
    rows: list[DealAnalyticsRow]
    amount_basis: str = "reviewed_or_verified_per_currency_and_unit"


class DuplicateDecisionRequest(BaseModel):
    decision: Literal[DUPLICATE_DECISIONS]  # type: ignore[valid-type]
    # Required for same_deal / same_deal_multi_source: the deal the other one is attached to.
    primary_deal_id: str | None = None
    actor: str = Field(max_length=ACTOR_MAX_LENGTH)
    reason: str
    expected_state: str | None = "duplicate_candidate"

    @field_validator("actor", "reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()
