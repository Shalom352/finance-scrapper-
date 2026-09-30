"""
UMOA Banking Intelligence — Historical Time Series Analyzer

Analyzes temporal continuity, tracks missing periods without interpolation,
and flags explainable historical anomalies without destructive data modification.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import (
    HistoricalAnomaly,
    HistoricalSeries,
    ObservationSummary,
)

NON_NEGATIVE_METRIC_CODES = {
    "TOTAL_ASSETS",
    "CASH_AND_CENTRAL_BANKS",
    "CUSTOMER_DEPOSITS",
    "NET_LOANS",
    "INTERBANK_LOANS",
    "INTERBANK_DEPOSITS",
    "PERSONNEL_EXPENSES",
}


class HistoricalAnalyzer:
    """Evaluates time series continuity and flags irregularities for financial indicators."""

    def __init__(self, extreme_variation_threshold: float = 3.0) -> None:
        self.duplicate_detector = DuplicateDetector()
        self.extreme_variation_threshold = extreme_variation_threshold

    def analyze_series(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[HistoricalSeries]:
        """
        Group observations by (institution_id, metric_code) and perform chronological analysis.

        Returns:
            List of HistoricalSeries with gaps, continuity metrics, and anomalies.
        """
        parsed_obs: list[ObservationSummary] = [
            obs if isinstance(obs, ObservationSummary) else self.duplicate_detector.observation_from_orm(obs)
            for obs in observations
        ]

        # One series per (institution, metric, period type, scope): annual and semi-annual,
        # individual and consolidated are never chained together. Rejected rows are never
        # picked as the value of a year (Phase 13).
        grouped: dict[tuple[str, str, str, str | None], list[ObservationSummary]] = defaultdict(list)
        for obs in parsed_obs:
            if obs.status == "rejected":
                continue
            metric_code = getattr(obs, "metric_code", "")
            if not metric_code and hasattr(obs, "metric"):
                metric_code = getattr(obs.metric, "code", "")
            key = (obs.institution_id, metric_code, obs.period_type, obs.scope)
            grouped[key].append(obs)

        series_list: list[HistoricalSeries] = []

        for (inst_id, metric_code, p_type, scope), items in grouped.items():
            # For each year, select the most authoritative observation if multiple exist
            year_map: dict[int, ObservationSummary] = {}
            for it in items:
                y = it.period_year
                if y not in year_map:
                    year_map[y] = it
                else:
                    # Prefer verified > reviewed > higher confidence
                    existing = year_map[y]
                    if it.status == "verified" and existing.status != "verified":
                        year_map[y] = it
                    elif it.status == "reviewed" and existing.status not in ("verified", "reviewed"):
                        year_map[y] = it
                    elif (it.confidence_score or 0) > (existing.confidence_score or 0) and existing.status == it.status:
                        year_map[y] = it

            sorted_years = sorted(year_map.keys())
            if not sorted_years:
                continue

            first_year = sorted_years[0]
            last_year = sorted_years[-1]
            all_expected_years = set(range(first_year, last_year + 1))
            missing_years = sorted(all_expected_years - set(sorted_years))

            consecutive_count = self._compute_max_consecutive_years(sorted_years)
            has_rupture = len(missing_years) > 0

            anomalies = self._detect_anomalies(metric_code, sorted_years, year_map)

            # Check for series gaps of >= 2 years
            if len(missing_years) >= 2:
                for gap_year in missing_years:
                    anomalies.append(
                        HistoricalAnomaly(
                            anomaly_type="series_gap",
                            year=gap_year,
                            metric_code=metric_code,
                            description=f"Missing observation for year {gap_year} in range [{first_year}-{last_year}]",
                            severity="warning",
                        )
                    )

            series_list.append(
                HistoricalSeries(
                    institution_id=inst_id,
                    institution_name=None,
                    metric_code=metric_code,
                    period_type=p_type,
                    scope=scope,
                    first_year=first_year,
                    last_year=last_year,
                    available_years=sorted_years,
                    missing_years=missing_years,
                    consecutive_years_count=consecutive_count,
                    has_rupture=has_rupture,
                    anomalies=anomalies,
                )
            )

        return series_list

    def _detect_anomalies(
        self,
        metric_code: str,
        sorted_years: list[int],
        year_map: dict[int, ObservationSummary],
    ) -> list[HistoricalAnomaly]:
        """Detect variations, sudden unit shifts, negative values, and repeated identical numbers."""
        anomalies: list[HistoricalAnomaly] = []

        # 1. Negative guardrail check
        if metric_code in NON_NEGATIVE_METRIC_CODES:
            for y in sorted_years:
                obs = year_map[y]
                if obs.value_normalized is not None and obs.value_normalized < Decimal("0"):
                    anomalies.append(
                        HistoricalAnomaly(
                            anomaly_type="negative_guardrail_breach",
                            year=y,
                            metric_code=metric_code,
                            current_value=obs.value_normalized,
                            description=(
                                f"Metric '{metric_code}' has negative value {obs.value_normalized} in {y}; "
                                "expected non-negative value according to catalogue."
                            ),
                            severity="flag",
                            data_id=obs.id,
                        )
                    )

        # 2. Year-to-year variation and unit checks
        for i in range(1, len(sorted_years)):
            prev_y = sorted_years[i - 1]
            curr_y = sorted_years[i]
            prev_obs = year_map[prev_y]
            curr_obs = year_map[curr_y]

            v_prev = prev_obs.value_normalized
            v_curr = curr_obs.value_normalized

            # Check currency consistency
            c_prev = prev_obs.currency_normalized or prev_obs.currency_original
            c_curr = curr_obs.currency_normalized or curr_obs.currency_original
            if c_prev and c_curr and c_prev != c_curr:
                anomalies.append(
                    HistoricalAnomaly(
                        anomaly_type="currency_shift",
                        year=curr_y,
                        metric_code=metric_code,
                        description=f"Currency shifted from {c_prev} in {prev_y} to {c_curr} in {curr_y}",
                        severity="flag",
                        data_id=curr_obs.id,
                    )
                )

            if v_prev is not None and v_curr is not None:
                # Sudden unit change check (factor of approx 1000 or 1000000)
                if abs(v_prev) > Decimal("0"):
                    ratio = float(abs(v_curr / v_prev))
                    if 900.0 <= ratio <= 1100.0 or 0.0009 <= ratio <= 0.0011:
                        anomalies.append(
                            HistoricalAnomaly(
                                anomaly_type="sudden_unit_change",
                                year=curr_y,
                                metric_code=metric_code,
                                current_value=v_curr,
                                previous_value=v_prev,
                                description=(
                                    f"Suspected unit scaling change (factor ~{ratio:.1f}) between "
                                    f"{prev_y} ({v_prev}) and {curr_y} ({v_curr})"
                                ),
                                severity="flag",
                                data_id=curr_obs.id,
                            )
                        )

                # Extreme variation check (only for consecutive years)
                if curr_y == prev_y + 1 and abs(v_prev) > Decimal("0"):
                    pct_change = float(abs((v_curr - v_prev) / v_prev))
                    abs_delta = abs(v_curr - v_prev)
                    if pct_change >= self.extreme_variation_threshold and abs_delta >= Decimal("10000"):
                        anomalies.append(
                            HistoricalAnomaly(
                                anomaly_type="extreme_variation",
                                year=curr_y,
                                metric_code=metric_code,
                                current_value=v_curr,
                                previous_value=v_prev,
                                variation_pct=round(pct_change * 100.0, 1),
                                description=(
                                    f"Extreme year-to-year variation (+{pct_change * 100.0:.1f}%) between "
                                    f"{prev_y} ({v_prev}) and {curr_y} ({v_curr})"
                                ),
                                severity="warning",
                                data_id=curr_obs.id,
                            )
                        )

        # 3. Suspicious repeating identical non-zero values across 3+ years
        if len(sorted_years) >= 3:
            for i in range(len(sorted_years) - 2):
                y1, y2, y3 = sorted_years[i], sorted_years[i + 1], sorted_years[i + 2]
                v1, v2, v3 = year_map[y1].value_normalized, year_map[y2].value_normalized, year_map[y3].value_normalized
                if v1 is not None and v2 is not None and v3 is not None:
                    if v1 == v2 == v3 and abs(v1) > Decimal("0"):
                        anomalies.append(
                            HistoricalAnomaly(
                                anomaly_type="repeating_identical_values",
                                year=y3,
                                metric_code=metric_code,
                                current_value=v3,
                                description=(
                                    f"Identical non-zero value ({v3}) repeated across 3 consecutive periods "
                                    f"({y1}, {y2}, {y3})"
                                ),
                                severity="warning",
                                data_id=year_map[y3].id,
                            )
                        )

        return anomalies

    @staticmethod
    def _compute_max_consecutive_years(years: list[int]) -> int:
        """Find the maximum consecutive streak of observed years."""
        if not years:
            return 0
        max_streak = 1
        current_streak = 1
        for i in range(1, len(years)):
            if years[i] == years[i - 1] + 1:
                current_streak += 1
                if current_streak > max_streak:
                    max_streak = current_streak
            elif years[i] != years[i - 1]:
                current_streak = 1
        return max_streak
