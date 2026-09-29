"""
UMOA Banking Intelligence — Phase 7 Analytics, Banking Ratios & Aggregations Tests

Validates:
  1. Banking Ratios: ROA, ROE, DEPOTS_ACTIFS, CREDITS_DEPOTS, DETTES_ACTIFS, COST_TO_INCOME
  2. Edge Cases & Invariants: Zero denominator, negative denominator, currency mismatch, missing t-1
  3. Status Hierarchy: calculated_from_verified, calculated, needs_review, unavailable
  4. Growth Calculator: Normal YoY, previous year 0, missing previous year, currency mismatch
  5. Sector & UMOA Aggregations: Zero double-counting, institutional deduplication, coverage ratio
  6. Sector Analysis & Market Share: Bank deposit and asset market shares
  7. Factual Comparisons: Institution vs institution, country vs UMOA
  8. REST API Endpoints: /definitions, /ratios, /growth, /aggregations, /sector, /compare
"""
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from scraping.analytics.aggregation import SectorAggregator
from scraping.analytics.analytics_service import AnalyticsService
from scraping.analytics.growth_calculator import GrowthCalculator
from scraping.analytics.models import SectorAggregationResult
from scraping.analytics.ratio_calculator import RatioCalculator
from scraping.analytics.sector_analysis import SectorAnalyzer
from scraping.consolidation.models import ObservationSummary


def make_obs(
    obs_id: str,
    inst_id: str,
    metric_code: str,
    year: int,
    val_norm: Decimal | None,
    doc_id: str = "doc-1",
    source_id: str = "src-bceao",
    source_name: str = "BCEAO",
    source_priority: int = 1,
    currency: str = "XOF",
    status: str = "extracted",
    period_type: str = "annual",
    verified_by: str | None = None,
) -> ObservationSummary:
    return ObservationSummary(
        id=obs_id,
        institution_id=inst_id,
        metric_code=metric_code,
        period_year=year,
        period_type=period_type,
        period_label=str(year),
        value_original=str(val_norm) if val_norm is not None else "0",
        value_normalized=val_norm,
        currency_original=currency,
        currency_normalized=currency,
        source_id=source_id,
        source_name=source_name,
        source_priority=source_priority,
        document_id=doc_id,
        status=status,
        verified_by=verified_by,
    )


# ==============================================================================
# 1. RATIO CALCULATOR TESTS
# ==============================================================================

def test_ratio_definitions_catalogue():
    """All 6 official ratios are registered with comprehensive metadata."""
    calc = RatioCalculator()
    defs = calc.get_definitions()
    assert len(defs) == 6
    codes = {d.ratio_code for d in defs}
    assert codes == {"ROA", "ROE", "DEPOTS_ACTIFS", "CREDITS_DEPOTS", "DETTES_ACTIFS", "COST_TO_INCOME"}


def test_calculate_synchronous_ratio_depots_actifs():
    """Valid calculation of DEPOTS_ACTIFS (customer deposits / total assets)."""
    calc = RatioCalculator()
    obs_depots = make_obs("o1", "inst-sgci", "depots_clients", 2024, Decimal("1600000000"), status="verified")
    obs_actifs = make_obs("o2", "inst-sgci", "total_actifs", 2024, Decimal("2000000000"), status="verified")

    res = calc.calculate_ratio("DEPOTS_ACTIFS", "inst-sgci", 2024, [obs_depots, obs_actifs])
    assert res.status == "calculated_from_verified"
    assert res.value == Decimal("0.8")
    assert res.value_percent == 80.0
    assert len(res.components) == 2


def test_calculate_synchronous_ratio_credits_depots():
    """Valid calculation of CREDITS_DEPOTS (loans / deposits)."""
    calc = RatioCalculator()
    obs_loans = make_obs("o1", "inst-ecobank", "creances_clients", 2024, Decimal("900000000"), status="reviewed")
    obs_depots = make_obs("o2", "inst-ecobank", "depots_clients", 2024, Decimal("1200000000"), status="reviewed")

    res = calc.calculate_ratio("CREDITS_DEPOTS", "inst-ecobank", 2024, [obs_loans, obs_depots])
    assert res.status == "calculated"
    assert res.value == Decimal("0.75")
    assert res.value_percent == 75.0


