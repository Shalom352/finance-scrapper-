"""
UMOA Banking Intelligence — Data Quality Analyzer

Computes an explainable, multi-dimensional quality score across 8 transparent dimensions
(provenance, institution, period, currency, normalization, validation, conflicts, historical coherence).
"""
from typing import Any

from scraping.consolidation.conflict_detector import ConflictDetector
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.historical_analyzer import HistoricalAnalyzer
from scraping.consolidation.models import (
    HistoricalQualityReport,
    ObservationSummary,
    QualityDimensionScore,
)


class DataQualityAnalyzer:
    """Evaluates financial data quality across explainable architectural dimensions."""

    DIMENSION_WEIGHTS: dict[str, float] = {
        "provenance": 0.15,
        "institution": 0.15,
        "period": 0.10,
        "currency": 0.10,
        "normalization": 0.15,
        "validation": 0.15,
        "conflict_absence": 0.10,
        "historical_coherence": 0.10,
    }

    def __init__(self) -> None:
        self.duplicate_detector = DuplicateDetector()
        self.conflict_detector = ConflictDetector()
        self.historical_analyzer = HistoricalAnalyzer()

    def generate_report(
        self,
        observations: list[ObservationSummary | Any],
    ) -> HistoricalQualityReport:
        """
        Evaluate full dataset and synthesize a complete HistoricalQualityReport.

        Returns:
            HistoricalQualityReport containing summary statistics and 8 dimensional scores.
        """
        parsed_obs: list[ObservationSummary] = [
            obs if isinstance(obs, ObservationSummary) else self.duplicate_detector.observation_from_orm(obs)
            for obs in observations
        ]

        total = len(parsed_obs)
        if total == 0:
            return HistoricalQualityReport(
                total_points=0,
                verified_count=0,
                reviewed_count=0,
                needs_review_count=0,
                rejected_count=0,
                extracted_count=0,
                potential_duplicates_count=0,
                conflicts_count=0,
                institutions_covered_count=0,
                metrics_covered_count=0,
                periods_covered_count=0,
                missing_periods_count=0,
                historical_anomalies_count=0,
                overall_quality_score=0.0,
                quality_dimensions=[],
            )

        # 1. Status breakdown
        counts = {"verified": 0, "reviewed": 0, "needs_review": 0, "rejected": 0, "extracted": 0}
        for it in parsed_obs:
            s = it.status.lower()
            if s in counts:
                counts[s] += 1
            else:
                counts["extracted"] += 1

        # 2. Duplicate & conflict evaluation
        duplicates = self.duplicate_detector.detect_duplicates(parsed_obs)
        conflicts = self.conflict_detector.detect_conflicts(parsed_obs)
        conflict_point_ids = {obs.id for c in conflicts for obs in c.observations}

        # 3. Historical series evaluation
        series = self.historical_analyzer.analyze_series(parsed_obs)
        all_anomalies = [a for s in series for a in s.anomalies]
        all_missing_years = {y for s in series for y in s.missing_years}

        # 4. Dimension scores
        dim_scores: list[QualityDimensionScore] = []

        # Provenance: valid source_id, document_id, extraction_method
        prov_pass = sum(1 for it in parsed_obs if it.source_id and it.document_id and it.extraction_method)
        prov_ratio = prov_pass / total
        dim_scores.append(self._build_dimension("provenance", prov_ratio, f"{prov_pass}/{total} observations carry complete provenance"))

        # Institution: institution_id attached
        inst_pass = sum(1 for it in parsed_obs if it.institution_id and it.institution_id != "unresolved")
        inst_ratio = inst_pass / total
        dim_scores.append(self._build_dimension("institution", inst_ratio, f"{inst_pass}/{total} observations mapped to verified institutions"))

        # Period: period_year in valid range [1900, 2100]
        period_pass = sum(1 for it in parsed_obs if 1900 <= it.period_year <= 2100 and it.period_type in ("annual", "semi_annual", "quarterly"))
        period_ratio = period_pass / total
        dim_scores.append(self._build_dimension("period", period_ratio, f"{period_pass}/{total} observations have certified period metadata"))

        # Currency: currency identified
        curr_pass = sum(1 for it in parsed_obs if it.currency_normalized or it.currency_original)
        curr_ratio = curr_pass / total
        dim_scores.append(self._build_dimension("currency", curr_ratio, f"{curr_pass}/{total} observations explicitly state currency"))

        # Normalization: value_normalized present
        norm_pass = sum(1 for it in parsed_obs if it.value_normalized is not None)
        norm_ratio = norm_pass / total
        dim_scores.append(self._build_dimension("normalization", norm_ratio, f"{norm_pass}/{total} observations successfully normalized"))

        # Validation: workflow maturity (verified=1.0, reviewed=0.8, extracted=0.5, needs_review=0.3, rejected=0.0)
        val_weighted_sum = (
            (counts["verified"] * 1.0)
            + (counts["reviewed"] * 0.8)
            + (counts["extracted"] * 0.5)
            + (counts["needs_review"] * 0.3)
            + (counts["rejected"] * 0.0)
        )
        val_ratio = val_weighted_sum / total
        dim_scores.append(
            self._build_dimension(
                "validation",
                val_ratio,
                f"Status: {counts['verified']} verified, {counts['reviewed']} reviewed, {counts['needs_review']} needs_review",
            )
        )

        # Conflict absence
        no_conflict_pass = total - len(conflict_point_ids)
        conflict_ratio = max(0.0, no_conflict_pass / total)
        dim_scores.append(self._build_dimension("conflict_absence", conflict_ratio, f"{len(conflicts)} active conflict groups affecting {len(conflict_point_ids)} observations"))

        # Historical coherence
        anomaly_count = len(all_anomalies)
        coherence_ratio = max(0.0, 1.0 - (anomaly_count / max(1, len(series) * 3)))
        dim_scores.append(self._build_dimension("historical_coherence", coherence_ratio, f"{anomaly_count} temporal anomalies flagged across {len(series)} indicator series"))

        # 5. Composite overall score (0.0 to 100.0)
        overall = sum(d.score * d.weight for d in dim_scores) * 100.0

        distinct_institutions = {it.institution_id for it in parsed_obs if it.institution_id}
        distinct_metrics = {getattr(it, "metric_code", "") for it in parsed_obs if getattr(it, "metric_code", "")}
        distinct_periods = {it.period_year for it in parsed_obs if it.period_year > 0}

        return HistoricalQualityReport(
            total_points=total,
            verified_count=counts["verified"],
            reviewed_count=counts["reviewed"],
            needs_review_count=counts["needs_review"],
            rejected_count=counts["rejected"],
            extracted_count=counts["extracted"],
            potential_duplicates_count=len(duplicates),
            conflicts_count=len(conflicts),
            institutions_covered_count=len(distinct_institutions),
            metrics_covered_count=len(distinct_metrics),
            periods_covered_count=len(distinct_periods),
            missing_periods_count=len(all_missing_years),
            historical_anomalies_count=len(all_anomalies),
            overall_quality_score=round(overall, 1),
            quality_dimensions=dim_scores,
        )

    def _build_dimension(self, dimension: str, score: float, details: str) -> QualityDimensionScore:
        weight = self.DIMENSION_WEIGHTS.get(dimension, 0.10)
        clamped_score = min(1.0, max(0.0, score))
        if clamped_score >= 0.85:
            status = "pass"
        elif clamped_score >= 0.60:
            status = "warning"
        else:
            status = "fail"

        return QualityDimensionScore(
            dimension=dimension,
            status=status,
            score=round(clamped_score, 3),
            weight=weight,
            details=details,
        )
