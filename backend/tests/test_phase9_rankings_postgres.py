"""
Phase 9 — Rankings & comparisons against a REAL PostgreSQL database.

Same scratch-database mechanism as Phase 8C (never the dev database):
Alembic upgrade head, minimal seed, real FastAPI app bound to the scratch DB.

Seed (fiscal year 2024 unless stated, individual annual, XOF):
  CI  A 5000 (verified) · B 5000 (tie) · C 3000 · D conflict (10 vs 20)
      E rejected only · F no data
      A also: 9000 consolidated, 480 semi-annual, 4000 in 2023
      C also: 3500 in 2023
      depots_clients: A 2500, B 2500 (DEPOTS_ACTIFS tie at 50 %)
  SN  S1 100 XOF · S2 50 EUR (heterogeneous currencies)

Skipped automatically when no PostgreSQL server is reachable.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

YEAR = 2024


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase9_pytest"
    asyncio.run(
        _exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"')
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
        banks = {}
        for key, code in (("A", "CI"), ("B", "CI"), ("C", "CI"), ("D", "CI"), ("E", "CI"), ("F", "CI"),
                          ("S1", "SN"), ("S2", "SN")):
            banks[key] = Institution(name_official=f"Banque {key}", institution_type="bank",
                                     country_id=countries[code].id, status="active")
            db.add(banks[key])
        await db.flush()
        doc = Document(title="Rapport annuel", document_type="annual_report", source_id=source.id,
                       download_status="downloaded", extraction_status="extracted")
        db.add(doc)
        await db.flush()

        def fd(key, value, *, metric="total_actifs", year=YEAR, scope="individual", period_type="annual",
               status="extracted", currency="XOF"):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "analyst"} if status == "verified" else {}
            db.add(FinancialData(
                institution_id=banks[key].id, source_id=source.id, document_id=doc.id, metric_code=metric,
                # consolidation_scope must agree with scope: rankings refuse incoherent rows.
                scope=scope, consolidation_scope=scope, period_type=period_type, period_year=year,
                value_original=str(value),
                value_normalized=Decimal(str(value)), currency_normalized=currency,
                extraction_method="pdf_table", status=status, page_number=7, **extra,
            ))

        fd("A", 5000, status="verified")
        fd("A", 9000, scope="consolidated")
        fd("A", 480, period_type="semi_annual")
        fd("A", 4000, year=2023)
        fd("B", 5000)
        fd("C", 3000)
        fd("C", 3500, year=2023)
        fd("D", 10)
        fd("D", 20)
        fd("E", 777, status="rejected")
        fd("A", 2500, metric="depots_clients")
        fd("B", 2500, metric="depots_clients")
        fd("S1", 100, currency="XOF")
        fd("S2", 50, currency="EUR")
        await db.commit()
        ids = {k: v.id for k, v in banks.items()}
    await engine.dispose()
    return ids


@pytest_asyncio.fixture
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


def names(items):
    return [(e["rank"], e["institution_name"]) for e in items]


# ---------------------------------------------------------------------------
# Rankings
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_national_ranking_ties_unavailable_and_coverage(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "country_code": "CI"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["period_year"] == YEAR  # latest year holding data, not a constant
    assert d["period_type"] == "annual" and d["data_scope"] == "individual"
    assert names(d["items"]) == [(1, "Banque A"), (1, "Banque B"), (3, "Banque C")]
    assert Decimal(d["items"][0]["value"]) == Decimal("5000")  # never 9000 (consolidated) nor 480 (semi-annual)
    assert d["items"][0]["provenance"][0]["page_number"] == 7
    assert d["items"][0]["data_id"]
    reasons = {u["institution_name"]: u["reason"] for u in d["unavailable"]}
    assert reasons == {"Banque D": "conflict", "Banque E": "rejected_only", "Banque F": "missing"}
    assert d["coverage"] == {
        "eligible_count": 3, "ranked_count": 3, "expected_count": 6,
        "coverage_ratio": 0.5, "coverage_status": "available",
    }
    assert d["status"] == "partial" and d["currency"] == "XOF"


@pytest.mark.asyncio
async def test_consolidated_and_semi_annual_are_separate_rankings(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "country_code": "CI",
                                                  "data_scope": "consolidated"})
    assert names(r.json()["items"]) == [(1, "Banque A")]
    assert Decimal(r.json()["items"][0]["value"]) == Decimal("9000")
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "country_code": "CI",
                                                  "period_type": "semi_annual"})
    assert names(r.json()["items"]) == [(1, "Banque A")]
    assert Decimal(r.json()["items"][0]["value"]) == Decimal("480")


@pytest.mark.asyncio
async def test_umoa_ranking_heterogeneous_currency_needs_review(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "country_code": "UMOA"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "needs_review" and d["reason"] == "heterogeneous_currency"
    assert d["items"] == []
    assert d["country_code"] == "UMOA"
    # Values exist but cannot be ranked: real eligible count, nothing ranked, no 0/N coverage.
    assert d["coverage"]["eligible_count"] == 5  # A, B, C (CI) + S1, S2 (SN)
    assert d["coverage"]["ranked_count"] == 0
    assert d["coverage"]["expected_count"] == 8
    assert d["coverage"]["coverage_ratio"] is None
    assert d["coverage"]["coverage_status"] == "unavailable"


@pytest.mark.asyncio
async def test_umoa_ranking_across_countries(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "depots_clients"})
    d = r.json()
    assert names(d["items"]) == [(1, "Banque A"), (1, "Banque B")]
    assert d["coverage"]["expected_count"] == 8


@pytest.mark.asyncio
async def test_explicit_year_without_data(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "total_actifs", "country_code": "CI",
                                                  "period_year": 2019})
    d = r.json()
    assert d["items"] == [] and d["status"] == "unavailable" and d["period_year"] == 2019


@pytest.mark.asyncio
async def test_growth_and_ratio_rankings(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "growth_total_actifs", "country_code": "CI"})
    d = r.json()
    assert names(d["items"]) == [(1, "Banque A"), (2, "Banque C")]
    assert d["items"][0]["value"] == pytest.approx(25.0) or Decimal(d["items"][0]["value"]) == Decimal("25")
    assert "Banque B" in {u["institution_name"] for u in d["unavailable"]}  # no 2023 value: never ranked

    r = await api.get("/api/v1/rankings", params={"metric_code": "DEPOTS_ACTIFS", "country_code": "CI"})
    d = r.json()
    assert names(d["items"]) == [(1, "Banque A"), (1, "Banque B")]
    assert d["items"][0]["unit"] == "%"
    assert {p["scope"] for p in d["items"][0]["provenance"]} == {"individual"}


@pytest.mark.asyncio
async def test_unknown_indicator_404(api: AsyncClient):
    r = await api.get("/api/v1/rankings", params={"metric_code": "best_bank"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_rank_history(api: AsyncClient, pg_db: dict):
    r = await api.get("/api/v1/rankings/history",
                      params={"institution_id": pg_db["ids"]["A"], "metric_code": "total_actifs"})
    assert r.status_code == 200, r.text
    points = {p["period_year"]: p for p in r.json()["points"]}
    assert set(points) == {2023, 2024}
    assert points[2023]["rank"] == 1 and points[2024]["rank"] == 1
    r = await api.get("/api/v1/rankings/history",
                      params={"institution_id": pg_db["ids"]["F"], "metric_code": "total_actifs"})
    assert all(p["rank"] is None and p["reason"] == "missing" for p in r.json()["points"])


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compare_institutions(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    r = await api.get("/api/v1/comparisons", params={"institution_ids": f"{ids['A']},{ids['C']},{ids['F']}",
                                                     "metric_code": "total_actifs"})
    assert r.status_code == 200, r.text
    rows = {row["institution_name"]: row for row in r.json()["rows"]}
    assert Decimal(rows["Banque A"]["value"]) == Decimal("5000")
    assert Decimal(rows["Banque C"]["value"]) == Decimal("3000")
    assert rows["Banque F"]["value"] is None and rows["Banque F"]["reason"] == "missing"
    assert r.json()["status"] == "partial"


@pytest.mark.asyncio
async def test_compare_institutions_heterogeneous_currency(api: AsyncClient, pg_db: dict):
    ids = pg_db["ids"]
    r = await api.get("/api/v1/comparisons", params={"institution_ids": f"{ids['S1']},{ids['S2']}",
                                                     "metric_code": "total_actifs"})
    d = r.json()
    assert d["status"] == "needs_review" and all(row["value"] is None for row in d["rows"])


@pytest.mark.asyncio
async def test_compare_institutions_bounds(api: AsyncClient, pg_db: dict):
    ids = list(pg_db["ids"].values())
    assert (await api.get("/api/v1/comparisons", params={"institution_ids": ids[0], "metric_code": "total_actifs"}
                          )).status_code == 422
    assert (await api.get("/api/v1/comparisons", params={"institution_ids": ",".join(ids[:6]),
                                                         "metric_code": "total_actifs"})).status_code == 422


@pytest.mark.asyncio
async def test_institution_vs_sector(api: AsyncClient, pg_db: dict):
    r = await api.get("/api/v1/comparisons/sector",
                      params={"institution_id": pg_db["ids"]["A"], "metric_code": "total_actifs"})
    d = r.json()
    assert Decimal(d["sector_total"]) == Decimal("13000")  # A + B + C, individual annual only
    assert d["share_percent"] == pytest.approx(38.4615, rel=1e-4)
    r = await api.get("/api/v1/comparisons/sector",
                      params={"institution_id": pg_db["ids"]["D"], "metric_code": "total_actifs"})
    assert r.json()["share_percent"] is None and r.json()["reason"] == "institution_value_unavailable"


@pytest.mark.asyncio
async def test_country_vs_umoa(api: AsyncClient):
    r = await api.get("/api/v1/comparisons/country", params={"country_code": "CI", "metric_code": "total_actifs"})
    d = r.json()
    assert d["status"] == "needs_review" and d["share_percent"] is None  # UMOA total blocked by SN currencies
    r = await api.get("/api/v1/comparisons/country", params={"country_code": "CI", "metric_code": "depots_clients"})
    d = r.json()
    assert d["share_percent"] == pytest.approx(100.0) and d["currency"] == "XOF"


@pytest.mark.asyncio
async def test_market_share_contributors_only(api: AsyncClient):
    r = await api.get("/api/v1/analytics/sector", params={"country_code": "CI", "year": YEAR,
                                                          "metric_code": "total_actifs"})
    shares = {s["institution_name"]: s["market_share_percent"] for s in r.json()["market_shares"]}
    assert set(shares) == {"Banque A", "Banque B", "Banque C"}
    assert sum(shares.values()) == pytest.approx(100.0, abs=1e-3)  # shares are rounded to 4 decimals


@pytest.mark.asyncio
async def test_country_and_sector_comparisons_not_supported_for_ratio_and_growth(api: AsyncClient, pg_db: dict):
    for code in ("ROA", "growth_total_actifs"):
        r = await api.get("/api/v1/comparisons/country", params={"country_code": "CI", "metric_code": code})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["status"] == "unavailable" and d["reason"] == "aggregate_not_supported"
        assert d["country_total"] is None and d["umoa_total"] is None and d["share_percent"] is None

        r = await api.get("/api/v1/comparisons/sector", params={"institution_id": pg_db["ids"]["A"], "metric_code": code})
        d = r.json()
        assert d["status"] == "unavailable" and d["reason"] == "aggregate_not_supported"
        assert d["sector_total"] is None and d["share_percent"] is None

