"""
Review workflow rules (Phase 12) — the EXISTING transitions, written once.

The state machine is the one already enforced by the financial-data services
(Phase 5C); it is only extracted here so the services and the Review Center use
the same guards:

  extracted / needs_review / reviewed ──review──▶ reviewed   (value required)
  reviewed                              ──verify──▶ verified  (validator required)
  any status except rejected            ──reject──▶ rejected  (reason required)

Nothing is ever promoted automatically; every transition is a human action.
"""
from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

ReviewAction = Literal["review", "verify", "reject"]
REVIEW_ACTIONS: tuple[ReviewAction, ...] = ("review", "verify", "reject")


class ReviewError(ValueError):
    """Base class. Subclasses ValueError so the pre-existing routes keep their HTTP 400."""


class ObservationNotFoundError(ReviewError):
    pass


class InvalidTransitionError(ReviewError):
    pass


class StaleStateError(ReviewError):
    """The observation changed since the reviewer loaded it (another decision was recorded)."""


def can_review(status: str, value_normalized: Any) -> bool:
    return status not in ("verified", "rejected") and value_normalized is not None


def can_verify(status: str, value_normalized: Any) -> bool:
    return status == "reviewed" and value_normalized is not None


def can_reject(status: str) -> bool:
    return status != "rejected"


def allowed_actions(status: str, value_normalized: Any) -> list[ReviewAction]:
    allowed: list[ReviewAction] = []
    if can_review(status, value_normalized):
        allowed.append("review")
    if can_verify(status, value_normalized):
        allowed.append("verify")
    if can_reject(status):
        allowed.append("reject")
    return allowed


def check_expected_state(
    row: Any,
    expected_status: str | None,
    expected_updated_at: datetime | None,
) -> None:
    """Optimistic concurrency: refuse a decision taken on a stale view of the observation."""
    if expected_status is not None and row.status != expected_status:
        raise StaleStateError(
            f"Observation status is now '{row.status}' (expected '{expected_status}'); reload before deciding"
        )
    if expected_updated_at is not None and row.updated_at != expected_updated_at:
        raise StaleStateError("Observation was modified since it was loaded; reload before deciding")


DifferenceReason = Literal["same_observation", "missing_value", "currency_mismatch", "unit_mismatch"]


def difference(reference: Any, other: Any) -> tuple[Decimal | None, DifferenceReason | None]:
    """other − reference, only when both values exist in the same currency AND unit.

    Values in different currencies or units are never converted nor compared.
    """
    if other.id == reference.id:
        return None, "same_observation"
    if reference.value_normalized is None or other.value_normalized is None:
        return None, "missing_value"
    if (reference.currency_normalized or None) != (other.currency_normalized or None):
        return None, "currency_mismatch"
    if (reference.unit_normalized or None) != (other.unit_normalized or None):
        return None, "unit_mismatch"
    return Decimal(other.value_normalized) - Decimal(reference.value_normalized), None


def split_by_key(reference: Any, rows: Iterable[Any]) -> tuple[list[Any], list[Any]]:
    """Same logical key (competing) vs. same institution/metric/year but another scope or
    period type (listed separately, never merged nor compared)."""
    competing, not_comparable = [], []
    for r in rows:
        same = r.period_type == reference.period_type and r.scope == reference.scope
        (competing if same else not_comparable).append(r)
    return competing, not_comparable
