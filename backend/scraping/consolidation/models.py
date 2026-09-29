"""
UMOA Banking Intelligence — Consolidation Domain Models

Data models for duplicate detection, conflict classification, historical time series,
coverage metrics, and explainable data quality dimensions.
"""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

DuplicateType = Literal["duplicate_identical", "duplicate_different_source", "duplicate_potential"]

ConflictType = Literal[
    "conflicting_values",
    "conflicting_currency",
    "conflicting_period",
    "conflicting_institution",
    "conflict_with_verified",
]

AnomalyType = Literal[
    "extreme_variation",
    "sudden_unit_change",
    "currency_shift",
    "negative_guardrail_breach",
    "repeating_identical_values",
    "series_gap",
]


class ObservationSummary(BaseModel):
    """Concise representation of an individual financial observation."""

    id: str
    institution_id: str
    metric_code: str
    source_id: str
    source_name: str | None = None
    source_type: str | None = None
    source_priority: int = 2
    document_id: str
    document_title: str | None = None
    period_year: int
    period_type: str = "annual"
    period_label: str | None = None
    value_original: str
    unit_original: str | None = None
    currency_original: str | None = None
    value_normalized: Decimal | None = None
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    page_number: int | None = None
    status: str
    extraction_method: str = "pdf_table"
    confidence_score: Decimal | None = None
    verified_by: str | None = None


class DuplicateGroup(BaseModel):
    """Group of financial data observations sharing the same logical key."""

    logical_key: str
    institution_id: str
    metric_code: str
    period_year: int
    period_type: str
    duplicate_type: DuplicateType
    count: int
    observations: list[ObservationSummary]


class ConflictRecord(BaseModel):
    """Divergence or contradiction between multiple observations."""

    conflict_id: str
    conflict_type: ConflictType
    institution_id: str
    institution_name: str | None = None
    metric_code: str
    period_year: int
    period_type: str
    observations: list[ObservationSummary]
    proposed_resolution: str | None = None
    recommendation_reason: str
    requires_human_review: bool = True
    has_verified_observation: bool = False


class HistoricalAnomaly(BaseModel):
    """Irregularity, sudden shift, or inconsistency in a time series."""

    anomaly_type: AnomalyType
    year: int
    metric_code: str
    current_value: Decimal | None = None
    previous_value: Decimal | None = None
    variation_pct: float | None = None
    description: str
    severity: Literal["warning", "flag", "critical"] = "warning"
    data_id: str | None = None


class HistoricalSeries(BaseModel):
    """Chronological sequence of values for an institution and metric."""

    institution_id: str
    institution_name: str | None = None
    metric_code: str
    first_year: int | None = None
    last_year: int | None = None
    available_years: list[int] = Field(default_factory=list)
    missing_years: list[int] = Field(default_factory=list)
    consecutive_years_count: int = 0
    has_rupture: bool = False
    anomalies: list[HistoricalAnomaly] = Field(default_factory=list)


class InstitutionCoverage(BaseModel):
    """Historical data completeness and availability for an institution."""

    institution_id: str
    institution_name: str
    country_code: str
    first_year: int | None = None
    last_year: int | None = None
    available_years: list[int] = Field(default_factory=list)
    missing_years: list[int] = Field(default_factory=list)
    coverage_ratio: float | None = None
    metrics_available_count: int = 0
    documents_available_count: int = 0
    data_points_count: int = 0


class QualityDimensionScore(BaseModel):
    """Evaluation score for a specific dimension of data quality."""

    dimension: str
    status: Literal["pass", "warning", "fail"]
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)
    details: str


class HistoricalQualityReport(BaseModel):
    """Comprehensive synthetic data quality and consolidation report."""

    total_points: int
    verified_count: int
    reviewed_count: int
    needs_review_count: int
    rejected_count: int
    extracted_count: int
    potential_duplicates_count: int
    conflicts_count: int
    institutions_covered_count: int
    metrics_covered_count: int
    periods_covered_count: int
    missing_periods_count: int
    historical_anomalies_count: int
    overall_quality_score: float = Field(ge=0.0, le=100.0)
    quality_dimensions: list[QualityDimensionScore] = Field(default_factory=list)