def test_calculate_average_ratio_roa():
    """Valid ROA calculation with 2-year average assets denominator."""
    calc = RatioCalculator()
    obs_net = make_obs("o1", "inst-boa", "resultat_net", 2024, Decimal("30000000"), status="verified")
    obs_act_2024 = make_obs("o2", "inst-boa", "total_actifs", 2024, Decimal("1100000000"), status="verified")
    obs_act_2023 = make_obs("o3", "inst-boa", "total_actifs", 2023, Decimal("900000000"), status="verified")

    # Average assets = (1.1B + 0.9B)/2 = 1.0B -> ROA = 30M / 1B = 0.03 = 3%
    res = calc.calculate_ratio("ROA", "inst-boa", 2024, [obs_net, obs_act_2024, obs_act_2023])
    assert res.status == "calculated_from_verified"
    assert res.value == Decimal("0.03")
    assert res.value_percent == 3.0
    assert len(res.components) == 3


def test_calculate_average_ratio_roe():
    """Valid ROE calculation with 2-year average equity denominator."""
    calc = RatioCalculator()
    obs_net = make_obs("o1", "inst-boa", "resultat_net", 2024, Decimal("15000000"), status="reviewed")
    obs_eq_2024 = make_obs("o2", "inst-boa", "capitaux_propres", 2024, Decimal("120000000"), status="reviewed")
    obs_eq_2023 = make_obs("o3", "inst-boa", "capitaux_propres", 2023, Decimal("80000000"), status="reviewed")

    # Average equity = (120M + 80M)/2 = 100M -> ROE = 15M / 100M = 0.15 = 15%
    res = calc.calculate_ratio("ROE", "inst-boa", 2024, [obs_net, obs_eq_2024, obs_eq_2023])
    assert res.status == "calculated"
    assert res.value == Decimal("0.15")
    assert res.value_percent == 15.0


def test_cost_to_income_unavailable_by_rule():
    """Cost-to-income is explicitly unavailable due to accounting catalogue limitation."""
    calc = RatioCalculator()
    res = calc.calculate_ratio("COST_TO_INCOME", "inst-sgci", 2024, [])
    assert res.status == "unavailable"
    assert "unsupported_accounting_component" in (res.reason or "")


def test_zero_denominator_handled():
    """Zero denominator is safely caught without ZeroDivisionError."""
    calc = RatioCalculator()
    obs_depots = make_obs("o1", "inst-x", "depots_clients", 2024, Decimal("1000000"))
    obs_actifs = make_obs("o2", "inst-x", "total_actifs", 2024, Decimal("0"))

    res = calc.calculate_ratio("DEPOTS_ACTIFS", "inst-x", 2024, [obs_depots, obs_actifs])
    assert res.status == "unavailable"
    assert "zero_denominator" in (res.reason or "")


def test_negative_equity_in_roe_flags_needs_review():
    """Negative equity signals financial distress and flags needs_review."""
    calc = RatioCalculator()
    obs_net = make_obs("o1", "inst-x", "resultat_net", 2024, Decimal("10000000"))
    obs_eq_2024 = make_obs("o2", "inst-x", "capitaux_propres", 2024, Decimal("-50000000"))
    obs_eq_2023 = make_obs("o3", "inst-x", "capitaux_propres", 2023, Decimal("-10000000"))

    res = calc.calculate_ratio("ROE", "inst-x", 2024, [obs_net, obs_eq_2024, obs_eq_2023])
    assert res.status == "needs_review"
    assert "negative_denominator" in (res.reason or "")


def test_missing_previous_year_for_roa():
    """If previous year asset is missing, ROA cannot be computed and returns unavailable."""
    calc = RatioCalculator()
    obs_net = make_obs("o1", "inst-x", "resultat_net", 2024, Decimal("10000000"))
    obs_act_2024 = make_obs("o2", "inst-x", "total_actifs", 2024, Decimal("500000000"))

    res = calc.calculate_ratio("ROA", "inst-x", 2024, [obs_net, obs_act_2024])
    assert res.status == "unavailable"
    assert "total_actifs (2023)" in (res.reason or "")


