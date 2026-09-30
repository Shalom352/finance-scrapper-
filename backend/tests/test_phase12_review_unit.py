"""
Phase 12 — Data Quality & Review Center: unit tests (no database).

Guards = the existing transitions; services write the audit event in the same
transaction; concurrency and invalid transitions are refused explicitly.
"""
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.data_quality import DataQualityCounts, ReviewActionRequest, ReviewDetail
from app.services.financial_data import (
    reject_financial_data,
    review_financial_data,
    verify_financial_data,
)
from scraping.financial_data.review import (
    InvalidTransitionError,
    ObservationNotFoundError,
    StaleStateError,
    allowed_actions,
    can_reject,
    can_review,
    can_verify,
    check_expected_state,
    difference,
    split_by_key,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


# ---------------------------------------------------------------- guards (existing transitions)

@pytest.mark.parametrize(
    ("status", "value", "expected"),
    [
        ("extracted", Decimal("1"), ["review", "reject"]),
        ("needs_review", Decimal("1"), ["review", "reject"]),
        ("reviewed", Decimal("1"), ["review", "verify", "reject"]),
        ("verified", Decimal("1"), ["reject"]),
        ("rejected", Decimal("1"), []),
        ("extracted", None, ["reject"]),  # nothing to review without a value
        ("reviewed", None, ["reject"]),
    ],
)
def test_allowed_actions_follow_existing_transitions(status, value, expected):
    assert allowed_actions(status, value) == expected


def test_no_automatic_promotion_paths():
    assert not can_verify("needs_review", Decimal("1"))
    assert not can_verify("extracted", Decimal("1"))
    assert not can_review("rejected", Decimal("1")) and not can_verify("rejected", Decimal("1"))
    assert not can_reject("rejected")


def test_expected_state():
    row = SimpleNamespace(status="reviewed", updated_at=T0)
    check_expected_state(row, "reviewed", T0)
    check_expected_state(row, None, None)
    with pytest.raises(StaleStateError):
        check_expected_state(row, "needs_review", None)
    with pytest.raises(StaleStateError):
        check_expected_state(row, "reviewed", datetime(2025, 1, 1, tzinfo=UTC))
    assert issubclass(StaleStateError, ValueError) and issubclass(InvalidTransitionError, ValueError)


# ---------------------------------------------------------------- comparison (never across currencies)

def obs(id_, value, currency="XOF", unit="unit", scope="individual", period_type="annual"):
    return SimpleNamespace(id=id_, value_normalized=None if value is None else Decimal(value),
                           currency_normalized=currency, unit_normalized=unit, scope=scope,
                           period_type=period_type)


def test_difference_same_currency_and_unit_only():
    a = obs("a", "100")
    assert difference(a, obs("b", "130")) == (Decimal("30"), None)
    assert difference(a, a) == (None, "same_observation")
    assert difference(a, obs("b", "0.5", currency="EUR")) == (None, "currency_mismatch")
    assert difference(a, obs("b", "130", unit="millions")) == (None, "unit_mismatch")
    assert difference(a, obs("b", None)) == (None, "missing_value")
    assert difference(obs("c", None), a) == (None, "missing_value")


def test_other_scope_or_period_is_not_comparable():
    ref = obs("a", "100")
    rows = [ref, obs("b", "130"), obs("c", "900", scope="consolidated"), obs("d", "48", period_type="semi_annual")]
    competing, other = split_by_key(ref, rows)
    assert [r.id for r in competing] == ["a", "b"] and [r.id for r in other] == ["c", "d"]


# ---------------------------------------------------------------- services (mocked session)

@pytest.fixture(autouse=True)
def _no_reload(monkeypatch):
    """The services end by re-reading the full record; not the subject of these tests."""
    monkeypatch.setattr("app.services.financial_data.get_financial_data_by_id", AsyncMock(return_value=None))


def session_with(row):
    db = AsyncMock()
    db.add = MagicMock()
    res = MagicMock()
    res.scalar_one_or_none.return_value = row
    db.execute.return_value = res
    return db


def row(status, value=Decimal("100")):
    return MagicMock(id="d1", status=status, value_normalized=value, notes=None, updated_at=T0)


@pytest.mark.asyncio
async def test_review_records_actor_reason_and_values():
    r = row("needs_review")
    db = session_with(r)
    await review_financial_data(db, "d1", reviewer_notes="Read on p.12", actor=" analyst-1 ",
                                expected_status="needs_review", expected_updated_at=T0)
    (e,) = (c.args[0] for c in db.add.call_args_list)
    assert (e.action, e.previous_status, e.new_status, e.actor, e.reason) == (
        "review", "needs_review", "reviewed", "analyst-1", "Read on p.12")
    assert e.value_before == e.value_after == Decimal("100")
    db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_value_override_is_traced():
    r = row("extracted")
    db = session_with(r)
    await review_financial_data(db, "d1", value_normalized_override=Decimal("120"))
    (e,) = (c.args[0] for c in db.add.call_args_list)
    assert (e.value_before, e.value_after) == (Decimal("100"), Decimal("120"))


@pytest.mark.asyncio
async def test_verify_requires_reviewed_and_records_validator():
    db = session_with(row("needs_review"))
    with pytest.raises(InvalidTransitionError, match="Direct verification"):
        await verify_financial_data(db, "d1", verified_by="a")
    db.add.assert_not_called()
    db.commit.assert_not_awaited()

    db = session_with(row("reviewed"))
    await verify_financial_data(db, "d1", verified_by="analyst-2", verification_notes="Audited")
    (e,) = (c.args[0] for c in db.add.call_args_list)
    assert (e.action, e.new_status, e.actor, e.reason) == ("verify", "verified", "analyst-2", "Audited")


@pytest.mark.asyncio
async def test_reject_rules():
    db = session_with(row("needs_review"))
    with pytest.raises(ValueError, match="Rejection reason is mandatory"):
        await reject_financial_data(db, "d1", reason=" ")
    db = session_with(row("rejected"))
    with pytest.raises(InvalidTransitionError):
        await reject_financial_data(db, "d1", reason="again")
    db.add.assert_not_called()
    db = session_with(row("extracted", value=None))  # an observation without value can be rejected
    await reject_financial_data(db, "d1", reason="No value in the table", actor="analyst-1")
    (e,) = (c.args[0] for c in db.add.call_args_list)
    assert (e.previous_status, e.new_status, e.value_before) == ("extracted", "rejected", None)


@pytest.mark.asyncio
async def test_not_found_and_stale_state():
    with pytest.raises(ObservationNotFoundError):
        await reject_financial_data(session_with(None), "nope", reason="x")
    db = session_with(row("reviewed"))
    with pytest.raises(StaleStateError):
        await verify_financial_data(db, "d1", verified_by="a", expected_updated_at=datetime(2020, 1, 1, tzinfo=UTC))
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


# ---------------------------------------------------------------- API contract

def test_action_payload_never_carries_a_status():
    assert "status" not in ReviewActionRequest.model_fields
    assert "new_status" not in ReviewActionRequest.model_fields
    with pytest.raises(ValueError):
        ReviewActionRequest(actor=" ", reason="x")
    with pytest.raises(ValueError):
        ReviewActionRequest(actor="a", reason="")


def test_counters_are_counts_not_scores():
    fields = set(DataQualityCounts.model_fields) | set(ReviewDetail.model_fields)
    assert not {f for f in fields if re.search(r"score|rate|rating|grade|rank", f)}


def test_routes_order():
    from app.main import create_app

    paths = [r.path for r in create_app().routes if r.path.startswith("/api/v1/data-quality")]
    assert paths.index("/api/v1/data-quality/summary") < paths.index("/api/v1/data-quality/{data_id}")


FORBIDDEN = re.compile(
    r"(?i)\b(best|worst|top|leader|winner|loser|strongest|weakest|buy|sell|recommend\w*|"
    r"score|rating|excellent|meilleur\w*|pire|recommand\w*)\b"
)


@pytest.mark.parametrize(
    "path",
    ["scraping/financial_data/review.py", "app/services/data_quality.py", "app/api/v1/data_quality.py",
     "app/schemas/data_quality.py", "app/models/review_event.py"],
)
def test_no_evaluative_vocabulary(path):
    text = (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")
    assert not FORBIDDEN.search(text), path
