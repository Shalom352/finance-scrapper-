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

# Sector, country and UMOA aggregates use individual annual accounts only: consolidated
# accounts would double count subsidiaries already reported individually.
SECTOR_SCOPE = "individual"
SECTOR_PERIOD_TYPE = "annual"


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
        data_scope: str = SECTOR_SCOPE,
        period_type: str = SECTOR_PERIOD_TYPE,
    ) -> SectorAggregationResult:
        """
        Compute sector total for a single country and metric.

        Invariants:
          - exactly ONE authoritative observation per institution is counted;
          - only `data_scope` / `period_type` observations are eligible (never mixed);
          - rejected observations and unresolved conflicts never contribute;
          - contributions in different currencies are never summed.
        """
        # Group observations by institution_id
        by_institution: dict[str, list[ObservationSummary | Any]] = defaultdict(list)
        for obs in observations:
            inst_id = getattr(obs, "institution_id", None)
            m_code = getattr(obs, "metric_code", None)
            p_year = getattr(obs, "period_year", None)

            obs_scope = getattr(obs, "scope", None)
            obs_period = getattr(obs, "period_type", None)
            if obs_scope is not None and obs_scope != data_scope:
                continue
            if obs_period is not None and obs_period != period_type:
                continue

            if inst_id and m_code == metric_code and p_year == year:
                by_institution[inst_id].append(obs)

        contributing_ids: list[str] = []
        total_sum = Decimal("0")
        has_needs_review_contributions = False
        conflicting_ids: list[str] = []
        currencies: set[str | None] = set()

        for inst_id, obs_list in by_institution.items():
            best_obs, conflict = self.eligibility.select_authoritative_observation(obs_list)
            if not best_obs:
                continue

            # Divergent unverified values: the pick would be arbitrary, never aggregate it.
            if conflict:
                conflicting_ids.append(inst_id)
                continue

            if best_obs.status == "rejected":
                continue

            if best_obs.status == "needs_review" and not include_needs_review:
                has_needs_review_contributions = True
                continue

            if best_obs.value_normalized is not None:
                total_sum += best_obs.value_normalized
                contributing_ids.append(inst_id)
                currencies.add(best_obs.currency_normalized)

        inst_count = len(contributing_ids)
        # No licensed institution known: coverage is unknown (None), never computed on an
        # invented denominator.
        tot_inst = max(total_institutions_in_country, inst_count)
        coverage_ratio = round(inst_count / tot_inst, 4) if tot_inst > 0 else None
        is_partial = coverage_ratio is not None and coverage_ratio < 1.0
        currency_mismatch = len(currencies) > 1

        status: AggregationStatus
        if currency_mismatch:
            status = "needs_review"
            total_val = None
        elif inst_count == 0:
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
        if conflicting_ids:
            notes = f"{notes or ''} {len(conflicting_ids)} institution(s) excluded: unresolved conflicting values."
        if currency_mismatch:
            found = ", ".join(sorted(c or "unknown" for c in currencies))
            notes = f"{notes or ''} Currency mismatch ({found}): total not computed."

        return SectorAggregationResult(
            scope="country",
            country_code=country_code.upper(),
            country_name=country_name,
            year=year,
            metric_code=metric_code,
            metric_label=metric_label,
            total_value=total_val,
            currency=next(iter(currencies)) if len(currencies) == 1 else None,
            data_scope=data_scope,
            period_type=period_type,
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
        currencies: set[str | None] = set()
        countries_needing_review = [c.country_code for c in country_aggregations if c.status == "needs_review"]

        for c_agg in country_aggregations:
            if c_agg.total_value is not None:
                total_sum += c_agg.total_value
                all_contributing.extend(c_agg.contributing_institutions)
                currencies.add(c_agg.currency)
                if c_agg.country_code:
                    countries_represented.add(c_agg.country_code)

        # A country total that could not be computed (e.g. currency mismatch) or totals in
        # different currencies make the regional sum unreliable: it is not computed.
        needs_review = bool(countries_needing_review) or len(currencies) > 1

        inst_count = len(all_contributing)
        tot_inst = max(total_institutions_umoa, inst_count)
        coverage_ratio = round(inst_count / tot_inst, 4) if tot_inst > 0 else None
        is_partial = (coverage_ratio is not None and coverage_ratio < 1.0) or len(countries_represented) < 8

        status: AggregationStatus
        if needs_review:
            status = "needs_review"
            total_val = None
        elif inst_count == 0:
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
            f"{inst_count}/{tot_inst} institutions"
            f"{f' ({round(coverage_ratio * 100, 1)}%)' if coverage_ratio is not None else ''}."
        )

        return SectorAggregationResult(
            scope="umoa",
            country_code=None,
            country_name="Union Monétaire Ouest-Africaine",
            year=year,
            metric_code=metric_code,
            metric_label=metric_label,
            total_value=total_val,
            currency=next(iter(currencies)) if len(currencies) == 1 and not needs_review else None,
            institution_count=inst_count,
            total_institutions=tot_inst,
            coverage_ratio=coverage_ratio,
            is_partial=is_partial,
            status=status,
            contributing_institutions=all_contributing,
            notes=(
                f"{notes} Not computed: currency mismatch or country total under review"
                f" ({', '.join(c for c in countries_needing_review if c) or 'currencies'})."
                if needs_review
                else notes
            ),
        )
