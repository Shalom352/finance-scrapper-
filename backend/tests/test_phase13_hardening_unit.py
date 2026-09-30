"""
Phase 13 — production hardening, unit tests (no database).

Health readiness (503), error envelope for router-level errors, security headers,
production configuration guards, CSV formula neutralization, scope-aware detectors,
explicit needs_review flag in aggregations, no invented 0 % share.
"""
from collections.abc import AsyncGenerator
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from scraping.analytics.aggregation import SectorAggregator
from scraping.analytics.sector_analysis import SectorAnalyzer
from scraping.consolidation.conflict_detector import ConflictDetector
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.historical_analyzer import HistoricalAnalyzer
from scraping.consolidation.models import ObservationSummary
from scraping.financial_data.export import _cell
from scraping.pipeline import SCOPE_NOT_DETECTED_NOTE, scope_guard


def obs(i, value, *, scope="individual", status="extracted", year=2024, period_type="annual", inst="A"):
    return ObservationSummary(
        id=i, institution_id=inst, metric_code="total_actifs", source_id="s", document_id=f"d{i}",
        period_year=year, period_type=period_type, scope=scope, value_original=str(value),
        value_normalized=None if value is None else Decimal(str(value)), currency_normalized="XOF",
        unit_normalized="unit", status=status,
    )


# ------------------------------------------------------------------ health / envelope / headers


@pytest.fixture
async def broken_db_client() -> AsyncGenerator[AsyncClient, None]:
    """Application whose database is unreachable (closed port)."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.session import get_db_session
    from app.main import create_app

    engine = create_async_engine("postgresql+asyncpg://nobody:not-a-secret@127.0.0.1:1/none",
                                 connect_args={"timeout": 2})
    maker = async_sessionmaker(engine)

    async def override():
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await engine.dispose()


@pytest.mark.asyncio
async def test_readiness_is_503_when_the_database_is_down(broken_db_client):
    r = await broken_db_client.get("/api/v1/health")
    assert r.status_code == 503
    body = r.json()
    assert body["status"] == "unavailable" and body["database"] == {"status": "unavailable"}
    text = r.text
    for leak in ("127.0.0.1", "nobody", "not-a-secret", "Error", "Traceback"):
        assert leak not in text


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_the_database(broken_db_client):
    assert (await broken_db_client.get("/health")).status_code == 200


@pytest.mark.asyncio
async def test_router_level_errors_use_the_error_envelope(client):
    r = await client.get("/api/v1/does-not-exist")
    assert r.status_code == 404 and r.json()["error"]["code"] == "RESOURCE_NOT_FOUND"
    r = await client.delete("/health")
    assert r.status_code == 405 and r.json()["error"]["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.asyncio
async def test_security_headers_are_set(client):
    r = await client.get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"


@pytest.mark.asyncio
async def test_unhandled_errors_never_expose_a_stack_trace():
    from app.main import create_app

    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    async with AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False),
                           base_url="http://test") as client:
        r = await client.get("/boom")
    assert r.status_code == 500 and r.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "secret internal detail" not in r.text and "Traceback" not in r.text


def test_production_configuration_guards(monkeypatch):
    from pydantic import ValidationError

    from app.core.config import Settings

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "*")
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings()
    monkeypatch.setenv("CORS_ORIGINS", "https://umoa.example")
    monkeypatch.setenv("BACKEND_DEBUG", "true")
    with pytest.raises(ValidationError, match="BACKEND_DEBUG"):
        Settings()
    monkeypatch.setenv("BACKEND_DEBUG", "false")
    assert Settings().cors_origins_list == ["https://umoa.example"]


def test_api_docs_are_not_exposed_in_production(monkeypatch):
    from app.core import config
    from app.main import create_app

    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("CORS_ORIGINS", "https://umoa.example")
    monkeypatch.setenv("BACKEND_DEBUG", "false")
    config.get_settings.cache_clear()
    try:
        app = create_app()
        assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None
    finally:
        monkeypatch.undo()
        config.get_settings.cache_clear()


# ------------------------------------------------------------------ CSV export


@pytest.mark.parametrize("value, expected", [
    ("=HYPERLINK(\"http://x\")", "'=HYPERLINK(\"http://x\")"),
    ("+1+1", "'+1+1"),
    ("@SUM(A1)", "'@SUM(A1)"),
    ("-2+3+cmd|' /C calc'!A0", "'-2+3+cmd|' /C calc'!A0"),
    ("-1 250,5", "-1 250,5"),        # a published negative number is kept as published
    ("Banque A", "Banque A"),
    (None, ""),                       # missing stays missing
    (Decimal("-12.50"), "-12.50"),
])
def test_csv_cells_are_neutralized_against_formula_injection(value, expected):
    assert _cell(value) == expected


# ------------------------------------------------------------------ scope guard helper


def test_scope_guard_forces_needs_review_and_is_idempotent():
    assert scope_guard("extracted", None) == ("needs_review", SCOPE_NOT_DETECTED_NOTE)
    status, notes = scope_guard("extracted", "Resolved to Banque A")
    assert status == "needs_review" and notes == f"Resolved to Banque A | {SCOPE_NOT_DETECTED_NOTE}"
    assert scope_guard("needs_review", notes) == ("needs_review", notes)


# ------------------------------------------------------------------ detectors never mix scopes


def test_individual_and_consolidated_are_neither_duplicates_nor_conflicts():
    rows = [obs("1", 100), obs("2", 900, scope="consolidated")]
    assert DuplicateDetector().detect_duplicates(rows) == []
    assert ConflictDetector().detect_conflicts(rows) == []
    same_scope = [obs("1", 100), obs("2", 130)]
    (group,) = DuplicateDetector().detect_duplicates(same_scope)
    assert group.logical_key.endswith(":annual:individual")
    assert len(ConflictDetector().detect_conflicts(same_scope)) == 1


def test_history_never_chains_scopes_nor_uses_rejected_rows():
    rows = [obs("1", 100, year=2022), obs("2", 900, year=2023, scope="consolidated"),
            obs("3", 5, year=2023, status="rejected")]
    series = HistoricalAnalyzer().analyze_series(rows)
    by_scope = {s.scope: s for s in series}
    assert set(by_scope) == {"individual", "consolidated"}
    assert by_scope["individual"].available_years == [2022]  # the rejected 2023 row is not a value
    assert by_scope["consolidated"].available_years == [2023]


# ------------------------------------------------------------------ aggregation and shares


def test_including_needs_review_is_flagged_and_never_calculated():
    rows = [obs("1", 100, inst="A"), obs("2", 50, inst="B", status="needs_review")]
    excluded = SectorAggregator().aggregate_country("CI", 2024, "total_actifs", rows, 2)
    assert excluded.total_value == Decimal("100") and "excluded" in excluded.notes
    included = SectorAggregator().aggregate_country("CI", 2024, "total_actifs", rows, 2, include_needs_review=True)
    assert included.status == "needs_review" and included.total_value == Decimal("150")
    assert "Includes observations with 'needs_review'" in included.notes


def test_unavailable_share_is_not_described_as_zero_percent():
    r = SectorAnalyzer().compare_institution_to_country("Banque A", None, "CI", Decimal("10"), "total_actifs", 2024)
    assert r.ratio_a_to_b is None and "0.0%" not in r.description and "not available" in r.description
    r = SectorAnalyzer().compare_country_to_umoa("CI", Decimal("10"), None, "total_actifs", 2024)
    assert r.ratio_a_to_b is None and "0.0%" not in r.description
