"""
Phase 10 — Institution financial profile: unit tests (no database).

The profile is the single source of the qualification rules for the institution
page (the former client-side qualification is retired). Covers: profile, history,
annual / semi-annual and individual / consolidated separation, missing data,
unavailable, ratios, growth, provenance, coverage, rejected, conflict,
needs_review, heterogeneous currency, descriptive quality counters.
"""
import ast
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scraping.consolidation.models import ObservationSummary
from scraping.institutions.service import PRIORITY_METRICS, InstitutionProfileService

SVC = InstitutionProfileService()
_seq = iter(range(10**6))


def obs(metric="total_actifs", year=2024, value=100, *, status="extracted", scope="individual",
        period_type="annual", currency="XOF", page=12, doc="doc-1", obs_id=None):
    return ObservationSummary(
        id=obs_id or f"fd-{next(_seq)}",
        institution_id="inst",
        metric_code=metric,
        source_id="src",
        source_name="BCEAO",
        document_id=doc,
        document_title=f"Rapport {doc}",
        period_year=year,
        period_type=period_type,
        scope=scope,
        value_original=f"{value} (millions)",
        unit_original="millions",
        currency_original=currency,
        value_normalized=None if value is None else Decimal(str(value)),
        unit_normalized="unit",
        currency_normalized=currency,
        page_number=page,
        status=status,
    )


def financials(rows, **kw):
    kw.setdefault("period_year", None)
    kw.setdefault("period_type", "annual")
    kw.setdefault("data_scope", "individual")
    return SVC.build_financials("inst", rows, **kw)


def history(rows, **kw):
    kw.setdefault("period_type", "annual")
    kw.setdefault("data_scope", "individual")
    return SVC.build_history("inst", rows, **kw)


def coverage(rows, **kw):
    kw.setdefault("period_type", "annual")
    kw.setdefault("data_scope", "individual")
    return SVC.build_coverage("inst", rows, **kw)


# ---------------------------------------------------------------------------
# Profile (one year)
# ---------------------------------------------------------------------------


def test_institution_without_data_is_unavailable_without_numbers():
    f = financials([])
    assert f.status == "unavailable" and f.reason == "no_data" and f.period_year is None
    assert f.values == []
    assert [u.metric_code for u in f.unavailable] == list(PRIORITY_METRICS)


def test_default_year_is_latest_qualified_year_and_priority_metrics_always_listed():
    f = financials([obs(year=2023, value=90), obs(year=2024, value=100)])
    assert f.period_year == 2024
    assert [v.metric_code for v in f.values] == ["total_actifs"]
    assert {u.metric_code for u in f.unavailable} == set(PRIORITY_METRICS) - {"total_actifs"}
    assert all(u.reason == "missing" for u in f.unavailable)
    assert f.status == "partial"


def test_value_carries_original_normalized_unit_currency_and_provenance():
    v = financials([obs(value=1000, page=84, doc="ar-2024", obs_id="fd-x")]).values[0]
    assert v.value_original == "1000 (millions)" and v.unit_original == "millions"
    assert v.value_normalized == Decimal("1000") and v.currency == "XOF"
    assert (v.period_type, v.data_scope, v.status, v.data_id) == ("annual", "individual", "extracted", "fd-x")
    assert v.provenance.document_id == "ar-2024" and v.provenance.page_number == 84


def test_annual_and_semi_annual_are_never_mixed():
    rows = [obs(value=100), obs(value=48, period_type="semi_annual")]
    assert financials(rows).values[0].value_normalized == Decimal("100")
    semi = financials(rows, period_type="semi_annual").values[0]
    assert semi.value_normalized == Decimal("48") and semi.period_type == "semi_annual"


def test_individual_and_consolidated_are_never_mixed_and_no_fallback():
    rows = [obs(value=100), obs(value=900, scope="consolidated")]
    assert financials(rows).values[0].value_normalized == Decimal("100")
    assert financials(rows, data_scope="consolidated").values[0].value_normalized == Decimal("900")
    only_consolidated = [obs(value=900, scope="consolidated")]
    f = financials(only_consolidated)  # individual requested: never borrowed from consolidated
    assert f.status == "unavailable" and f.reason == "no_data_for_selection" and f.values == []


def test_rejected_is_never_a_value():
    f = financials([obs(value=999, status="rejected"), obs(value=100)])
    assert f.values[0].value_normalized == Decimal("100")
    only = financials([obs(value=999, status="rejected")], period_year=2024)
    assert only.values == [] and only.unavailable[0].reason == "rejected_only"


def test_conflict_and_needs_review_are_not_certified_values():
    conflict = financials([obs(value=100), obs(value=130)], period_year=2024)
    assert conflict.values == [] and conflict.unavailable[0].reason == "conflict"
    review = financials([obs(value=100, status="needs_review")], period_year=2024)
    assert review.values == [] and review.unavailable[0].reason == "needs_review"