def test_currency_mismatch_blocks_ratio():
    """Incompatible currencies block the calculation without implicit conversion."""
    calc = RatioCalculator()
    obs_depots = make_obs("o1", "inst-x", "depots_clients", 2024, Decimal("1000000"), currency="EUR")
    obs_actifs = make_obs("o2", "inst-x", "total_actifs", 2024, Decimal("2000000"), currency="XOF")

    res = calc.calculate_ratio("DEPOTS_ACTIFS", "inst-x", 2024, [obs_depots, obs_actifs])
    assert res.status == "unavailable"
    assert "currency_mismatch" in (res.reason or "")


def test_component_with_needs_review_taints_ratio():
    """If a component is in needs_review, the derived ratio inherits needs_review."""
    calc = RatioCalculator()
    obs_depots = make_obs("o1", "inst-x", "depots_clients", 2024, Decimal("1000000"), status="needs_review")
    obs_actifs = make_obs("o2", "inst-x", "total_actifs", 2024, Decimal("2000000"), status="verified")

    res = calc.calculate_ratio("DEPOTS_ACTIFS", "inst-x", 2024, [obs_depots, obs_actifs])
    assert res.status == "needs_review"


# ==============================================================================
# 2. GROWTH CALCULATOR TESTS
# ==============================================================================

def test_growth_calculator_normal():
    """Standard YoY growth calculation (rate, percentage, absolute difference)."""
    gc = GrowthCalculator()
    obs_2024 = make_obs("o1", "inst-sgci", "total_actifs", 2024, Decimal("2300000000"), status="verified")
    obs_2023 = make_obs("o2", "inst-sgci", "total_actifs", 2023, Decimal("2000000000"), status="verified")

    res = gc.calculate_growth("total_actifs", "inst-sgci", 2024, [obs_2024, obs_2023])
    assert res.status == "calculated_from_verified"
    assert res.absolute_change == Decimal("300000000")
    assert res.growth_rate == 0.15
    assert res.growth_percent == 15.0


def test_growth_calculator_missing_previous_year():
    """Missing prior year returns unavailable."""
    gc = GrowthCalculator()
    obs_2024 = make_obs("o1", "inst-sgci", "total_actifs", 2024, Decimal("2300000000"))

    res = gc.calculate_growth("total_actifs", "inst-sgci", 2024, [obs_2024])
    assert res.status == "unavailable"
    assert "total_actifs (2023)" in (res.reason or "")


def test_growth_calculator_zero_base_value():
    """Prior year of zero cannot compute percentage growth."""
    gc = GrowthCalculator()
    obs_2024 = make_obs("o1", "inst-x", "resultat_net", 2024, Decimal("50000000"))
    obs_2023 = make_obs("o2", "inst-x", "resultat_net", 2023, Decimal("0"))

    res = gc.calculate_growth("resultat_net", "inst-x", 2024, [obs_2024, obs_2023])
    assert res.status == "unavailable"
    assert "zero_base_value" in (res.reason or "")


# ==============================================================================
# 3. SECTOR AGGREGATOR & DEDUPLICATION TESTS
# ==============================================================================

def test_sector_aggregator_deduplicates_sources():
    """
    CRITICAL RULE: When BCEAO and bank both publish for the same bank,
    exactly ONE authoritative value is counted in national aggregation.
    """
    agg = SectorAggregator()

    # Bank 1: SGCI has 2 observations (BCEAO priority 1 and Bank report priority 2)
    obs_sgci_bceao = make_obs("o1", "bank-sgci", "total_actifs", 2024, Decimal("1000"), source_name="BCEAO", source_priority=1)
    obs_sgci_bank = make_obs("o2", "bank-sgci", "total_actifs", 2024, Decimal("1000"), source_name="SGCI", source_priority=2)

    # Bank 2: Ecobank has 1 observation
    obs_eco = make_obs("o3", "bank-eco", "total_actifs", 2024, Decimal("800"), source_name="BCEAO", source_priority=1)

    all_obs = [obs_sgci_bceao, obs_sgci_bank, obs_eco]
    res = agg.aggregate_country(
        country_code="CI",
        year=2024,
        metric_code="total_actifs",
        observations=all_obs,
        total_institutions_in_country=2,
    )

    # Sum should be exactly 1000 + 800 = 1800, NOT 2800!
    assert res.total_value == Decimal("1800")
    assert res.institution_count == 2
    assert res.coverage_ratio == 1.0
    assert not res.is_partial
    assert res.status == "calculated"


