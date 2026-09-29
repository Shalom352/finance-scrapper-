"""
UMOA Banking Intelligence — Analytics Schemas

Pydantic schemas for the REST API analytics endpoints (/api/v1/analytics/*).
"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class ComponentProvenanceResponse(BaseModel):
    """Provenance details of a data point feeding a derived ratio."""

    model_config = ConfigDict(from_attributes=True)

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


class RatioDefinitionResponse(BaseModel):
    """Specification of an official financial ratio."""

    model_config = ConfigDict(from_attributes=True)

    ratio_code: str
    name_fr: str
    name_en: str
    description_fr: str
    description_en: str
    formula: str
    numerator_metric: str
    denominator_metric: str
    requires_average_denominator: bool
    unit: str
    frequency: str
    required_metrics: list[str]
    eligibility_rules: list[str]


class RatioResponse(BaseModel):
    """Calculated banking ratio with status and component provenance."""

    model_config = ConfigDict(from_attributes=True)

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
    status: str
    reason: str | None = None
    formula_used: str
    components: list[ComponentProvenanceResponse]
    calculated_at: datetime


class GrowthResponse(BaseModel):
    """Annual variation (YoY) for a financial metric."""

    model_config = ConfigDict(from_attributes=True)

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
    status: str
    reason: str | None = None
    components: list[ComponentProvenanceResponse]
    calculated_at: datetime


class SectorAggregationResponse(BaseModel):
    """Aggregated financial indicator at Country or regional UMOA level."""

    model_config = ConfigDict(from_attributes=True)

    scope: str
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
    status: str
    contributing_institutions: list[str]
    notes: str | None = None


class MarketShareResponse(BaseModel):
    """Bank market share for a specific metric in a given country and year."""

    model_config = ConfigDict(from_attributes=True)

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
    status: str


class SectorStructureResponse(BaseModel):
    """Complete structure of a national sector including aggregation and market shares."""

    model_config = ConfigDict(from_attributes=True)

    aggregation: SectorAggregationResponse
    market_shares: list[MarketShareResponse]


class ComparisonResponse(BaseModel):
    """Factual comparative indicator between entities or time periods."""

    model_config = ConfigDict(from_attributes=True)

    comparison_type: str
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