def test_verified_wins():
    f = financials([obs(value=100), obs(value=120, status="verified", obs_id="v")])
    assert f.values[0].data_id == "v" and f.values[0].value_normalized == Decimal("120")


def test_explicit_year_without_data_gives_missing_not_zero():
    f = financials([obs(year=2024)], period_year=2021)
    assert f.period_year == 2021 and f.values == []
    assert all(u.reason == "missing" for u in f.unavailable)


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


def test_history_only_real_years_and_explicit_gaps():
    h = history([obs(year=2021, value=80), obs(year=2022, value=85), obs(year=2024, value=100)])
    s = h.series[0]
    assert [p.period_year for p in s.points] == [2021, 2022, 2024]  # no 2023 point
    assert s.missing_years == [2023]
    assert all(p.value != 0 for p in s.points)
    assert s.status == "partial"


def test_history_never_invents_a_future_year():
    s = history([obs(year=2022), obs(year=2023)]).series[0]
    assert max(p.period_year for p in s.points) == 2023 and s.missing_years == []


def test_history_heterogeneous_currency_is_not_drawn_as_one_series():
    s = history([obs(year=2023, currency="XOF"), obs(year=2024, currency="EUR")]).series[0]
    assert s.status == "needs_review" and s.reason == "heterogeneous_currency" and s.currency is None
    assert {p.currency for p in s.points} == {"XOF", "EUR"}  # values remain visible with their own currency


def test_history_excluded_years_carry_their_reason():
    s = history([obs(year=2023, value=90), obs(year=2024, value=10), obs(year=2024, value=20)]).series[0]
    assert [p.period_year for p in s.points] == [2023]
    assert [(u.period_year, u.reason) for u in s.excluded_years] == [(2024, "conflict")]


def test_history_respects_scope_and_period():
    rows = [obs(year=2024, value=100), obs(year=2024, value=900, scope="consolidated"),
            obs(year=2024, value=48, period_type="semi_annual")]
    assert history(rows).series[0].points[0].value == Decimal("100")
    assert history(rows, data_scope="consolidated").series[0].points[0].value == Decimal("900")
    assert history(rows, period_type="semi_annual").series[0].points[0].value == Decimal("48")


def test_history_without_data_is_unavailable():
    h = history([])
    assert h.status == "unavailable" and h.series == []


# ---------------------------------------------------------------------------
# Coverage, quality, documents
# ---------------------------------------------------------------------------


def test_coverage_defined_denominator():
    c = coverage([obs(year=2021), obs(year=2022), obs(year=2024), obs(year=2025)])
    assert (c.first_year, c.last_year) == (2021, 2025)
    assert c.available_years == [2021, 2022, 2024, 2025] and c.missing_years == [2023]
    assert (c.available_years_count, c.expected_years_count) == (4, 5)
    assert c.coverage_ratio == pytest.approx(0.8)


def test_coverage_without_data_is_unavailable_not_zero():
    c = coverage([])
    assert c.status == "unavailable" and c.coverage_ratio is None and c.expected_years_count is None


def test_coverage_ignores_rejected_and_conflicts_for_available_years():
    c = coverage([obs(year=2023), obs(year=2024, status="rejected"), obs(year=2025, value=1), obs(year=2025, value=2)])
    assert c.available_years == [2023]


def test_quality_counters_are_descriptive_without_score():
    c = coverage([obs(status="verified"), obs(metric="depots_clients", status="rejected"),
                  obs(metric="resultat_net", status="needs_review")])
    q = c.quality
    assert (q.total_observations, q.verified, q.rejected, q.needs_review) == (3, 1, 1, 1)
    dumped = c.model_dump()
    assert "overall_quality_score" not in str(dumped) and "score" not in dumped["quality"]


def test_source_documents_only_from_qualified_provenance():
    c = coverage([obs(year=2024, doc="ar-2024", page=84), obs(year=2023, doc="ar-2023", page=None),
                  obs(year=2022, doc="rej", status="rejected")])
    docs = {d.document_id: d for d in c.documents}
    assert set(docs) == {"ar-2024", "ar-2023"}  # rejected value's document is not listed
    assert docs["ar-2024"].pages == [84] and docs["ar-2023"].pages == []


def test_selection_lists_only_what_exists():
    sel = SVC.selection([obs(), obs(scope="consolidated", year=2022), obs(status="rejected", period_type="quarterly")])
    assert sel.scopes == ["consolidated", "individual"]
    assert sel.period_types == ["annual"]  # the quarterly row is rejected
    assert sel.years == [2024, 2022]


