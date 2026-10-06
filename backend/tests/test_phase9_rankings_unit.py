"""
Phase 9 — Descriptive rankings: unit tests (no database).

Covers the pure ranking rules and RankingService.rank / compare logic with the
database accessors replaced: ties, missing values, rejected, conflict,
needs_review, heterogeneous currencies, zero coverage, scope / period rules,
pagination independence and absence of any default year.
"""
import ast
import re
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from scraping.analytics.eligibility import EligibilityEngine
from scraping.consolidation.models import ObservationSummary
from scraping.rankings.calculator import competition_ranks, compute_coverage, paginate
from scraping.rankings.definitions import RANKABLE_INDICATORS, get_indicator
from scraping.rankings.eligibility import qualify_derived, qualify_metric
from scraping.rankings.models import Candidate
from scraping.rankings.service import RankingService
from scraping.rankings.universe import UniverseResolution

ENGINE = EligibilityEngine()


def obs(value, status="extracted", currency="XOF", obs_id=None, scope="individual", period_type="annual"):
    return ObservationSummary(
        id=obs_id or f"fd-{value}-{status}",
        institution_id="i1",
        metric_code="total_actifs",
        source_id="src",
        document_id="doc",
        document_title="Rapport",
        period_year=2023,
        period_type=period_type,
        scope=scope,
        value_original=str(value),
        value_normalized=None if value is None else Decimal(str(value)),
        currency_normalized=currency,
        page_number=4,
        status=status,
    )


# ---------------------------------------------------------------------------
# Pure calculator
# ---------------------------------------------------------------------------


def _rank(values):
    items = [SimpleNamespace(id=k, name=k, v=Decimal(str(v))) for k, v in values]
    return [(r, it.id) for r, it in competition_ranks(items, value=lambda x: x.v, name=lambda x: x.name,
                                                       ident=lambda x: x.id)]


def test_tie_ranking_is_competition_style():
    assert _rank([("C", 90), ("B", 100), ("A", 100)]) == [(1, "A"), (1, "B"), (3, "C")]


def test_tie_order_is_deterministic_and_never_changes_rank():
    first = _rank([("B", 100), ("A", 100), ("C", 100)])
    second = _rank([("C", 100), ("A", 100), ("B", 100)])
    assert first == second == [(1, "A"), (1, "B"), (1, "C")]


def test_ascending_order():
    items = [SimpleNamespace(id=k, name=k, v=Decimal(v)) for k, v in (("A", "3"), ("B", "1"), ("C", "1"))]
    ranked = competition_ranks(items, value=lambda x: x.v, name=lambda x: x.name, ident=lambda x: x.id,
                               descending=False)
    assert [(r, it.id) for r, it in ranked] == [(1, "B"), (1, "C"), (3, "A")]


def test_coverage_zero_expected_is_unknown():
    cov = compute_coverage(0, 0)
    assert cov.coverage_ratio is None and cov.expected_count == 0 and cov.coverage_status == "unavailable"


def test_coverage_unavailable_keeps_real_eligible_count():
    cov = compute_coverage(8, 10, available=False)
    assert (cov.eligible_count, cov.ranked_count, cov.coverage_ratio, cov.coverage_status) == (8, 0, None, "unavailable")


def test_coverage_real_ratio():
    assert compute_coverage(8, 10).coverage_ratio == 0.8
    assert compute_coverage(8, 10).ranked_count == 8
    # Zero admissible values is a real fact (not a blocked ranking): 0 % is correct here.
    assert compute_coverage(0, 4).coverage_ratio == 0.0
    assert compute_coverage(0, 4).coverage_status == "available"


def test_pagination_never_changes_ranks():
    ranked = list(range(1, 26))
    page2, has_next, has_prev = paginate(ranked, 2, 10)
    assert page2 == list(range(11, 21)) and has_next and has_prev


# ---------------------------------------------------------------------------
# Eligibility (existing rules reused)
# ---------------------------------------------------------------------------


def test_missing_value_is_not_eligible():
    c = qualify_metric("i1", [], ENGINE)
    assert not c.eligible and c.reason == "missing" and c.value is None


def test_rejected_only_is_not_eligible():
    c = qualify_metric("i1", [obs(999, status="rejected")], ENGINE)
    assert not c.eligible and c.reason == "rejected_only"


def test_rejected_never_wins():
    c = qualify_metric("i1", [obs(999, status="rejected"), obs(100)], ENGINE)
    assert c.eligible and c.value == Decimal("100")


def test_conflict_is_needs_review_not_ranked():
    c = qualify_metric("i1", [obs(100, obs_id="a"), obs(130, obs_id="b")], ENGINE)
    assert not c.eligible and c.status == "needs_review" and c.reason == "conflict"


def test_needs_review_is_excluded():
    c = qualify_metric("i1", [obs(100, status="needs_review")], ENGINE)
    assert not c.eligible and c.reason == "needs_review"


def test_verified_wins_and_keeps_provenance():
    c = qualify_metric("i1", [obs(100), obs(120, status="verified", obs_id="v")], ENGINE)
    assert c.eligible and c.value == Decimal("120") and c.data_id == "v"
    assert c.provenance[0].page_number == 4 and c.provenance[0].scope == "individual"


