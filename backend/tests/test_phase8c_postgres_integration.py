"""
Phase 8C — Analytics endpoints against a REAL PostgreSQL database.

The Phase 7 API tests mock AnalyticsService, so they never ran the real SQL.
This module:
  1. creates a dedicated scratch database (never the dev database);
  2. applies every Alembic migration (``upgrade head``);
  3. seeds a minimal dataset exercising the Phase 8C rules;
  4. calls /api/v1/analytics/{ratios,growth,aggregations,sector,compare}
     through the real FastAPI app bound to that database.

Rules verified (DATA MISSING > DATA WRONG):
  A. individual + consolidated for the same year → sector aggregate uses individual only;
  B. individual 2024 / consolidated 2024 / individual 2023 → only individual annual rows used;
  C. a rejected observation never contributes;
  D. contributions in incompatible currencies are never summed;
  plus: semi-annual rows excluded, unresolved conflicts excluded, ratio and growth
  components never mix scopes, compare uses the authoritative value.

Skipped automatically when no PostgreSQL server is reachable.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

YEAR = 2024
PREV = 2023


# ---------------------------------------------------------------------------
# Scratch database + seed
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase8c_pytest"
    asyncio.run(
        _exec_admin(
            params,
            f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)',
            f'CREATE DATABASE "{test_db}"',
        )
    )
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")

    ids = asyncio.run(_seed(_async_dsn(params, test_db)))
    yield {"url": _async_dsn(params, test_db), "ids": ids}

    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        countries = {c.code: c for c in (await db.execute(select(Country))).scalars().all()}
        source = (await db.execute(select(Source))).scalars().first()
        assert source is not None, "migration 0004 seeds official sources"

        def bank(name: str, code: str) -> Institution:
            inst = Institution(name_official=name, institution_type="bank", country_id=countries[code].id, status="active")
            db.add(inst)
            return inst

        a, b, c, d = bank("Banque A", "CI"), bank("Banque B", "CI"), bank("Banque C", "CI"), bank("Banque D", "CI")
        s1, s2 = bank("Banque S1", "SN"), bank("Banque S2", "SN")
        await db.flush()

        doc = Document(title="Rapport annuel test", document_type="annual_report", source_id=source.id,
                       download_status="downloaded", extraction_status="extracted")
        db.add(doc)
        await db.flush()

        def fd(inst, metric, value, *, year=YEAR, scope="individual", period_type="annual",
               status="extracted", currency="XOF"):
            extra = {}
            if status == "verified":
                extra = {"verified_at": datetime.now(UTC), "verified_by": "analyst"}
            db.add(FinancialData(
                institution_id=inst.id, source_id=source.id, document_id=doc.id, metric_code=metric,
                scope=scope, period_type=period_type, period_year=year, value_original=str(value),
                value_normalized=Decimal(str(value)), currency_normalized=currency,
                extraction_method="pdf_table", status=status, page_number=1, **extra,
            ))

        # Bank A — cases A and B.
        fd(a, "total_actifs", 1000)
        fd(a, "total_actifs", 5000, scope="consolidated")
        fd(a, "total_actifs", 480, period_type="semi_annual")
        fd(a, "total_actifs", 900, year=PREV)
        fd(a, "total_actifs", 4000, year=PREV, scope="consolidated")
        fd(a, "depots_clients", 600)
        fd(a, "depots_clients", 2000, scope="consolidated")
        fd(a, "resultat_net", 50, scope="consolidated")  # only consolidated: individual ROA must stay unavailable

        # Bank B — case C: only a rejected value.
        fd(b, "total_actifs", 777777, status="rejected")
        # Bank C — clean individual value, plus a rejected one that must not win.
        fd(c, "total_actifs", 3000, status="verified")
        fd(c, "total_actifs", 999999, status="rejected")
        # Bank D — unresolved conflict (two divergent unverified values).
        fd(d, "total_actifs", 10)
        fd(d, "total_actifs", 20)

        # Senegal — case D: incompatible currencies.
        fd(s1, "total_actifs", 100, currency="XOF")
        fd(s2, "total_actifs", 50, currency="EUR")

        await db.commit()
        ids = {"A": a.id, "B": b.id, "C": c.id, "D": d.id}
    await engine.dispose()
    return ids


@pytest.fixture
async def api(pg_db: dict) -> AsyncGenerator[AsyncClient, None]:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.db.session import get_db_session
    from app.main import create_app

    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def override() -> AsyncGenerator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client
    await engine.dispose()


def one(items: list[dict], **match) -> dict:
    found = [i for i in items if all(i.get(k) == v for k, v in match.items())]
    assert len(found) == 1, (match, items)
    return found[0]


# ---------------------------------------------------------------------------
# Aggregations — cases A, C, D, conflicts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_aggregations_individual_annual_only(api: AsyncClient, pg_db: dict):
    r = await api.get("/api/v1/analytics/aggregations", params={"year": YEAR, "metric_code": "total_actifs", "country_code": "CI"})
    assert r.status_code == 200, r.text
    ci = one(r.json(), country_code="CI")
    ids = pg_db["ids"]

    # A: 1000 (individual) — never 5000 (consolidated) nor 480 (semi-annual).
    # C: B's rejected 777777 and C's rejected 999999 never contribute; C contributes 3000.
    # Conflict: D (10 vs 20, unverified) is excluded.
    assert Decimal(ci["total_value"]) == Decimal("4000")
    assert sorted(ci["contributing_institutions"]) == sorted([ids["A"], ids["C"]])
    assert ci["data_scope"] == "individual"
    assert ci["period_type"] == "annual"
    assert ci["currency"] == "XOF"
    assert ci["institution_count"] == 2 and ci["total_institutions"] == 4
    assert ci["is_partial"] is True
    assert "conflicting" in ci["notes"]


@pytest.mark.asyncio
async def test_aggregations_currency_mismatch_not_summed(api: AsyncClient):
    r = await api.get("/api/v1/analytics/aggregations", params={"year": YEAR, "metric_code": "total_actifs", "country_code": "SN"})
    assert r.status_code == 200, r.text
    sn = one(r.json(), country_code="SN")
    assert sn["total_value"] is None
    assert sn["status"] == "needs_review"
    assert sn["currency"] is None
    assert "Currency mismatch" in sn["notes"]


@pytest.mark.asyncio
async def test_umoa_aggregation_not_computed_when_a_country_is_under_review(api: AsyncClient):
    r = await api.get("/api/v1/analytics/aggregations", params={"year": YEAR, "metric_code": "total_actifs", "scope": "umoa"})
    assert r.status_code == 200, r.text
    umoa = r.json()[0]
    assert umoa["total_value"] is None
    assert umoa["status"] == "needs_review"
    assert umoa["currency"] is None


@pytest.mark.asyncio
async def test_umoa_aggregation_individual_only(api: AsyncClient):
    r = await api.get("/api/v1/analytics/aggregations", params={"year": YEAR, "metric_code": "depots_clients", "scope": "umoa"})
    assert r.status_code == 200, r.text
    umoa = r.json()[0]
    assert Decimal(umoa["total_value"]) == Decimal("600")  # never 2000 (consolidated)
    assert umoa["data_scope"] == "individual"


# ---------------------------------------------------------------------------
# Sector structure / market shares
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sector_market_shares_only_contributors(api: AsyncClient, pg_db: dict):
    r = await api.get("/api/v1/analytics/sector", params={"country_code": "CI", "year": YEAR, "metric_code": "total_actifs"})
    assert r.status_code == 200, r.text
    body = r.json()
    ids = pg_db["ids"]
    shares = {s["institution_id"]: s for s in body["market_shares"]}
    assert set(shares) == {ids["A"], ids["C"]}  # B (rejected) and D (conflict) have no share
    assert shares[ids["A"]]["market_share_percent"] == pytest.approx(25.0)
    assert shares[ids["C"]]["market_share_percent"] == pytest.approx(75.0)


@pytest.mark.asyncio
async def test_sector_currency_mismatch_has_no_shares(api: AsyncClient):
    r = await api.get("/api/v1/analytics/sector", params={"country_code": "SN", "year": YEAR, "metric_code": "total_actifs"})
    assert r.status_code == 200, r.text
    assert r.json()["aggregation"]["total_value"] is None
    assert r.json()["market_shares"] == []


# ---------------------------------------------------------------------------
# Ratios & growth — scope never mixed (case B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ratios_individual_scope(api: AsyncClient, pg_db: dict):
    r = await api.get("/api/v1/analytics/ratios", params={"institution_id": pg_db["ids"]["A"], "year": YEAR, "page_size": 100})
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    dep = one(items, ratio_code="DEPOTS_ACTIFS")
    assert dep["value_percent"] == pytest.approx(60.0)  # 600 / 1000, individual
    assert dep["data_scope"] == "individual"
    assert {c["scope"] for c in dep["components"]} == {"individual"}
    # ROA needs resultat_net, which only exists in consolidated accounts: never borrowed.
    roa = one(items, ratio_code="ROA")
    assert roa["value_percent"] is None
    assert roa["status"] == "unavailable"


@pytest.mark.asyncio
async def test_ratios_consolidated_scope_is_explicit(api: AsyncClient, pg_db: dict):
    r = await api.get(
        "/api/v1/analytics/ratios",
        params={"institution_id": pg_db["ids"]["A"], "year": YEAR, "data_scope": "consolidated", "ratio_code": "DEPOTS_ACTIFS"},
    )
    assert r.status_code == 200, r.text
    dep = r.json()["items"][0]
    assert dep["value_percent"] == pytest.approx(40.0)  # 2000 / 5000, consolidated
    assert {c["scope"] for c in dep["components"]} == {"consolidated"}


@pytest.mark.asyncio
async def test_growth_same_scope_both_years(api: AsyncClient, pg_db: dict):
    r = await api.get(
        "/api/v1/analytics/growth",
        params={"institution_id": pg_db["ids"]["A"], "year": YEAR, "metric_code": "total_actifs"},
    )
    assert r.status_code == 200, r.text
    g = r.json()["items"][0]
    # 1000 (2024 individual) vs 900 (2023 individual) — never 5000 / 4000 / 480.
    assert Decimal(g["current_value"]) == Decimal("1000")
    assert Decimal(g["previous_value"]) == Decimal("900")
    assert g["growth_percent"] == pytest.approx(11.1111, rel=1e-3)
    assert {c["scope"] for c in g["components"]} == {"individual"}


# ---------------------------------------------------------------------------
# Compare
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_metric_authoritative_same_scope(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    params = {"entity_a": ids["A"], "entity_b": ids["C"], "metric_or_ratio": "total_actifs", "year": YEAR}
    r = await api.get("/api/v1/analytics/compare", params=params)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["value_a"] == pytest.approx(1000)
    assert body["value_b"] == pytest.approx(3000)  # verified value, never the rejected 999999

    r = await api.get("/api/v1/analytics/compare", params={**params, "data_scope": "consolidated"})
    assert r.status_code == 200, r.text
    assert r.json()["value_a"] == pytest.approx(5000)
    assert r.json()["value_b"] is None


@pytest.mark.asyncio
async def test_compare_conflict_is_missing(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    r = await api.get(
        "/api/v1/analytics/compare",
        params={"entity_a": ids["D"], "entity_b": ids["A"], "metric_or_ratio": "total_actifs", "year": YEAR},
    )
    assert r.status_code == 200, r.text
    assert r.json()["value_a"] is None


@pytest.mark.asyncio
async def test_compare_ratio(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    r = await api.get(
        "/api/v1/analytics/compare",
        params={"entity_a": ids["A"], "entity_b": ids["C"], "metric_or_ratio": "DEPOTS_ACTIFS", "year": YEAR},
    )
    assert r.status_code == 200, r.text
    assert r.json()["value_a"] == pytest.approx(60.0)
    assert r.json()["value_b"] is None


# ---------------------------------------------------------------------------
# Financial data list — case B at the raw API level
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_financial_data_filters_return_only_individual_annual(api: AsyncClient, pg_db: dict):
    r = await api.get(
        "/api/v1/financial-data",
        params={
            "institution_id": pg_db["ids"]["A"],
            "metric_code": "total_actifs",
            "period_year": YEAR,
            "scope": "individual",
            "period_type": "annual",
        },
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert len(items) == 1
    assert Decimal(items[0]["value_normalized"]) == Decimal("1000")


@pytest.mark.asyncio
async def test_country_without_institutions_has_unknown_coverage(api: AsyncClient):
    """No licensed institution known → coverage None (never 0/1 on an invented denominator)."""
    r = await api.get("/api/v1/analytics/aggregations", params={"year": YEAR, "metric_code": "total_actifs", "country_code": "BJ"})
    assert r.status_code == 200, r.text
    bj = one(r.json(), country_code="BJ")
    assert bj["total_value"] is None
    assert bj["status"] == "unavailable"
    assert bj["total_institutions"] == 0
    assert bj["coverage_ratio"] is None
    assert bj["is_partial"] is False
