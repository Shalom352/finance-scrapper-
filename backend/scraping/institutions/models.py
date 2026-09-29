"""Pydantic models of the institution financial profile (Phase 10)."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

from scraping.analytics.models import GrowthCalculationResult, RatioCalculationResult
from scraping.rankings.models import ProvenanceRef

ProfileStatus = Literal["available", "partial", "needs_review", "unavailable"]


class Selection(BaseModel):
    """What the institution actually publishes (non-rejected rows) — feeds the page selectors."""

    scopes: list[str]
    period_types: list[str]
    years: list[int]


class ProfileValue(BaseModel):
    """One qualified (authoritative) value with its full provenance."""

    metric_code: str
    period_year: int
    period_type: str
    period_label: str | None = None
    data_scope: str
    value_original: str
    unit_original: str | None = None
    currency_original: str | None = None
    value_normalized: Decimal
    unit_normalized: str | None = None
    currency: str | None = None
    status: str
    data_id: str
    provenance: ProvenanceRef


class UnavailableValue(BaseModel):
    """Indicator without an admissible value for the selection: never a number."""

    metric_code: str
    period_year: int | None = None
    status: str
    reason: str


class InstitutionFinancials(BaseModel):
    institution_id: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: ProfileStatus
    reason: str | None = None
    selection: Selection
    values: list[ProfileValue]
    unavailable: list[UnavailableValue]


class HistoryPoint(BaseModel):
    period_year: int
    value: Decimal
    currency: str | None = None
    unit_normalized: str | None = None
    status: str
    data_id: str
    provenance: ProvenanceRef


class HistorySeries(BaseModel):
    """One indicator over the years that really hold a qualified value (no point otherwise)."""

    metric_code: str
    status: ProfileStatus
    reason: str | None = None
    currency: str | None = None
    points: list[HistoryPoint]
    # Years inside [first, last] without a qualified value (explicit gaps, never zero).
    missing_years: list[int]
    # Years with values that could not be qualified, and why (conflict, rejected_only, needs_review).
    excluded_years: list[UnavailableValue] = Field(default_factory=list)


class InstitutionHistory(BaseModel):
    institution_id: str
    period_type: str
    data_scope: str
    status: ProfileStatus
    reason: str | None = None
    selection: Selection
    series: list[HistorySeries]


class DataQualityCounts(BaseModel):
    """Descriptive counters of the stored observations — no score, no grade."""

    total_observations: int
    verified: int
    reviewed: int
    extracted: int
    needs_review: int
    rejected: int
    conflicts: int
    missing_years: int


class SourceDocument(BaseModel):
    """Document actually referenced by the provenance of a qualified value."""

    document_id: str
    title: str | None = None
    source_name: str | None = None
    period_years: list[int]
    pages: list[int]
    values_count: int


class InstitutionCoverage(BaseModel):
    institution_id: str
    period_type: str
    data_scope: str
    status: ProfileStatus
    reason: str | None = None
    first_year: int | None = None
    last_year: int | None = None
    available_years: list[int]
    missing_years: list[int]
    available_years_count: int
    # Denominator = every year between first_year and last_year (inclusive); None without data.
    expected_years_count: int | None = None
    coverage_ratio: float | None = None
    quality: DataQualityCounts
    documents: list[SourceDocument]


class InstitutionRatios(BaseModel):
    """Ratios computed by AnalyticsService / RatioCalculator (existing rules, annual only)."""

    institution_id: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: ProfileStatus
    reason: str | None = None
    items: list[RatioCalculationResult]


class InstitutionGrowth(BaseModel):
    """Year-over-year changes computed by AnalyticsService / GrowthCalculator (annual only)."""

    institution_id: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: ProfileStatus
    reason: str | None = None
    items: list[GrowthCalculationResult]