def test_derived_only_calculated_statuses_are_eligible():
    ok = SimpleNamespace(institution_id="i1", value_percent=12.5, status="calculated", components=[], reason=None)
    review = SimpleNamespace(institution_id="i1", value_percent=12.5, status="needs_review", components=[],
                             reason="conflict")
    missing = SimpleNamespace(institution_id="i1", value_percent=None, status="unavailable", components=[],
                              reason="Missing required component(s)")
    assert qualify_derived(ok, "value_percent").eligible
    assert not qualify_derived(review, "value_percent").eligible
    m = qualify_derived(missing, "value_percent")
    assert not m.eligible and m.value is None and m.detail.startswith("Missing")


def test_rankable_catalogue():
    assert {"total_actifs", "growth_pnb", "ROA", "COST_TO_INCOME"} <= set(RANKABLE_INDICATORS)
    assert get_indicator("growth_pnb").base_metric == "produit_net_bancaire"
    assert get_indicator("roa").kind == "ratio"
    assert get_indicator("unknown") is None


# ---------------------------------------------------------------------------
# RankingService with database accessors replaced
# ---------------------------------------------------------------------------


def inst(i, name, code="CI"):
    return (SimpleNamespace(id=i, name_official=name), code)


def service(universe, years, cands):
    svc = RankingService()

    async def fake_universe(db, country_code):
        return universe

    async def fake_resolution(db, country_code):
        return UniverseResolution(members=universe, source="institutions_table")

    async def fake_years(db, indicator, period_type, data_scope, ids):
        return years

    async def fake_candidates(db, indicator, year, period_type, data_scope, ids):
        return {i: cands.get(i) or Candidate(institution_id=i, eligible=False, status="unavailable", reason="missing")
                for i in ids}

    svc.universe, svc.available_years, svc.candidates = fake_universe, fake_years, fake_candidates
    svc.universe_resolution = fake_resolution
    return svc


def ok(i, v, currency="XOF"):
    return Candidate(institution_id=i, eligible=True, value=Decimal(v), currency=currency, status="verified")


@pytest.mark.asyncio
async def test_rank_missing_never_ranked_nor_last():
    svc = service([inst("a", "A"), inst("b", "B"), inst("c", "C")], [2023], {"a": ok("a", "10"), "b": ok("b", "5")})
    r = await svc.rank(None, get_indicator("total_actifs"))
    assert [(e.rank, e.institution_id) for e in r.items] == [(1, "a"), (2, "b")]
    assert [u.institution_id for u in r.unavailable] == ["c"]
    assert r.coverage.eligible_count == 2 and r.coverage.expected_count == 3


@pytest.mark.asyncio
async def test_rank_heterogeneous_currency_blocks_ranking():
    svc = service([inst("a", "A"), inst("b", "B")], [2023], {"a": ok("a", "10"), "b": ok("b", "5", "EUR")})
    r = await svc.rank(None, get_indicator("total_actifs"))
    assert r.status == "needs_review" and r.reason == "heterogeneous_currency" and r.items == []


@pytest.mark.asyncio
async def test_rank_heterogeneous_currency_coverage_is_unavailable_not_zero():
    """8 eligible institutions, XOF + EUR: eligible 8, ranked 0, coverage None — never 0/8."""
    universe = [inst(f"i{n}", f"Bank {n}") for n in range(8)]
    cands = {f"i{n}": ok(f"i{n}", str(100 + n), "XOF" if n < 5 else "EUR") for n in range(8)}
    r = await service(universe, [2023], cands).rank(None, get_indicator("total_actifs"))
    assert r.reason == "heterogeneous_currency" and r.total_ranked == 0
    c = r.coverage
    assert (c.eligible_count, c.ranked_count, c.expected_count) == (8, 0, 8)
    assert c.coverage_ratio is None and c.coverage_status == "unavailable"


@pytest.mark.asyncio
async def test_rank_normal_ranked_count_matches_entries():
    svc = service([inst("a", "A"), inst("b", "B"), inst("c", "C")], [2023], {"a": ok("a", "10"), "b": ok("b", "5")})
    r = await svc.rank(None, get_indicator("total_actifs"))
    assert r.coverage.ranked_count == r.total_ranked == 2 and r.coverage.coverage_ratio == pytest.approx(0.6667)


@pytest.mark.asyncio
async def test_rank_ratio_currency_not_checked():
    svc = service([inst("a", "A"), inst("b", "B")], [2023], {"a": ok("a", "10", None), "b": ok("b", "5", None)})
    r = await svc.rank(None, get_indicator("DEPOTS_ACTIFS"))
    assert r.status == "calculated" and len(r.items) == 2 and r.items[0].unit == "%"


@pytest.mark.asyncio
async def test_rank_empty_universe_coverage_unknown():
    svc = service([], [], {})
    r = await svc.rank(None, get_indicator("total_actifs"), country_code="GW")
    assert r.status == "unavailable" and r.coverage.coverage_ratio is None and r.coverage.expected_count == 0


