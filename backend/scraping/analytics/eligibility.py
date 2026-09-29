"""
UMOA Banking Intelligence — Analytics Eligibility Engine

Evaluates observation reliability, resolves multiple candidate observations
using official source hierarchy, and assigns strict quality statuses to derived ratios.
"""
from decimal import Decimal
from typing import Any

from scraping.analytics.exceptions import (
    CurrencyMismatchError,
    PeriodMismatchError,
    ScopeMismatchError,
)
from scraping.analytics.models import (
    ComponentProvenance,
    RatioStatus,
)
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import ObservationSummary


class EligibilityEngine:
    """Enforces strict financial data quality rules before calculating derived indicators."""

    def __init__(self) -> None:
        self.duplicate_detector = DuplicateDetector()

    def to_observation_summary(self, item: Any) -> ObservationSummary:
        """Convert ORM or dict-like object to ObservationSummary."""
        if isinstance(item, ObservationSummary):
            return item
        return self.duplicate_detector.observation_from_orm(item)

    def select_authoritative_observation(
        self,
        observations: list[ObservationSummary | Any],
    ) -> tuple[ObservationSummary | None, bool]:
        """
        Select the single most authoritative observation from a list of candidates.

        Returns:
            (best_observation, has_unresolved_conflict)
        """
        if not observations:
            return None, False

        parsed: list[ObservationSummary] = [
            self.to_observation_summary(obs) for obs in observations
        ]

        # Exclude rejected observations immediately
        valid_candidates = [obs for obs in parsed if obs.status != "rejected" and obs.value_normalized is not None]
        if not valid_candidates:
            return None, False

        if len(valid_candidates) == 1:
            return valid_candidates[0], False

        # Check for verified observation
        verified = [obs for obs in valid_candidates if obs.status == "verified"]
        if verified:
            # Verified record always wins
            return verified[0], False

        # Check for value divergence among valid candidates
        vals = [obs.value_normalized for obs in valid_candidates if obs.value_normalized is not None]
        has_conflict = False
        if len(vals) > 1:
            min_v = min(vals)
            max_v = max(vals)
            if abs(max_v - min_v) > Decimal("0.0001"):
                # Divergent values exist and none is verified
                has_conflict = True

        # Rank candidates:
        # 1. status hierarchy (reviewed=1, extracted=2, needs_review=3)
        # 2. source priority (1=highest, 3=lowest)
        # 3. confidence score
        status_rank = {"reviewed": 1, "extracted": 2, "needs_review": 3}

        def rank_key(it: ObservationSummary) -> tuple[int, int, float]:
            s = status_rank.get(it.status, 4)
            p = it.source_priority
            c = -float(it.confidence_score or 0.0)
            return (s, p, c)

        sorted_candidates = sorted(valid_candidates, key=rank_key)
        best = sorted_candidates[0]
        return best, has_conflict

    def to_component_provenance(
        self,
        obs: ObservationSummary,
        role: str,
    ) -> ComponentProvenance:
        """Convert an observation to a component provenance record."""
        return ComponentProvenance(
            data_id=obs.id,
            metric_code=obs.metric_code,
            period_year=obs.period_year,
            period_type=obs.period_type,
            scope=obs.scope,
            value_normalized=obs.value_normalized,
            currency=obs.currency_normalized or obs.currency_original,
            source_id=obs.source_id,
            source_name=obs.source_name,
            document_id=obs.document_id,
            page_number=obs.page_number,
            status=obs.status,
            role=role,
        )

    def determine_ratio_status(
        self,
        components: list[ComponentProvenance],
        has_conflict: bool = False,
    ) -> RatioStatus:
        """
        Determine the resulting ratio status based on component statuses and conflict state.

        Rules:
          - If any component is missing or rejected: unavailable
          - If has_conflict: needs_review
          - If any component has status 'needs_review': needs_review
          - If all components have status 'verified': calculated_from_verified
          - Otherwise: calculated
        """
        if not components:
            return "unavailable"

        if has_conflict:
            return "needs_review"

        statuses = {c.status for c in components}

        if "rejected" in statuses:
            return "unavailable"

        if "needs_review" in statuses:
            return "needs_review"

        if all(c.status == "verified" for c in components):
            return "calculated_from_verified"

        return "calculated"

    def validate_currency_compatibility(
        self,
        components: list[ComponentProvenance],
    ) -> None:
        """Ensure all components share the same currency."""
        currencies = {c.currency for c in components if c.currency}
        if len(currencies) > 1:
            raise CurrencyMismatchError(
                f"Incompatible currencies in ratio components: {', '.join(currencies)}"
            )

    def validate_scope_compatibility(
        self,
        components: list[ComponentProvenance],
    ) -> None:
        """Ensure all components share the same accounting scope (never individual + consolidated)."""
        scopes = {c.scope for c in components if c.scope}
        if len(scopes) > 1:
            raise ScopeMismatchError(
                f"Incompatible accounting scopes in components: {', '.join(sorted(scopes))}"
            )

    def validate_period_compatibility(
        self,
        component_a: ComponentProvenance,
        component_b: ComponentProvenance,
    ) -> None:
        """Ensure synchronous components belong to the same accounting period."""
        if component_a.period_year != component_b.period_year:
            raise PeriodMismatchError(
                f"Period year mismatch: {component_a.period_year} vs {component_b.period_year}"
            )
        if component_a.period_type != component_b.period_type:
            raise PeriodMismatchError(
                f"Period type mismatch: {component_a.period_type} vs {component_b.period_type}"
            )
