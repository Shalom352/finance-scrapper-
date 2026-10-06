"""
Ranking eligibility — reuses the existing qualification rules, adds none.

Published metrics: EligibilityEngine.select_authoritative_observation
  (rejected excluded, verified wins, status rank, conflict detection), then:
    - no usable observation      → missing / rejected_only
    - unresolved conflict        → needs_review (reason "conflict")
    - authoritative needs_review → needs_review (excluded, as in sector aggregation)
    - verified / reviewed / extracted → eligible
Derived indicators (ratios, growth): the RatioCalculator / GrowthCalculator
  status decides; only "calculated" and "calculated_from_verified" are eligible.
"""
from decimal import Decimal
from typing import Any

from scraping.analytics.eligibility import EligibilityEngine
from scraping.analytics.models import ComponentProvenance
from scraping.consolidation.models import ObservationSummary
from scraping.rankings.models import Candidate, ProvenanceRef

ELIGIBLE_DERIVED_STATUSES = {"calculated", "calculated_from_verified"}
# Published metrics: the only statuses a ranked value may carry (priority verified > reviewed > extracted).
ADMISSIBLE_STATUSES = ("verified", "reviewed", "extracted")


def provenance_from_observation(obs: ObservationSummary) -> ProvenanceRef:
    return ProvenanceRef(
        data_id=obs.id,
        metric_code=obs.metric_code,
        period_year=obs.period_year,
        period_type=obs.period_type,
        scope=obs.scope,
        source_id=obs.source_id or None,
        source_name=obs.source_name,
        document_id=obs.document_id or None,
        document_title=obs.document_title,
        page_number=obs.page_number,
        status=obs.status,
    )


def provenance_from_component(comp: ComponentProvenance) -> ProvenanceRef:
    return ProvenanceRef(
        data_id=comp.data_id,
        metric_code=comp.metric_code,
        period_year=comp.period_year,
        period_type=comp.period_type,
        scope=comp.scope,
        source_id=comp.source_id,
        source_name=comp.source_name,
        document_id=comp.document_id,
        page_number=comp.page_number,
        status=comp.status,
        role=comp.role,
    )


def qualify_metric(
    institution_id: str,
    observations: list[ObservationSummary],
    engine: EligibilityEngine,
) -> Candidate:
    """One authoritative published value for (institution, metric, year, period_type, scope)."""
    if not observations:
        return Candidate(institution_id=institution_id, eligible=False, status="unavailable", reason="missing")

    best, conflict = engine.select_authoritative_observation(observations)
    if best is None:
        rejected_only = all(o.status == "rejected" for o in observations)
        return Candidate(
            institution_id=institution_id,
            eligible=False,
            status="unavailable",
            reason="rejected_only" if rejected_only else "missing",
        )
    if conflict:
        return Candidate(
            institution_id=institution_id,
            eligible=False,
            status="needs_review",
            reason="conflict",
            currency=best.currency_normalized,
        )
    if best.status == "needs_review":
        return Candidate(
            institution_id=institution_id,
            eligible=False,
            status="needs_review",
            reason="needs_review",
            currency=best.currency_normalized,
        )
    if best.status not in ADMISSIBLE_STATUSES:
        # Locked: only verified > reviewed > extracted are ever ranked.
        return Candidate(
            institution_id=institution_id,
            eligible=False,
            status="unavailable",
            reason="status_not_admissible",
            detail=best.status,
            currency=best.currency_normalized,
        )
    return Candidate(
        institution_id=institution_id,
        eligible=True,
        value=best.value_normalized,
        currency=best.currency_normalized,
        status=best.status,
        data_id=best.id,
        provenance=[provenance_from_observation(best)],
    )


def qualify_derived(result: Any, value_attr: str, currency: str | None = None) -> Candidate:
    """Ratio / growth result → candidate, using the calculator's own status and reason."""
    value = getattr(result, value_attr, None)
    status = getattr(result, "status", "unavailable")
    components = list(getattr(result, "components", []) or [])
    provenance = [provenance_from_component(c) for c in components]
    if status in ELIGIBLE_DERIVED_STATUSES and value is not None:
        return Candidate(
            institution_id=result.institution_id,
            eligible=True,
            value=Decimal(str(value)),
            currency=currency,
            status=status,
            provenance=provenance,
        )
    return Candidate(
        institution_id=result.institution_id,
        eligible=False,
        status=status if status != "calculated" else "unavailable",
        reason="needs_review" if status == "needs_review" else "missing",
        detail=getattr(result, "reason", None),
        currency=currency,
        provenance=provenance,
    )
