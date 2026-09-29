"""
UMOA Banking Intelligence — Growth Calculator

Computes annual variation (YoY growth rate, percentage, and absolute difference)
for core banking metrics with strict gap and zero handling.
"""
from decimal import Decimal
from typing import Any

from scraping.analytics.eligibility import EligibilityEngine
from scraping.analytics.exceptions import CurrencyMismatchError, ScopeMismatchError, mismatch_kind
from scraping.analytics.models import (
    GrowthCalculationResult,
)
from scraping.consolidation.models import ObservationSummary

CORE_GROWTH_METRICS = [
    "total_actifs",
    "depots_clients",
    "creances_clients",
    "produit_net_bancaire",
    "resultat_net",
    "capitaux_propres",
]


class GrowthCalculator:
    """Calculates annual variation and growth rates without artificial interpolation."""

    def __init__(self) -> None:
        self.eligibility = EligibilityEngine()

    def calculate_growth(
        self,
        metric_code: str,
        institution_id: str,
        year: int,
        observations: list[ObservationSummary | Any],
        institution_name: str | None = None,
        country_code: str | None = None,
        metric_label: str | None = None,
    ) -> GrowthCalculationResult:
        """
        Calculate year-over-year variation for a metric between year t and year t-1.

        Args:
            metric_code: Financial indicator code
            institution_id: Unique bank identifier
            year: Current fiscal year (t)
            observations: List of observations containing data for t and t-1
            institution_name: Optional bank name
            country_code: Optional ISO country code
            metric_label: Optional human-readable metric name
        """
        prev_year = year - 1

        curr_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == metric_code
            and getattr(obs, "period_year", None) == year
        ]
        prev_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == metric_code
            and getattr(obs, "period_year", None) == prev_year
        ]

        best_curr, curr_conflict = self.eligibility.select_authoritative_observation(curr_candidates)
        best_prev, prev_conflict = self.eligibility.select_authoritative_observation(prev_candidates)

        if not best_curr or not best_prev:
            missing = []
            if not best_curr:
                missing.append(f"{metric_code} ({year})")
            if not best_prev:
                missing.append(f"{metric_code} ({prev_year})")
            return GrowthCalculationResult(
                metric_code=metric_code,
                metric_label=metric_label,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                current_year=year,
                previous_year=prev_year,
                status="unavailable",
                reason=f"Missing observation: {', '.join(missing)}",
            )

        comp_curr = self.eligibility.to_component_provenance(best_curr, role="current_year")
        comp_prev = self.eligibility.to_component_provenance(best_prev, role="previous_year")
        components = [comp_curr, comp_prev]

        # Currency mismatch check
        try:
            self.eligibility.validate_currency_compatibility(components)
            self.eligibility.validate_scope_compatibility(components)
        except (CurrencyMismatchError, ScopeMismatchError) as e:
            return GrowthCalculationResult(
                metric_code=metric_code,
                metric_label=metric_label,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                current_year=year,
                previous_year=prev_year,
                status="unavailable",
                reason=f"{mismatch_kind(e)}_mismatch: {e}",
                components=components,
            )

        v_curr = comp_curr.value_normalized
        v_prev = comp_prev.value_normalized

        if v_prev == Decimal("0"):
            return GrowthCalculationResult(
                metric_code=metric_code,
                metric_label=metric_label,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                current_year=year,
                previous_year=prev_year,
                current_value=v_curr,
                previous_value=v_prev,
                status="unavailable",
                reason="zero_base_value: Previous year value is 0; percentage growth undefined",
                components=components,
            )

        abs_diff = v_curr - v_prev
        growth_rate = float(abs_diff / abs(v_prev))
        growth_pct = round(growth_rate * 100.0, 4)

        status = self.eligibility.determine_ratio_status(
            components, has_conflict=(curr_conflict or prev_conflict)
        )

        return GrowthCalculationResult(
            metric_code=metric_code,
            metric_label=metric_label,
            institution_id=institution_id,
            institution_name=institution_name,
            country_code=country_code,
            current_year=year,
            previous_year=prev_year,
            current_value=v_curr,
            previous_value=v_prev,
            absolute_change=abs_diff,
            growth_rate=growth_rate,
            growth_percent=growth_pct,
            currency=comp_curr.currency,
            status=status,
            components=components,
        )
