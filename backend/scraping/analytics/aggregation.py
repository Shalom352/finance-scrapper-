"""
UMOA Banking Intelligence — Sector & Regional Aggregator

Computes sector totals at the Country and UMOA regional levels with strict deduplication
per institution and explicit coverage ratio reporting.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

from scraping.analytics.eligibility import EligibilityEngine
from scraping.analytics.models import (
    AggregationStatus,
    SectorAggregationResult,
)
from scraping.consolidation.models import ObservationSummary


class SectorAggregator:
    """Aggregates institution metrics into country and regional totals without double counting."""

    def __init__(self) -> None:
        self.eligibility = EligibilityEngine()

    def aggregate_country(
        self,
        country_code: str,
        year: int,
        metric_code: str,
        observations: list[ObservationSummary | Any],
        total_institutions_in_country: int,
        country_name: str | None = None,
        metric_label: str | None = None,
        include_needs_review: bool = False,
    ) -> SectorAggregationResult:
        """
        Compute sector total for a single country and metric.

        Invariant: Exactly ONE consolidated observation per institution is counted.
        """
        # Group observations by institution_id
        by_institution: dict[str, list[ObservationSummary | Any]] = defaultdict(list)
        for obs in observations:
            inst_id = getattr(obs, "institution_id", None)
            m_code = getattr(obs, "metric_code", None)
            p_year = getattr(obs, "period_year", None)

            if inst_id and m_code == metric_code and p_year == year:
                by_institution[inst_id].append(obs)

        contributing_ids: list[str] = []
        total_sum = Decimal("0")
        has_needs_review_contributions = False

        for inst_id, obs_list in by_institution.items():
            best_obs, conflict = self.eligibility.select_authoritative_observation(obs_list)
            if not best_obs:
                continue

            if best_obs.status == "rejected":
                continue

            if best_obs.status == "needs_review" and not include_needs_review:
                has_needs_review_contributions = True
                continue

            if best_obs.value_normalized is not None:
                total_sum += best_obs.value_normalized
                contributing_ids.append(inst_id)

        inst_count = len(contributing_ids)
        tot_inst = max(total_institutions_in_country, inst_count, 1)
        coverage_ratio = round(inst_count / tot_inst, 4)
        is_partial = coverage_ratio < 1.0

        status: AggregationStatus
        if inst_count == 0:
            status = "unavailable"
            total_val = None
        elif is_partial:
            status = "partial"
            total_val = total_sum
        else:
            status = "calculated"
            total_val = total_sum

        notes = None
        if is_partial:
            notes = (
                f"Partial coverage: {inst_count}/{tot_inst} institutions represented "
                f"({round(coverage_ratio * 100, 1)}%)."
            )
        if has_needs_review_contributions and not include_needs_review:
            notes = f"{notes or ''} Observations with 'needs_review' status were excluded."

        return SectorAggregationResult(
            scope="country",
            country_code=country_code.upper(),
            country_name=country_name,
            year=year,
            metric_code=metric_code,
            metric_label=metric_label,
            total_value=total_val,
            currency="XOF",
            institution_count=inst_count,
            total_institutions=tot_inst,
            coverage_ratio=coverage_ratio,
            is_partial=is_partial,
            status=status,
            contributing_institutions=contributing_ids,
            notes=notes.strip() if notes else None,
        )

    def aggregate_umoa(
        self,
        year: int,
        metric_code: str,
        country_aggregations: list[SectorAggregationResult],
        total_institutions_umoa: int,
        metric_label: str | None = None,
    ) -> SectorAggregationResult:
        """
        Aggregate country totals into a regional UMOA total.

        Verifies currency homogeneity and combines institutional coverage.
        """
        total_sum = Decimal("0")
        all_contributing: list[str] = []
        countries_represented: set[str] = set()

        for c_agg in country_aggregations:
            if c_agg.total_value is not None:
                total_sum += c_agg.total_value
                all_contributing.extend(c_agg.contributing_institutions)
                if c_agg.country_code:
                    countries_represented.add(c_agg.country_code)

        inst_count = len(all_contributing)
        tot_inst = max(total_institutions_umoa, inst_count, 1)
        coverage_ratio = round(inst_count / tot_inst, 4)
        is_partial = coverage_ratio < 1.0 or len(countries_represented) < 8

        status: AggregationStatus
        if inst_count == 0:
            status = "unavailable"
            total_val = None
        elif is_partial:
            status = "partial"
            total_val = total_sum
        else:
            status = "calculated"
            total_val = total_sum

        notes = (
            f"Regional UMOA total covers {len(countries_represented)}/8 countries and "
            f"{inst_count}/{tot_inst} institutions ({round(coverage_ratio * 100, 1)}%)."
        )

        return SectorAggregationResult(
            scope="umoa",
            country_code=None,
            country_name="Union Monétaire Ouest-Africaine",
            year=year,
            metric_code=metric_code,
            metric_label=metric_label,
            total_value=total_val,
            currency="XOF",
            institution_count=inst_count,
            total_institutions=tot_inst,
            coverage_ratio=coverage_ratio,
            is_partial=is_partial,
            status=status,
            contributing_institutions=all_contributing,
            notes=notes,
        )
