"""UMOA Banking Intelligence — Financial Data Schemas"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Actor
from app.schemas.document import DocumentList
from app.schemas.institution import InstitutionList
from app.schemas.metric_definition import MetricList
from app.schemas.source import SourceList


class FinancialDataList(BaseModel):
    id: str
    institution_id: str
    metric_code: str
    scope: str
    period_type: str
    period_year: int
    period_label: str | None = None
    value_original: str
    unit_original: str | None = None
    currency_original: str | None = None
    value_normalized: Decimal | None = None
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    extraction_method: str
    status: str
    model_config = {"from_attributes": True}

class FinancialDataExplorerItem(FinancialDataList):
    """List row enriched for the data explorer (Phase 11): names, provenance summary and
    the row's position in the existing authority rule. The value is exactly as stored."""

    institution_name: str | None = None
    country_code: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    page_number: int | None = None
    # authoritative | superseded | conflict | needs_review | rejected | missing_value
    qualification: str | None = None
    # For a superseded row: the authoritative observation of the same key.
    authoritative_data_id: str | None = None


class FinancialDataFacets(BaseModel):
    """Values really present in the stored observations (feed the explorer filters)."""

    period_years: list[int]
    period_types: list[str]
    scopes: list[str]
    currencies: list[str]
    statuses: list[str]
    metric_codes: list[str]


class FinancialDataRead(BaseModel):
    id: str
    institution_id: str
    source_id: str
    document_id: str
    metric_code: str
    scope: str
    period_type: str
    period_year: int
    period_label: str | None = None
    value_original: str
    unit_original: str | None = None
    currency_original: str | None = None
    value_normalized: Decimal | None = None
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    page_number: int | None = None
    extraction_method: str
    confidence_score: Decimal | None = None
    status: str
    notes: str | None = None
    extracted_at: datetime | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    created_at: datetime
    updated_at: datetime
    # Phase 21 — 'human' | 'automatic' | None; report of the automatic checks; withdrawn by a human
    validation_method: str | None = None
    auto_validation: dict | None = None
    auto_validation_blocked: bool = False

    institution: InstitutionList
    source: SourceList
    document: DocumentList
    metric: MetricList

    model_config = {"from_attributes": True}


class _ExpectedState(BaseModel):
    """State the caller saw before deciding (optimistic concurrency -> 409 if it changed)."""

    expected_status: str | None = None
    expected_updated_at: datetime | None = None


class FinancialDataReviewRequest(_ExpectedState):
    """Payload for promoting a financial data point to reviewed status."""

    actor: Actor
    reviewer_notes: str | None = None
    # A value override is always traced (value before / after, actor, reason) in the audit trail.
    value_normalized_override: Decimal | None = None


class FinancialDataVerifyRequest(_ExpectedState):
    """Payload for promoting a financial data point to verified status.

    ``verified_by`` is kept for compatibility; it is the actor of the decision.
    """

    verified_by: Actor
    verification_notes: str | None = None


class FinancialDataRejectRequest(_ExpectedState):
    """Payload for rejecting a financial data point."""

    actor: Actor
    reason: str  # Mandatory reason for rejection


BULK_REVIEW_MAX_IDS = 100


class BulkExpectedState(_ExpectedState):
    data_id: str


class FinancialDataBulkReviewRequest(BaseModel):
    """Payload for reviewing up to 100 data points in one all-or-nothing transaction."""

    data_ids: list[str] = Field(min_length=1, max_length=BULK_REVIEW_MAX_IDS)
    actor: Actor
    reviewer_notes: str | None = None
    expected: list[BulkExpectedState] = Field(default_factory=list, max_length=BULK_REVIEW_MAX_IDS)

    @field_validator("data_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(set(value)) != len(value):
            raise ValueError("data_ids must be unique")
        return value


class DataQualitySummary(BaseModel):
    """Data quality and validation workflow statistics."""

    total_points: int
    extracted_count: int
    needs_review_count: int
    reviewed_count: int
    verified_count: int
    rejected_count: int
    verification_rate: float | None = None
    needs_review_rate: float | None = None
    distinct_institutions_count: int
    distinct_metrics_count: int


class ObservationResponse(BaseModel):
    """Observation item inside a duplicate or conflict response."""

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


class DuplicateGroupResponse(BaseModel):
    """Group of identical or multi-source duplicate observations."""

    logical_key: str
    institution_id: str
    metric_code: str
    period_year: int
    period_type: str
    duplicate_type: str
    count: int
    observations: list[ObservationResponse]


class ConflictRecordResponse(BaseModel):
    """Discrepancy or contradiction between multiple observations."""

    conflict_id: str
    conflict_type: str
    institution_id: str
    institution_name: str | None = None
    metric_code: str
    period_year: int
    period_type: str
    observations: list[ObservationResponse]
    proposed_resolution: str | None = None
    recommendation_reason: str
    requires_human_review: bool = True
    has_verified_observation: bool = False


class InstitutionCoverageResponse(BaseModel):
    """Historical coverage and continuity metrics for an institution."""

    institution_id: str
    institution_name: str
    country_code: str
    first_year: int | None = None
    last_year: int | None = None
    available_years: list[int]
    missing_years: list[int]
    coverage_ratio: float | None = None
    metrics_available_count: int
    documents_available_count: int
    data_points_count: int


class QualityDimensionResponse(BaseModel):
    """Score and details for an explainable data quality dimension."""

    dimension: str
    status: str
    score: float
    weight: float
    details: str


class HistoricalQualityResponse(BaseModel):
    """Consolidated historical and multi-dimensional quality report."""

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
    overall_quality_score: float
    quality_dimensions: list[QualityDimensionResponse]
