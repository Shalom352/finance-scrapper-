"""
UMOA Banking Intelligence — Institution Coverage Analyzer

Calculates historical data depth, continuity ratios, and document distribution
per banking institution across UMOA member states.
"""
from collections import defaultdict
from typing import Any

from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import (
    InstitutionCoverage,
    ObservationSummary,
)


class CoverageAnalyzer:
    """Evaluates data depth, missing intervals, and document coverage per institution."""

    def __init__(self) -> None:
        self.duplicate_detector = DuplicateDetector()

    def analyze_coverage(
        self,
        observations: list[ObservationSummary | Any],
        institution_meta: dict[str, dict[str, str]] | None = None,
    ) -> list[InstitutionCoverage]:
        """
        Group observations by institution and compute historical coverage metrics.

        Args:
            observations: List of observations or ORM rows.
            institution_meta: Optional lookup mapping institution_id -> {"name": str, "country": str}.

        Returns:
            List of InstitutionCoverage objects ordered by institution name.
        """
        parsed_obs: list[ObservationSummary] = [
            obs if isinstance(obs, ObservationSummary) else self.duplicate_detector.observation_from_orm(obs)
            for obs in observations
        ]

        inst_groups: dict[str, list[ObservationSummary]] = defaultdict(list)
        for obs in parsed_obs:
            inst_groups[obs.institution_id].append(obs)

        meta = institution_meta or {}
        coverages: list[InstitutionCoverage] = []

        for inst_id, items in inst_groups.items():
            inst_info = meta.get(inst_id, {})
            name = inst_info.get("name") or inst_id
            country = inst_info.get("country") or "UMOA"

            distinct_years = sorted({it.period_year for it in items if it.period_year > 0})
            distinct_metrics = {getattr(it, "metric_code", "") for it in items if getattr(it, "metric_code", "")}
            distinct_docs = {it.document_id for it in items if it.document_id}

            if distinct_years:
                first_year = distinct_years[0]
                last_year = distinct_years[-1]
                expected_years = set(range(first_year, last_year + 1))
                missing_years = sorted(expected_years - set(distinct_years))
                total_expected = len(expected_years)
                coverage_ratio = round(len(distinct_years) / total_expected, 3) if total_expected > 0 else 1.0
            else:
                first_year = None
                last_year = None
                missing_years = []
                coverage_ratio = None

            coverages.append(
                InstitutionCoverage(
                    institution_id=inst_id,
                    institution_name=name,
                    country_code=country,
                    first_year=first_year,
                    last_year=last_year,
                    available_years=distinct_years,
                    missing_years=missing_years,
                    coverage_ratio=coverage_ratio,
                    metrics_available_count=len(distinct_metrics),
                    documents_available_count=len(distinct_docs),
                    data_points_count=len(items),
                )
            )

        coverages.sort(key=lambda c: (c.country_code, c.institution_name))
        return coverages