# ---------------------------------------------------------------------------
# Ratios & growth — delegated to AnalyticsService (existing rules)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ratios_and_growth_non_annual_are_unavailable():
    r = await SVC.ratios(None, "inst", period_type="semi_annual")
    g = await SVC.growth(None, "inst", period_type="quarterly")
    for res in (r, g):
        assert res.status == "unavailable" and res.reason == "period_type_not_supported" and res.items == []


@pytest.mark.asyncio
async def test_ratios_delegate_to_analytics_with_scope(monkeypatch):
    calls = {}

    async def fake_get_ratios(db, **kw):
        calls.update(kw)
        return [SimpleNamespace(value_percent=None, status="unavailable")], 1

    svc = InstitutionProfileService()
    monkeypatch.setattr(svc.analytics, "get_ratios", fake_get_ratios)
    monkeypatch.setattr("scraping.institutions.service.InstitutionRatios", lambda **kw: SimpleNamespace(**kw))
    res = await svc.ratios(None, "inst", period_year=2024, data_scope="consolidated")
    assert calls["institution_id"] == "inst" and calls["data_scope"] == "consolidated" and calls["year"] == 2024
    assert res.status == "unavailable" and res.reason == "no_computable_value"


@pytest.mark.asyncio
async def test_growth_unavailable_when_a_period_is_missing(monkeypatch):
    async def fake_get_growth(db, **kw):
        return [SimpleNamespace(growth_percent=None, status="unavailable")], 1

    svc = InstitutionProfileService()
    monkeypatch.setattr(svc.analytics, "get_growth", fake_get_growth)
    monkeypatch.setattr("scraping.institutions.service.InstitutionGrowth", lambda **kw: SimpleNamespace(**kw))
    res = await svc.growth(None, "inst", period_year=2025)
    assert res.status == "unavailable"  # never 0 % as a substitute


# ---------------------------------------------------------------------------
# Descriptive-only vocabulary
# ---------------------------------------------------------------------------

FORBIDDEN_WORDING = re.compile(
    r"\bbest\b|\bworst\b|\btop\s+(?:bank|banque)|\bleader\b|\bwinner\b|\bloser\b|\bbuy\b|\bsell\b"
    r"|recommend|recommand|\bstrongest\b|\bweakest\b|meilleure?s?\b|\bpires?\b",
    re.IGNORECASE,
)


def test_profile_code_has_no_qualitative_or_investment_wording():
    root = Path(__file__).resolve().parents[1]
    files = list((root / "scraping" / "institutions").glob("*.py"))
    hits = {}
    for f in files:
        texts = [n.value for n in ast.walk(ast.parse(f.read_text(encoding="utf-8")))
                 if isinstance(n, ast.Constant) and isinstance(n.value, str)]
        found = [m.group(0) for t in texts for m in FORBIDDEN_WORDING.finditer(t)]
        if found:
            hits[f.name] = found
    assert hits == {}


def test_forbidden_regex_really_works():
    for w in ("best bank", "la pire", "buy", "sell", "top bank", "leader", "strongest"):
        assert FORBIDDEN_WORDING.search(w), w
    for w in ("bestow", "Topic", "leadership"):
        assert not FORBIDDEN_WORDING.search(w), w


def test_default_year_shared_by_key_figures_ratios_and_growth():
    rows = [obs(year=2022), obs(year=2024), obs(year=2025, status="rejected"), obs(year=2023, scope="consolidated")]
    assert SVC.latest_qualified_year(rows, "annual", "individual") == 2024  # rejected 2025 and consolidated ignored
    assert SVC.latest_qualified_year([], "annual", "individual") is None


@pytest.mark.asyncio
async def test_ratios_and_growth_use_the_key_figures_year_by_default(monkeypatch):
    seen = {}
    svc = InstitutionProfileService()

    async def fake_obs(db, institution_id):
        return [obs(year=2023), obs(year=2024)]

    async def fake_get_ratios(db, **kw):
        seen["ratios"] = kw["year"]
        return [], 0

    async def fake_get_growth(db, **kw):
        seen["growth"] = kw["year"]
        return [], 0

    monkeypatch.setattr(svc, "observations", fake_obs)
    monkeypatch.setattr(svc.analytics, "get_ratios", fake_get_ratios)
    monkeypatch.setattr(svc.analytics, "get_growth", fake_get_growth)
    r = await svc.ratios(None, "inst")
    g = await svc.growth(None, "inst")
    assert seen == {"ratios": 2024, "growth": 2024} and r.period_year == g.period_year == 2024


@pytest.mark.asyncio
async def test_ratios_and_growth_without_data_are_unavailable(monkeypatch):
    svc = InstitutionProfileService()

    async def no_obs(db, institution_id):
        return []

    monkeypatch.setattr(svc, "observations", no_obs)
    for res in (await svc.ratios(None, "inst"), await svc.growth(None, "inst")):
        assert res.status == "unavailable" and res.reason == "no_data_for_selection" and res.items == []

