"""UMOA Banking Intelligence — Financial Data Schemas"""
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel

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

    institution: InstitutionList
    source: SourceList
    document: DocumentList
    metric: MetricList

    model_config = {"from_attributes": True}


class FinancialDataReviewRequest(BaseModel):
    """Payload for promoting a financial data point to reviewed status."""

    reviewer_notes: str | None = None
    value_normalized_override: Decimal | None = None


class FinancialDataVerifyRequest(BaseModel):
    """Payload for promoting a financial data point to verified status."""

    verified_by: str  # Mandatory technical identifier of validator (agent code / email)
    verification_notes: str | None = None


class FinancialDataRejectRequest(BaseModel):
    """Payload for rejecting a financial data point."""

    reason: str  # Mandatory reason for rejection


class FinancialDataBulkReviewRequest(BaseModel):
    """Payload for reviewing multiple data points simultaneously."""

    data_ids: list[str]
    reviewer_notes: str | None = None


class DataQualitySummary(BaseModel):
    """Data quality and validation workflow statistics."""

    total_points: int
    extracted_count: int
    needs_review_count: int
    reviewed_count: int
    verified_count: int
    rejected_count: int
    verification_rate: float
    needs_review_rate: float
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
