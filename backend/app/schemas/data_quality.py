"""UMOA Banking Intelligence — Data Quality & Review Center schemas (Phase 12).

Descriptive counters and review payloads only: plain counts of stored observations.
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from app.schemas.financial_data import FinancialDataRead


class DataQualityCounts(BaseModel):
    """Stored observations per status, plus the conflicts decided by the authority rule."""

    total: int
    extracted: int
    needs_review: int
    reviewed: int
    verified: int
    rejected: int
    conflict_keys: int
    conflict_observations: int
    # needs_review observations ∪ observations in conflict (each counted once).
    unresolved: int


class ReviewObservation(BaseModel):
    """An observation shown next to the one under review (same key or other dimension)."""

    id: str
    status: str
    qualification: str | None = None
    scope: str
    period_type: str
    period_year: int
    value_original: str
    value_normalized: Decimal | None = None
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    extraction_method: str
    source_name: str | None = None
    document_title: str | None = None
    page_number: int | None = None
    # other - reviewed observation, only for the same currency and unit.
    difference: Decimal | None = None
    difference_reason: str | None = None


class ReviewDetail(BaseModel):
    observation: FinancialDataRead
    country_code: str | None = None
    qualification: str | None = None
    authoritative_data_id: str | None = None
    allowed_actions: list[str]
    competing: list[ReviewObservation]
    not_comparable: list[ReviewObservation]


class ReviewEventRead(BaseModel):
    id: str
    financial_data_id: str
    action: str
    previous_status: str
    new_status: str
    reason: str | None = None
    actor: str | None = None
    value_before: Decimal | None = None
    value_after: Decimal | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class ReviewActionRequest(BaseModel):
    """A human decision. The resulting status is decided by the backend, never sent."""

    actor: str
    reason: str
    # State the reviewer saw when deciding (optimistic concurrency -> 409 if it changed).
    expected_status: str | None = None
    expected_updated_at: datetime | None = None

    @field_validator("actor", "reason")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be blank")
        return value.strip()