def test_sector_aggregator_partial_coverage():
    """Partial coverage is explicitly flagged when some banks are missing."""
    agg = SectorAggregator()
    obs_sgci = make_obs("o1", "bank-sgci", "total_actifs", 2024, Decimal("1000"))

    res = agg.aggregate_country(
        country_code="CI",
        year=2024,
        metric_code="total_actifs",
        observations=[obs_sgci],
        total_institutions_in_country=5,  # 5 banks exist in CI, only 1 provided data
    )

    assert res.total_value == Decimal("1000")
    assert res.institution_count == 1
    assert res.total_institutions == 5
    assert res.coverage_ratio == 0.2
    assert res.is_partial
    assert res.status == "partial"


def test_umoa_regional_aggregation():
    """UMOA regional aggregate correctly combines country totals."""
    agg = SectorAggregator()

    ci_agg = SectorAggregationResult(
        scope="country",
        country_code="CI",
        year=2024,
        metric_code="total_actifs",
        total_value=Decimal("15000000000"),
        institution_count=25,
        total_institutions=28,
        coverage_ratio=0.8929,
        is_partial=True,
        status="partial",
        contributing_institutions=[f"ci-bank-{i}" for i in range(25)],
    )
    sn_agg = SectorAggregationResult(
        scope="country",
        country_code="SN",
        year=2024,
        metric_code="total_actifs",
        total_value=Decimal("10000000000"),
        institution_count=20,
        total_institutions=22,
        coverage_ratio=0.9091,
        is_partial=True,
        status="partial",
        contributing_institutions=[f"sn-bank-{i}" for i in range(20)],
    )

    umoa_res = agg.aggregate_umoa(
        year=2024,
        metric_code="total_actifs",
        country_aggregations=[ci_agg, sn_agg],
        total_institutions_umoa=120,
    )

    assert umoa_res.scope == "umoa"
    assert umoa_res.total_value == Decimal("25000000000")
    assert umoa_res.institution_count == 45
    assert umoa_res.total_institutions == 120
    assert umoa_res.is_partial  # 45/120 and only 2/8 countries represented


# ==============================================================================
# 4. SECTOR ANALYSIS & MARKET SHARES TESTS
# ==============================================================================

def test_market_share_calculation():
    """Accurate market share calculation within national banking sector."""
    analyzer = SectorAnalyzer()
    sector_agg = SectorAggregationResult(
        scope="country",
        country_code="CI",
        year=2024,
        metric_code="depots_clients",
        total_value=Decimal("5000000000"),
        institution_count=10,
        total_institutions=10,
        coverage_ratio=1.0,
        is_partial=False,
        status="calculated",
    )

    res = analyzer.calculate_market_share(
        institution_id="inst-sgci",
        institution_value=Decimal("1000000000"),
        sector_aggregation=sector_agg,
        institution_name="SGCI",
    )

    assert res.market_share == 0.2
    assert res.market_share_percent == 20.0
    assert res.status == "calculated"


def test_compare_institutions_factual():
    """Factual comparison between two institutions without subjective rankings."""
    analyzer = SectorAnalyzer()
    res = analyzer.compare_institutions(
        inst_a_name="SGCI",
        val_a=15.0,
        inst_b_name="Ecobank",
        val_b=12.0,
        metric_or_ratio="ROE",
        year=2024,
        unit="%",
    )

    assert res.comparison_type == "institution_vs_institution"
    assert res.difference == 3.0
    assert res.ratio_a_to_b == 1.25


