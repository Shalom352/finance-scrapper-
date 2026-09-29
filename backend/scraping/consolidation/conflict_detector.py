"""
UMOA Banking Intelligence — Conflict Detector

Identifies, categorizes, and tracks contradictions between financial data points.
Protects verified observations and applies explainable source priority heuristics.
"""
from collections import defaultdict
from decimal import Decimal
from typing import Any

from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import (
    ConflictRecord,
    ConflictType,
    ObservationSummary,
)


class ConflictDetector:
    """Detects and documents data conflicts without applying destructive updates."""

    def __init__(self) -> None:
        self.duplicate_detector = DuplicateDetector()

    def detect_conflicts(
        self,
        observations: list[ObservationSummary | Any],
    ) -> list[ConflictRecord]:
        """
        Scan observations for discrepancies across identical logical keys.

        Returns:
            List of ConflictRecord objects describing each conflict and proposed resolution.
        """
        parsed_obs: list[ObservationSummary] = [
            obs if isinstance(obs, ObservationSummary) else self.duplicate_detector.observation_from_orm(obs)
            for obs in observations
        ]

        grouped: dict[tuple[str, str, int, str], list[ObservationSummary]] = defaultdict(list)
        for obs in parsed_obs:
            metric_code = getattr(obs, "metric_code", "")
            if not metric_code and hasattr(obs, "metric"):
                metric_code = getattr(obs.metric, "code", "")
            key = (obs.institution_id, metric_code, obs.period_year, obs.period_type)
            grouped[key].append(obs)

        conflicts: list[ConflictRecord] = []

        for (inst_id, metric_code, year, p_type), items in grouped.items():
            if len(items) < 2:
                continue

            conflict_type, reason = self._evaluate_conflict(items)
            if conflict_type is None:
                continue  # Identical duplicates with no value/currency contradiction

            has_verified = any(it.status == "verified" for it in items)
            if has_verified and conflict_type != "conflict_with_verified":
                conflict_type = "conflict_with_verified"
                reason = f"Conflict with verified record: {reason}"

            proposed, rec_reason = self._propose_resolution(items, has_verified)

            conflict_id = f"conf-{inst_id}-{metric_code}-{year}-{p_type}"

            conflicts.append(
                ConflictRecord(
                    conflict_id=conflict_id,
                    conflict_type=conflict_type,
                    institution_id=inst_id,
                    institution_name=None,  # Populated downstream or via joins
                    metric_code=metric_code,
                    period_year=year,
                    period_type=p_type,
                    observations=items,
                    proposed_resolution=proposed,
                    recommendation_reason=rec_reason,
                    requires_human_review=True,
                    has_verified_observation=has_verified,
                )
            )

        return conflicts

    def _evaluate_conflict(
        self,
        items: list[ObservationSummary],
    ) -> tuple[ConflictType | None, str]:
        """Classify conflict nature between matching observations."""
        # 1. Currency conflict check
        currencies = {it.currency_normalized or it.currency_original for it in items if it.currency_normalized or it.currency_original}
        if len(currencies) > 1:
            return "conflicting_currency", f"Heterogeneous currencies observed: {', '.join(currencies)}"

        # 2. Value conflict check
        valid_vals = [it.value_normalized for it in items if it.value_normalized is not None]
        if len(valid_vals) > 1:
            min_val = min(valid_vals)
            max_val = max(valid_vals)
            if abs(max_val - min_val) > Decimal("0.0001"):
                val_strs = [f"{v} ({it.source_name or it.source_id})" for it, v in zip(items, valid_vals, strict=False)]
                return "conflicting_values", f"Divergent normalized values: {', '.join(val_strs)}"

        # 3. Period label mismatch check
        labels = {it.period_label for it in items if it.period_label}
        if len(labels) > 1:
            return "conflicting_period", f"Contradictory period labels: {', '.join(labels)}"

        return None, ""

    def _propose_resolution(
        self,
        items: list[ObservationSummary],
        has_verified: bool,
    ) -> tuple[str | None, str]:
        """
        Formulate an explainable resolution suggestion using source priority and status.

        Rules:
          - If an item is already verified, it is protected and recommended to keep.
          - Otherwise, prefer source with priority 1 (BCEAO / CB-UMOA) over priority 2 or 3.
          - Tie-break using confidence_score.
          - Never overwrite automatically.
        """
        if has_verified:
            verified_item = next(it for it in items if it.status == "verified")
            return (
                f"Retain verified value {verified_item.value_normalized} {verified_item.currency_normalized or ''}",
                f"Observation {verified_item.id} is certified verified by {verified_item.verified_by or 'validator'}. "
                "Invariant: verified observations are protected and must not be overwritten automatically.",
            )

        # Sort candidate observations by:
        # 1. status hierarchy (reviewed > extracted > needs_review > rejected)
        # 2. source priority (1=highest, 3=lowest)
        # 3. confidence_score (highest)
        status_rank = {"reviewed": 1, "extracted": 2, "needs_review": 3, "rejected": 4}

        def rank_key(it: ObservationSummary) -> tuple[int, int, float]:
            s_rank = status_rank.get(it.status, 5)
            p_rank = it.source_priority
            c_score = -float(it.confidence_score or 0.0)
            return (s_rank, p_rank, c_score)

        sorted_items = sorted(items, key=rank_key)
        best = sorted_items[0]

        reason = (
            f"Candidate value {best.value_normalized} from {best.source_name or best.source_id} "
            f"(priority={best.source_priority}, status='{best.status}', confidence={best.confidence_score or 0.0}) "
            "is recommended based on official source hierarchy. Human review required for confirmation."
        )

        return str(best.value_normalized), reason