@pytest.mark.asyncio
async def test_rank_no_default_year():
    svc = service([inst("a", "A")], [], {"a": ok("a", "10")})
    r = await svc.rank(None, get_indicator("total_actifs"))
    assert r.period_year is None and r.reason == "no_period"


@pytest.mark.asyncio
async def test_rank_uses_latest_available_year_or_explicit_year():
    svc = service([inst("a", "A")], [2023, 2021], {"a": ok("a", "10")})
    assert (await svc.rank(None, get_indicator("total_actifs"))).period_year == 2023
    assert (await svc.rank(None, get_indicator("total_actifs"), period_year=2021)).period_year == 2021


@pytest.mark.asyncio
async def test_rank_ratio_or_growth_non_annual_is_unavailable():
    svc = service([inst("a", "A")], [2023], {"a": ok("a", "10")})
    for code in ("ROA", "growth_total_actifs"):
        r = await svc.rank(None, get_indicator(code), period_type="semi_annual")
        assert r.status == "unavailable" and r.reason == "period_type_not_supported" and r.items == []
        assert r.coverage.coverage_ratio is None and r.coverage.coverage_status == "unavailable"


@pytest.mark.asyncio
async def test_sector_and_country_comparisons_not_supported_for_ratio_and_growth():
    """No aggregation method is invented for ratios / growth: unavailable, no SQL query at all."""

    class NoDb:
        async def execute(self, *a, **k):  # pragma: no cover - must never be called
            raise AssertionError("no query expected")

    svc = RankingService()
    institution = SimpleNamespace(id="a", name_official="A")
    for code in ("ROA", "DEPOTS_ACTIFS", "growth_total_actifs"):
        country = await svc.country_vs_umoa(NoDb(), get_indicator(code), "CI")
        sector = await svc.institution_vs_sector(NoDb(), get_indicator(code), institution, "CI")
        for res in (country, sector):
            assert res.status == "unavailable" and res.reason == "aggregate_not_supported"
            assert res.share_percent is None
        assert country.country_total is None and country.umoa_total is None
        assert sector.sector_total is None


@pytest.mark.asyncio
async def test_rank_single_scope_and_period_reported():
    svc = service([inst("a", "A")], [2023], {"a": ok("a", "10")})
    r = await svc.rank(None, get_indicator("total_actifs"), data_scope="consolidated", period_type="semi_annual")
    assert r.data_scope == "consolidated" and r.period_type == "semi_annual"
    assert all(e.data_scope == "consolidated" and e.period_type == "semi_annual" for e in r.items)


@pytest.mark.asyncio
async def test_rank_pages_keep_global_ranks():
    universe = [inst(f"i{n:02d}", f"Bank {n:02d}") for n in range(12)]
    cands = {f"i{n:02d}": ok(f"i{n:02d}", str(100 - n)) for n in range(12)}
    svc = service(universe, [2023], cands)
    p2 = await svc.rank(None, get_indicator("total_actifs"), page=2, page_size=5)
    assert [e.rank for e in p2.items] == [6, 7, 8, 9, 10] and p2.total_ranked == 12


@pytest.mark.asyncio
async def test_compare_heterogeneous_currency_hides_values():
    svc = service([], [2023], {"a": ok("a", "10"), "b": ok("b", "5", "EUR")})
    r = await svc.compare_institutions(None, get_indicator("total_actifs"), [inst("a", "A"), inst("b", "B")])
    assert r.status == "needs_review" and all(row.value is None for row in r.rows)


@pytest.mark.asyncio
async def test_compare_missing_institution_value_is_none_not_zero():
    svc = service([], [2023], {"a": ok("a", "10")})
    r = await svc.compare_institutions(None, get_indicator("total_actifs"), [inst("a", "A"), inst("b", "B")])
    assert r.status == "partial"
    b = next(row for row in r.rows if row.institution_id == "b")
    assert b.value is None and b.reason == "missing"


# ---------------------------------------------------------------------------
# Descriptive-only vocabulary
# ---------------------------------------------------------------------------

FORBIDDEN_WORDING = re.compile(
    r"meilleure?s?\b|\bpires?\b|\bbest\b|\bworst\b|\btop\s+(?:bank|banque)|recommand|recommend|\bbuy\b|\bsell\b"
    r"|credit score|score de cr[ée]dit|safest|la plus s[ûu]re|most profitable|la plus rentable",
    re.IGNORECASE,
)


def _text_literals(path: Path) -> list[str]:
    """String literals and docstrings only: identifiers (e.g. `best` in the reused
    select_authoritative_observation contract) are code, not wording."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def test_rankings_code_has_no_qualitative_or_investment_wording():
    root = Path(__file__).resolve().parents[1]
    files = list((root / "scraping" / "rankings").glob("*.py")) + [
        root / "app" / "api" / "v1" / "rankings.py",
        root / "app" / "api" / "v1" / "comparisons.py",
    ]
    hits = {
        f.name: [m.group(0) for text in _text_literals(f) for m in FORBIDDEN_WORDING.finditer(text)] for f in files
    }
    assert {k: v for k, v in hits.items() if v} == {}
