"""
UMOA Banking Intelligence — Financial Data Consolidator

Central orchestrator for data deduplication, conflict resolution, historical continuity,
institutional coverage analysis, and quality reporting.
"""
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.consolidation.conflict_detector import ConflictDetector
from scraping.consolidation.coverage_analyzer import CoverageAnalyzer
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.historical_analyzer import HistoricalAnalyzer
from scraping.consolidation.models import (
    ConflictRecord,
    DuplicateGroup,
    HistoricalQualityReport,
    HistoricalSeries,
    InstitutionCoverage,
    ObservationSummary,
)
from scraping.consolidation.quality_analyzer import DataQualityAnalyzer


class FinancialDataConsolidator:
    """Coordinates all analytical consolidation processes across UMOA financial observations."""

    def __init__(self) -> None:
        self.duplicate_detector = DuplicateDetector()
        self.conflict_detector = ConflictDetector()
        self.historical_analyzer = HistoricalAnalyzer()
        self.coverage_analyzer = CoverageAnalyzer()
        self.quality_analyzer = DataQualityAnalyzer()

    async def fetch_observations(
        self,
        db: AsyncSession,
        *,
        institution_id: str | None = None,
        country_code: str | None = None,
        metric_code: str | None = None,
        period_year: int | None = None,
        status: str | None = None,
        source_id: str | None = None,
        limit: int | None = None,
    ) -> list[FinancialData]:
        """Query FinancialData rows from database applying optional metadata filters."""
        stmt = (
            select(FinancialData)
            .options(
                selectinload(FinancialData.institution).selectinload(Institution.country),
                selectinload(FinancialData.source),
                selectinload(FinancialData.document),
                selectinload(FinancialData.metric),
            )
            .where(FinancialData.deleted_at.is_(None))
        )

        if institution_id:
            stmt = stmt.where(FinancialData.institution_id == institution_id)

        if metric_code:
            stmt = stmt.where(FinancialData.metric_code == metric_code)

        if period_year is not None:
            stmt = stmt.where(FinancialData.period_year == period_year)

        if status:
            stmt = stmt.where(FinancialData.status == status)

        if source_id:
            stmt = stmt.where(FinancialData.source_id == source_id)

        if country_code:
            stmt = stmt.join(FinancialData.institution).join(Institution.country).where(Country.code == country_code.upper())

        stmt = stmt.order_by(FinancialData.institution_id, FinancialData.period_year.desc())

        if limit:
            stmt = stmt.limit(limit)

        result = await db.execute(stmt)
        return list(result.scalars().all())

    def get_duplicates(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[DuplicateGroup]:
        """Detect and group potential duplicates."""
        return self.duplicate_detector.detect_duplicates(observations)

    def get_conflicts(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[ConflictRecord]:
        """Identify and classify contradictions."""
        return self.conflict_detector.detect_conflicts(observations)

    def get_historical_series(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[HistoricalSeries]:
        """Evaluate chronological series and flag anomalies."""
        return self.historical_analyzer.analyze_series(observations)

    def get_coverage(
        self,
        observations: list[ObservationSummary | Any],
        institution_meta: dict[str, dict[str, str]] | None = None,
    ) -> list[InstitutionCoverage]:
        """Compute institutional coverage statistics."""
        return self.coverage_analyzer.analyze_coverage(observations, institution_meta=institution_meta)

    def get_quality_report(
        self,
        observations: list[ObservationSummary | Any],
    ) -> HistoricalQualityReport:
        """Synthesize overall explainable quality scorecard."""
        return self.quality_analyzer.generate_report(observations)
