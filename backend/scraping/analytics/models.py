"""
UMOA Banking Intelligence — Analytics Domain Models

Pydantic data models for financial ratios, eligibility metadata, YoY growth,
sector aggregations, and comparative analytics.
"""
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

RatioStatus = Literal["calculated", "calculated_from_verified", "needs_review", "unavailable"]
GrowthStatus = Literal["calculated", "calculated_from_verified", "needs_review", "unavailable"]
AggregationStatus = Literal["calculated", "partial", "unavailable"]
ScopeType = Literal["country", "umoa"]
ComparisonType = Literal[
    "institution_vs_institution",
    "institution_vs_country",
    "country_vs_umoa",
    "year_vs_year",
]


class ComponentProvenance(BaseModel):
    """Traceability provenance of an individual financial observation feeding a ratio."""

    data_id: str
    metric_code: str
    period_year: int
    period_type: str = "annual"
    value_normalized: Decimal | None = None
    currency: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    document_id: str | None = None
    page_number: int | None = None
    status: str
    role: str | None = None


class RatioDefinition(BaseModel):
    """Specification of a financial ratio in the platform catalogue."""

    ratio_code: str
    name_fr: str
    name_en: str
    description_fr: str
    description_en: str
    formula: str
    numerator_metric: str
    denominator_metric: str
    requires_average_denominator: bool = False
    unit: str = "%"
    frequency: str = "annual"
    required_metrics: list[str]
    eligibility_rules: list[str]


class RatioCalculationResult(BaseModel):
    """Outcome of a ratio calculation with strict traceability and status."""

    ratio_code: str
    ratio_name: str
    institution_id: str
    institution_name: str | None = None
    country_code: str | None = None
    period_year: int
    period_type: str = "annual"
    value: Decimal | None = None
    value_percent: float | None = None
    unit: str = "%"
    status: RatioStatus
    reason: str | None = None
    formula_used: str
    components: list[ComponentProvenance] = Field(default_factory=list)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GrowthCalculationResult(BaseModel):
    """Annual variation (YoY) for a financial metric."""

    metric_code: str
    metric_label: str | None = None
    institution_id: str
    institution_name: str | None = None
    country_code: str | None = None
    current_year: int
    previous_year: int
    current_value: Decimal | None = None
    previous_value: Decimal | None = None
    absolute_change: Decimal | None = None
    growth_rate: float | None = None
    growth_percent: float | None = None
    currency: str | None = None
    status: GrowthStatus
    reason: str | None = None
    components: list[ComponentProvenance] = Field(default_factory=list)
    calculated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SectorAggregationResult(BaseModel):
    """Aggregated financial indicator at the Country or UMOA regional level."""

    scope: ScopeType
    country_code: str | None = None
    country_name: str | None = None
    year: int
    metric_code: str
    metric_label: str | None = None
    total_value: Decimal | None = None
    currency: str = "XOF"
    institution_count: int
    total_institutions: int
    coverage_ratio: float
    is_partial: bool
    status: AggregationStatus
    contributing_institutions: list[str] = Field(default_factory=list)
    notes: str | None = None


class MarketShareResult(BaseModel):
    """Institution's market share within its country sector for a specific metric."""

    institution_id: str
    institution_name: str | None = None
    country_code: str
    year: int
    metric_code: str
    institution_value: Decimal
    sector_total_value: Decimal
    market_share: float
    market_share_percent: float
    currency: str = "XOF"
    coverage_ratio: float
    status: Literal["calculated", "needs_review", "unavailable"]


class ComparisonResult(BaseModel):
    """Comparative indicator between entities or time periods."""

    comparison_type: ComparisonType
    entity_a: str
    entity_b: str
    metric_or_ratio: str
    year: int
    value_a: float | None = None
    value_b: float | None = None
    unit: str | None = None
    difference: float | None = None
    ratio_a_to_b: float | None = None
    description: str
