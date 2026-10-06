"""Pydantic models for descriptive rankings and comparisons."""
from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

RankingStatus = Literal["calculated", "partial", "needs_review", "unavailable"]


class ProvenanceRef(BaseModel):
    """Traceability of one financial observation behind a ranked value."""

    data_id: str
    metric_code: str
    period_year: int
    period_type: str
    scope: str | None = None
    source_id: str | None = None
    source_name: str | None = None
    document_id: str | None = None
    document_title: str | None = None
    page_number: int | None = None
    status: str
    role: str | None = None


class Candidate(BaseModel):
    """Qualified (or not) value of one institution for one indicator and period."""

    institution_id: str
    eligible: bool
    value: Decimal | None = None
    currency: str | None = None
    status: str
    reason: str | None = None
    detail: str | None = None
    data_id: str | None = None
    provenance: list[ProvenanceRef] = Field(default_factory=list)


class Coverage(BaseModel):
    """eligible = institutions with an admissible value; ranked = institutions actually ranked.

    When the ranking cannot be computed although values exist (heterogeneous currencies,
    unsupported period type) the coverage is unavailable: ratio None, never 0/N.
    """

    eligible_count: int
    ranked_count: int
    expected_count: int
    # None when no institution is expected or when coverage cannot be established.
    coverage_ratio: float | None = None
    coverage_status: Literal["available", "unavailable"] = "available"


class RankingEntry(BaseModel):
    rank: int
    institution_id: str
    institution_name: str
    country_code: str | None = None
    metric_code: str
    period_year: int
    period_type: str
    data_scope: str
    value: Decimal
    unit: str
    currency: str | None = None
    status: str
    data_id: str | None = None
    provenance: list[ProvenanceRef] = Field(default_factory=list)


class UnavailableEntry(BaseModel):
    """Institution of the universe without an admissible value: never ranked."""

    institution_id: str
    institution_name: str
    country_code: str | None = None
    status: str
    reason: str
    detail: str | None = None
    currency: str | None = None


class ExclusionSummary(BaseModel):
    """Why the universe is (not) ranked, counted per institution.

    Invariant: eligible_count + every excluded_* except excluded_population == universe_total.
    excluded_population counts institutions OUTSIDE the universe (kept in the database,
    never ranked, never part of universe_total).
    """

    universe_source: Literal["reference_universe", "institutions_table"]
    universe_reference_date: date | None = None
    universe_total: int
    eligible_count: int
    excluded_needs_review: int = 0
    excluded_missing: int = 0
    excluded_conflict: int = 0
    excluded_rejected: int = 0
    excluded_scope: int = 0
    excluded_observation_level: int = 0
    excluded_currency: int = 0
    excluded_other: int = 0
    excluded_population: int = 0


class RankingResult(BaseModel):
    metric_code: str
    kind: str
    unit: str
    country_code: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    order: str
    status: RankingStatus
    reason: str | None = None
    currency: str | None = None
    coverage: Coverage
    items: list[RankingEntry]
    total_ranked: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
    unavailable: list[UnavailableEntry]
    available_years: list[int]
    exclusions: ExclusionSummary | None = None
    # Institutions of the requested scope that are outside the ranking universe.
    excluded_population: list[UnavailableEntry] = Field(default_factory=list)


class RankHistoryPoint(BaseModel):
    period_year: int
    rank: int | None = None
    value: Decimal | None = None
    currency: str | None = None
    ranking_status: RankingStatus
    status: str
    reason: str | None = None
    eligible_count: int
    ranked_count: int
    expected_count: int
    coverage_ratio: float | None = None


class RankHistory(BaseModel):
    institution_id: str
    institution_name: str
    metric_code: str
    period_type: str
    data_scope: str
    country_code: str
    points: list[RankHistoryPoint]


class ComparisonRow(BaseModel):
    institution_id: str
    institution_name: str
    country_code: str | None = None
    value: Decimal | None = None
    currency: str | None = None
    status: str
    reason: str | None = None
    data_id: str | None = None
    provenance: list[ProvenanceRef] = Field(default_factory=list)


class InstitutionsComparison(BaseModel):
    metric_code: str
    kind: str
    unit: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: RankingStatus
    reason: str | None = None
    currency: str | None = None
    rows: list[ComparisonRow]


class SectorComparison(BaseModel):
    """Institution vs its national sector (individual + annual, Phase 8C rule)."""

    metric_code: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: RankingStatus
    reason: str | None = None
    institution: ComparisonRow | None = None
    country_code: str | None = None
    sector_total: Decimal | None = None
    sector_currency: str | None = None
    sector_status: str | None = None
    sector_coverage_ratio: float | None = None
    sector_institution_count: int | None = None
    sector_total_institutions: int | None = None
    share_percent: float | None = None


class CountryComparison(BaseModel):
    """Country aggregate vs UMOA aggregate (individual + annual, Phase 8C rule)."""

    metric_code: str
    period_year: int | None = None
    period_type: str
    data_scope: str
    status: RankingStatus
    reason: str | None = None
    country_code: str
    country_total: Decimal | None = None
    country_status: str | None = None
    country_coverage_ratio: float | None = None
    umoa_total: Decimal | None = None
    umoa_status: str | None = None
    umoa_coverage_ratio: float | None = None
    currency: str | None = None
    share_percent: float | None = None
