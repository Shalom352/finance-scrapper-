"""
UMOA Banking Intelligence — Phase 6 Consolidation, Historical Analysis & Data Quality Tests

Validates:
  - Duplicate Detection: identical, multi-source, potential
  - Conflict Detection: conflicting values, currencies, periods, conflict_with_verified
  - Invariant: Verified records are protected from automatic overwrite
  - Historical Series Analysis: missing years, series gaps, extreme variations, unit changes,
    currency shifts, negative guardrails, repeating identical values
  - Institutional Coverage: depth, missing periods, ratio calculation
  - Explainable Data Quality Scorecard: 8 dimensions and composite score
  - REST API Endpoints: /duplicates, /conflicts, /coverage, /historical-quality
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.country import Country
from app.models.document import Document
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.source import Source
from scraping.consolidation.conflict_detector import ConflictDetector
from scraping.consolidation.consolidator import FinancialDataConsolidator
from scraping.consolidation.coverage_analyzer import CoverageAnalyzer
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.historical_analyzer import HistoricalAnalyzer
from scraping.consolidation.models import ObservationSummary
from scraping.consolidation.quality_analyzer import DataQualityAnalyzer

# ==============================================================================
# 1. FIXTURES & HELPERS
# ==============================================================================

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
    period_label: str | None = None,
    verified_by: str | None = None,
) -> ObservationSummary:
    return ObservationSummary(
        id=obs_id,
        institution_id=inst_id,
        metric_code=metric_code,
        period_year=year,
        period_type=period_type,
        period_label=period_label or str(year),
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
# 2. DUPLICATE DETECTOR TESTS
# ==============================================================================

def test_duplicate_detector_identical():
    """Identical observations in the same document are flagged duplicate_identical."""
    detector = DuplicateDetector()
    obs1 = make_obs("o1", "inst-sgci", "TOTAL_ASSETS", 2024, Decimal("1500000000"), doc_id="doc-1")
    obs2 = make_obs("o2", "inst-sgci", "TOTAL_ASSETS", 2024, Decimal("1500000000"), doc_id="doc-1")

    dups = detector.detect_duplicates([obs1, obs2])
    assert len(dups) == 1
    assert dups[0].duplicate_type == "duplicate_identical"
    assert dups[0].count == 2
    assert dups[0].institution_id == "inst-sgci"
    assert dups[0].metric_code == "TOTAL_ASSETS"


def test_duplicate_detector_different_sources():
    """Identical values across different publications are flagged duplicate_different_source."""
    detector = DuplicateDetector()
    obs_bceao = make_obs("o1", "inst-sgci", "NET_INCOME", 2023, Decimal("25000000"), doc_id="doc-bceao-2023", source_name="BCEAO")
    obs_annual = make_obs("o2", "inst-sgci", "NET_INCOME", 2023, Decimal("25000000"), doc_id="doc-annual-report", source_name="SGCI")

    dups = detector.detect_duplicates([obs_bceao, obs_annual])
    assert len(dups) == 1
    assert dups[0].duplicate_type == "duplicate_different_source"
    assert dups[0].count == 2
    docs = {o.document_id for o in dups[0].observations}
    assert docs == {"doc-bceao-2023", "doc-annual-report"}


def test_duplicate_detector_ignores_singletons():
    """Non-duplicate distinct year observations are not grouped."""
    detector = DuplicateDetector()
    obs1 = make_obs("o1", "inst-sgci", "TOTAL_ASSETS", 2023, Decimal("1400000000"))
    obs2 = make_obs("o2", "inst-sgci", "TOTAL_ASSETS", 2024, Decimal("1500000000"))

    dups = detector.detect_duplicates([obs1, obs2])
    assert len(dups) == 0


# ==============================================================================
# 3. CONFLICT DETECTOR & SOURCE PRIORITY TESTS
# ==============================================================================

def test_conflict_detector_value_contradiction():
    """Conflicting normalized values for same logical key are detected."""
    detector = ConflictDetector()
    obs_bceao = make_obs(
        "o1", "inst-baci", "NET_INCOME", 2024, Decimal("12000000"),
        source_id="src-bceao", source_name="BCEAO", source_priority=1,
    )
    obs_press = make_obs(
        "o2", "inst-baci", "NET_INCOME", 2024, Decimal("15000000"),
        source_id="src-press", source_name="Financial Press", source_priority=3,
    )

    conflicts = detector.detect_conflicts([obs_bceao, obs_press])
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "conflicting_values"
    assert c.requires_human_review is True
    # Priority 1 (BCEAO) should be recommended
    assert "12000000" in (c.proposed_resolution or "")
    assert "BCEAO" in c.recommendation_reason


def test_conflict_detector_currency_conflict():
    """Heterogeneous currencies for the same observation key trigger conflicting_currency."""
    detector = ConflictDetector()
    obs1 = make_obs("o1", "inst-baci", "TOTAL_ASSETS", 2023, Decimal("500000000"), currency="XOF")
    obs2 = make_obs("o2", "inst-baci", "TOTAL_ASSETS", 2023, Decimal("500000000"), currency="EUR")

    conflicts = detector.detect_conflicts([obs1, obs2])
    assert len(conflicts) == 1
    assert conflicts[0].conflict_type == "conflicting_currency"


def test_conflict_detector_protects_verified_records():
    """Verified observations in conflict MUST NOT be overwritten and trigger conflict_with_verified."""
    detector = ConflictDetector()
    obs_verified = make_obs(
        "o-verif", "inst-sgci", "EQUITY", 2023, Decimal("80000000"),
        status="verified", verified_by="analyst_auditor@umoa.org",
    )
    obs_new = make_obs(
        "o-new", "inst-sgci", "EQUITY", 2023, Decimal("95000000"),
        status="extracted",
    )

    conflicts = detector.detect_conflicts([obs_verified, obs_new])
    assert len(conflicts) == 1
    c = conflicts[0]
    assert c.conflict_type == "conflict_with_verified"
    assert c.has_verified_observation is True
    assert "Retain verified value 80000000" in (c.proposed_resolution or "")
    assert "protected" in c.recommendation_reason


# ==============================================================================
# 4. HISTORICAL ANALYZER TESTS
# ==============================================================================

def test_historical_analyzer_complete_series():
    """Continuous series from 2020 to 2024 has no rupture and no missing years."""
    analyzer = HistoricalAnalyzer()
    obs = [
        make_obs(f"o{y}", "inst-ecob-ci", "TOTAL_ASSETS", y, Decimal(f"{y * 1000000}"))
        for y in range(2020, 2025)
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    s = series[0]
    assert s.first_year == 2020
    assert s.last_year == 2024
    assert s.available_years == [2020, 2021, 2022, 2023, 2024]
    assert s.missing_years == []
    assert s.consecutive_years_count == 5
    assert s.has_rupture is False


def test_historical_analyzer_detects_missing_periods():
    """Time series gap signals missing_years without interpolation."""
    analyzer = HistoricalAnalyzer()
    # Missing 2022 and 2024
    obs = [
        make_obs("o1", "inst-ecob-ci", "NET_INCOME", 2020, Decimal("1000")),
        make_obs("o2", "inst-ecob-ci", "NET_INCOME", 2021, Decimal("1200")),
        make_obs("o3", "inst-ecob-ci", "NET_INCOME", 2023, Decimal("1500")),
        make_obs("o4", "inst-ecob-ci", "NET_INCOME", 2025, Decimal("1800")),
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    s = series[0]
    assert s.first_year == 2020
    assert s.last_year == 2025
    assert s.available_years == [2020, 2021, 2023, 2025]
    assert s.missing_years == [2022, 2024]
    assert s.has_rupture is True
    # Gap anomalies reported
    gap_anomalies = [a for a in s.anomalies if a.anomaly_type == "series_gap"]
    assert len(gap_anomalies) == 2


def test_historical_analyzer_detects_extreme_variation():
    """Year-to-year variation > 300% is flagged as historical_anomaly without data deletion."""
    analyzer = HistoricalAnalyzer(extreme_variation_threshold=3.0)
    obs = [
        make_obs("o1", "inst-cbi-bf", "NET_INCOME", 2023, Decimal("10000000")),
        make_obs("o2", "inst-cbi-bf", "NET_INCOME", 2024, Decimal("50000000")),  # +400% jump
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    anomalies = series[0].anomalies
    var_anom = next((a for a in anomalies if a.anomaly_type == "extreme_variation"), None)
    assert var_anom is not None
    assert var_anom.year == 2024
    assert var_anom.variation_pct == 400.0
    assert var_anom.severity == "warning"


def test_historical_analyzer_detects_sudden_unit_change():
    """Unscaled transition (e.g. 1000x jump) is detected as sudden_unit_change."""
    analyzer = HistoricalAnalyzer()
    obs = [
        make_obs("o1", "inst-cbi-bf", "TOTAL_ASSETS", 2023, Decimal("500000")),  # in thousands
        make_obs("o2", "inst-cbi-bf", "TOTAL_ASSETS", 2024, Decimal("500000000")),  # in units (1000x)
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    unit_anom = next((a for a in series[0].anomalies if a.anomaly_type == "sudden_unit_change"), None)
    assert unit_anom is not None
    assert unit_anom.year == 2024
    assert unit_anom.severity == "flag"


def test_historical_analyzer_negative_guardrail():
    """Negative values on strictly non-negative balance sheet assets trigger negative_guardrail_breach."""
    analyzer = HistoricalAnalyzer()
    obs = [
        make_obs("o1", "inst-cbi-bf", "TOTAL_ASSETS", 2024, Decimal("-500000")),
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    guardrail_anom = next((a for a in series[0].anomalies if a.anomaly_type == "negative_guardrail_breach"), None)
    assert guardrail_anom is not None
    assert guardrail_anom.severity == "flag"


def test_historical_analyzer_repeating_identical_values():
    """Identical non-zero values over 3 consecutive exercises are flagged."""
    analyzer = HistoricalAnalyzer()
    obs = [
        make_obs("o1", "inst-boa-sn", "NET_INCOME", 2021, Decimal("12500000")),
        make_obs("o2", "inst-boa-sn", "NET_INCOME", 2022, Decimal("12500000")),
        make_obs("o3", "inst-boa-sn", "NET_INCOME", 2023, Decimal("12500000")),
    ]

    series = analyzer.analyze_series(obs)
    assert len(series) == 1
    repeat_anom = next((a for a in series[0].anomalies if a.anomaly_type == "repeating_identical_values"), None)
    assert repeat_anom is not None
    assert repeat_anom.year == 2023


# ==============================================================================
# 5. COVERAGE ANALYZER TESTS
# ==============================================================================

def test_coverage_analyzer_computes_exact_ratios():
    """Coverage analyzer calculates coverage_ratio, available metrics, and documents count."""
    analyzer = CoverageAnalyzer()
    obs = [
        make_obs("o1", "inst-sgci", "TOTAL_ASSETS", 2020, Decimal("100"), doc_id="d1"),
        make_obs("o2", "inst-sgci", "TOTAL_ASSETS", 2021, Decimal("110"), doc_id="d1"),
        make_obs("o3", "inst-sgci", "TOTAL_ASSETS", 2022, Decimal("120"), doc_id="d2"),
        make_obs("o4", "inst-sgci", "NET_INCOME", 2024, Decimal("15"), doc_id="d2"),  # 2023 missing
    ]

    meta = {"inst-sgci": {"name": "Société Générale CI", "country": "CI"}}
    cov = analyzer.analyze_coverage(obs, institution_meta=meta)

    assert len(cov) == 1
    c = cov[0]
    assert c.institution_id == "inst-sgci"
    assert c.institution_name == "Société Générale CI"
    assert c.country_code == "CI"
    assert c.first_year == 2020
    assert c.last_year == 2024
    assert c.available_years == [2020, 2021, 2022, 2024]
    assert c.missing_years == [2023]
    # 4 observed years out of 5 expected years (2020..2024) -> 4/5 = 0.80
    assert c.coverage_ratio == 0.8
    assert c.metrics_available_count == 2  # TOTAL_ASSETS, NET_INCOME
    assert c.documents_available_count == 2  # d1, d2
    assert c.data_points_count == 4


# ==============================================================================
# 6. DATA QUALITY ANALYZER TESTS
# ==============================================================================

def test_quality_analyzer_dimensions_and_composite_score():
    """Quality analyzer evaluates 8 explainable dimensions and calculates composite score."""
    analyzer = DataQualityAnalyzer()
    obs = [
        make_obs("o1", "inst-1", "TOTAL_ASSETS", 2023, Decimal("100"), status="verified", verified_by="auditor@umoa.org"),
        make_obs("o2", "inst-1", "TOTAL_ASSETS", 2024, Decimal("120"), status="reviewed"),
    ]

    report = analyzer.generate_report(obs)
    assert report.total_points == 2
    assert report.verified_count == 1
    assert report.reviewed_count == 1
    assert report.conflicts_count == 0
    assert report.potential_duplicates_count == 0
    assert len(report.quality_dimensions) == 8

    # Check each dimension is present
    dim_names = {d.dimension for d in report.quality_dimensions}
    expected_dims = {
        "provenance", "institution", "period", "currency",
        "normalization", "validation", "conflict_absence", "historical_coherence"
    }
    assert dim_names == expected_dims
    assert report.overall_quality_score >= 80.0


# ==============================================================================
# 7. CONSOLIDATOR ORCHESTRATOR TESTS
# ==============================================================================

def test_consolidator_orchestrates_all_analyzers():
    """FinancialDataConsolidator routes queries and synthesizes reports correctly."""
    consolidator = FinancialDataConsolidator()
    obs = [
        make_obs("o1", "inst-1", "TOTAL_ASSETS", 2023, Decimal("100"), doc_id="d1"),
        make_obs("o2", "inst-1", "TOTAL_ASSETS", 2023, Decimal("100"), doc_id="d2"),  # Duplicate
        make_obs("o3", "inst-1", "TOTAL_ASSETS", 2024, Decimal("150"), doc_id="d2"),
    ]

    dups = consolidator.get_duplicates(obs)
    assert len(dups) == 1

    series = consolidator.get_historical_series(obs)
    assert len(series) == 1

    report = consolidator.get_quality_report(obs)
    assert report.total_points == 3
    assert report.potential_duplicates_count == 1


# ==============================================================================
# 8. REST API ENDPOINTS TESTS
# ==============================================================================

@pytest.fixture
def mock_financial_rows():
    """Mock database rows with relations for API integration testing."""
    country = MagicMock(spec=Country)
    country.code = "CI"
    inst = MagicMock(spec=Institution)
    inst.id = "inst-ci-1"
    inst.name_official = "Banque CI"
    inst.name_commercial = "BCI"
    inst.country = country

    src = MagicMock(spec=Source)
    src.id = "src-1"
    src.name = "BCEAO"
    src.source_type = "central_bank"
    src.priority = 1

    doc1 = MagicMock(spec=Document)
    doc1.id = "doc-1"
    doc1.title = "Rapport 2023"

    doc2 = MagicMock(spec=Document)
    doc2.id = "doc-2"
    doc2.title = "Rapport 2024"

    fd1 = MagicMock(
        spec=FinancialData,
        id="fd-1",
        institution_id="inst-ci-1",
        source_id="src-1",
        document_id="doc-1",
        metric_code="TOTAL_ASSETS",
        period_year=2023,
        period_type="annual",
        period_label="2023",
        value_original="1000",
        value_normalized=Decimal("1000.00"),
        currency_original="XOF",
        currency_normalized="XOF",
        unit_original="thousands",
        unit_normalized="absolute",
        page_number=1,
        extraction_method="pdf_table",
        confidence_score=Decimal("0.95"),
        status="verified",
        verified_by="analyst_test",
        institution=inst,
        source=src,
        document=doc1,
        deleted_at=None,
    )

    fd2 = MagicMock(
        spec=FinancialData,
        id="fd-2",
        institution_id="inst-ci-1",
        source_id="src-1",
        document_id="doc-2",
        metric_code="TOTAL_ASSETS",
        period_year=2023,  # Same logical key with fd1 -> duplicate/conflict
        period_type="annual",
        period_label="2023",
        value_original="1000",
        value_normalized=Decimal("1000.00"),
        currency_original="XOF",
        currency_normalized="XOF",
        unit_original="thousands",
        unit_normalized="absolute",
        page_number=3,
        extraction_method="pdf_table",
        confidence_score=Decimal("0.90"),
        status="extracted",
        verified_by=None,
        institution=inst,
        source=src,
        document=doc2,
        deleted_at=None,
    )

    return [fd1, fd2]


@pytest.mark.asyncio
async def test_api_duplicates_endpoint(mock_financial_rows):
    """GET /api/v1/financial-data/duplicates returns grouped duplicate observations."""
    db = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = mock_financial_rows
    db.execute.return_value = exec_res

    from app.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.get("/api/v1/financial-data/duplicates?institution_id=inst-ci-1")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert data["total"] == 1
            assert data["items"][0]["duplicate_type"] == "duplicate_different_source"
            assert data["items"][0]["count"] == 2
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_conflicts_endpoint(mock_financial_rows):
    """GET /api/v1/financial-data/conflicts returns empty when values are identical."""
    db = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalars.return_value.all.return_value = mock_financial_rows
    db.execute.return_value = exec_res

    from app.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.get("/api/v1/financial-data/conflicts")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert data["total"] == 0  # Identical duplicates are not value conflicts
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_coverage_endpoint(mock_financial_rows):
    """GET /api/v1/financial-data/coverage returns institutional historical depth."""
    db = AsyncMock()
    exec_rows = MagicMock()
    exec_rows.scalars.return_value.all.return_value = mock_financial_rows

    inst_mock = MagicMock()
    inst_mock.scalars.return_value.all.return_value = [mock_financial_rows[0].institution]

    db.execute.side_effect = [exec_rows, inst_mock]

    from app.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.get("/api/v1/financial-data/coverage")
            assert resp.status_code == 200
            data = resp.json()
            assert "items" in data
            assert data["total"] == 1
            item = data["items"][0]
            assert item["institution_id"] == "inst-ci-1"
            assert item["available_years"] == [2023]
            assert item["coverage_ratio"] == 1.0
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_historical_quality_endpoint(mock_financial_rows):
    """GET /api/v1/financial-data/historical-quality returns multi-dimensional scorecard."""
    db = AsyncMock()
    exec_rows = MagicMock()
    exec_rows.scalars.return_value.all.return_value = mock_financial_rows
    db.execute.return_value = exec_rows

    from app.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.get("/api/v1/financial-data/historical-quality")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_points"] == 2
            assert data["verified_count"] == 1
            assert data["potential_duplicates_count"] == 1
            assert "overall_quality_score" in data
            assert len(data["quality_dimensions"]) == 8
        finally:
            app.dependency_overrides.clear()