# ==============================================================================
# 5. REST API ENDPOINTS INTEGRATION TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_api_analytics_definitions():
    """GET /api/v1/analytics/definitions returns catalogue of ratios."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/analytics/definitions")
        assert res.status_code == 200
        data = res.json()
        assert isinstance(data, list)
        assert len(data) == 6
        codes = {d["ratio_code"] for d in data}
        assert "ROA" in codes
        assert "ROE" in codes
        assert "DEPOTS_ACTIFS" in codes


@pytest.mark.asyncio
async def test_api_analytics_ratios(monkeypatch):
    """GET /api/v1/analytics/ratios returns paginated ratio calculations."""
    calc_res = RatioCalculator().calculate_ratio(
        "DEPOTS_ACTIFS",
        "inst-1",
        2024,
        [
            make_obs("o1", "inst-1", "depots_clients", 2024, Decimal("800")),
            make_obs("o2", "inst-1", "total_actifs", 2024, Decimal("1000")),
        ],
    )

    async def mock_get_ratios(self, db, **kwargs):
        return [calc_res], 1

    monkeypatch.setattr(AnalyticsService, "get_ratios", mock_get_ratios)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/analytics/ratios?institution_id=inst-1&ratio_code=DEPOTS_ACTIFS")
        assert res.status_code == 200
        payload = res.json()
        assert payload["total"] == 1
        assert len(payload["items"]) == 1
        item = payload["items"][0]
        assert item["ratio_code"] == "DEPOTS_ACTIFS"
        assert item["value_percent"] == 80.0


@pytest.mark.asyncio
async def test_api_analytics_growth(monkeypatch):
    """GET /api/v1/analytics/growth returns YoY variations."""
    growth_res = GrowthCalculator().calculate_growth(
        "total_actifs",
        "inst-1",
        2024,
        [
            make_obs("o1", "inst-1", "total_actifs", 2024, Decimal("1200")),
            make_obs("o2", "inst-1", "total_actifs", 2023, Decimal("1000")),
        ],
    )

    async def mock_get_growth(self, db, **kwargs):
        return [growth_res], 1

    monkeypatch.setattr(AnalyticsService, "get_growth", mock_get_growth)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/analytics/growth?institution_id=inst-1&year=2024")
        assert res.status_code == 200
        payload = res.json()
        assert payload["total"] == 1
        item = payload["items"][0]
        assert item["growth_percent"] == 20.0
        assert item["absolute_change"] == "200"


@pytest.mark.asyncio
async def test_api_analytics_aggregations(monkeypatch):
    """GET /api/v1/analytics/aggregations returns country or regional totals."""
    agg_res = SectorAggregationResult(
        scope="country",
        country_code="CI",
        year=2024,
        metric_code="total_actifs",
        total_value=Decimal("15000000000"),
        institution_count=25,
        total_institutions=28,
        coverage_ratio=0.8929,
        is_partial=True,
        status="partial",
        contributing_institutions=["bank-1"],
    )

    async def mock_get_aggregations(self, db, **kwargs):
        return [agg_res]

    monkeypatch.setattr(AnalyticsService, "get_aggregations", mock_get_aggregations)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/analytics/aggregations?year=2024&country_code=CI")
        assert res.status_code == 200
        payload = res.json()
        assert len(payload) == 1
        assert payload[0]["country_code"] == "CI"
        assert payload[0]["total_value"] == "15000000000"


@pytest.mark.asyncio
async def test_api_analytics_sector(monkeypatch):
    """GET /api/v1/analytics/sector returns sector structure and market shares."""
    agg_res = SectorAggregationResult(
        scope="country",
        country_code="CI",
        year=2024,
        metric_code="depots_clients",
        total_value=Decimal("5000000000"),
        institution_count=2,
        total_institutions=2,
        coverage_ratio=1.0,
        is_partial=False,
        status="calculated",
        contributing_institutions=["bank-1", "bank-2"],
    )
    ms = SectorAnalyzer().calculate_market_share("bank-1", Decimal("2000000000"), agg_res, "Bank One")

    async def mock_get_sector_structure(self, db, **kwargs):
        return agg_res, [ms]

    monkeypatch.setattr(AnalyticsService, "get_sector_structure", mock_get_sector_structure)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get("/api/v1/analytics/sector?country_code=CI&year=2024")
        assert res.status_code == 200
        payload = res.json()
        assert payload["aggregation"]["total_value"] == "5000000000"
        assert len(payload["market_shares"]) == 1
        assert payload["market_shares"][0]["market_share_percent"] == 40.0


@pytest.mark.asyncio
async def test_api_analytics_compare(monkeypatch):
    """GET /api/v1/analytics/compare performs factual entity comparison."""
    comp = SectorAnalyzer().compare_institutions("Bank A", 10.0, "Bank B", 8.0, "ROA", 2024, "%")

    async def mock_compare_entities(self, db, **kwargs):
        return comp

    monkeypatch.setattr(AnalyticsService, "compare_entities", mock_compare_entities)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(
            "/api/v1/analytics/compare?comparison_type=institution_vs_institution&entity_a=a&entity_b=b&metric_or_ratio=ROA&year=2024"
        )
        assert res.status_code == 200
        payload = res.json()
        assert payload["difference"] == 2.0
        assert payload["ratio_a_to_b"] == 1.25
