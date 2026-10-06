"""
Phase 10 — Institution financial profile against a REAL PostgreSQL database.

Same scratch-database mechanism as Phases 8C / 9 (never the dev database).

Seed — Banque A (CI), individual annual XOF unless stated:
  total_actifs      2021: 800 · 2022: 850 · 2024: 1000 (verified, p.84)   — 2023 absent
                    2024 consolidated: 9000 · 2024 semi-annual: 480
  depots_clients    2024: 600 · 2022: 500
  creances_clients  2024: needs_review
  capitaux_propres  2024: conflict (100 vs 130)
  resultat_net      2024: rejected only
  produit_net_bancaire: none
Banque B (CI): no data at all.
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


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase10_pytest"
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
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        source = (await db.execute(select(Source))).scalars().first()
        a = Institution(name_official="Banque A", institution_type="bank", country_id=ci.id, status="active")
        b = Institution(name_official="Banque B", institution_type="bank", country_id=ci.id, status="active")
        db.add_all([a, b])
        await db.flush()
        doc = Document(title="Rapport annuel 2024", document_type="annual_report", source_id=source.id,
                       institution_id=a.id, download_status="downloaded", extraction_status="extracted")
        db.add(doc)
        await db.flush()

        def fd(metric, value, *, year=2024, scope="individual", period_type="annual", status="extracted", page=12):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "analyst"} if status == "verified" else {}
            db.add(FinancialData(
                institution_id=a.id, source_id=source.id, document_id=doc.id, metric_code=metric, scope=scope,
                period_type=period_type, period_year=year, value_original=f"{value} (millions)",
                unit_original="millions", currency_original="XOF", value_normalized=Decimal(str(value)),
                unit_normalized="unit", currency_normalized="XOF", extraction_method="pdf_table",
                status=status, page_number=page, **extra,
            ))

        fd("total_actifs", 800, year=2021)
        fd("total_actifs", 850, year=2022)
        fd("total_actifs", 1000, status="verified", page=84)
        fd("total_actifs", 9000, scope="consolidated")
        fd("total_actifs", 480, period_type="semi_annual")
        fd("depots_clients", 600)
        fd("depots_clients", 500, year=2022)
        fd("creances_clients", 700, status="needs_review")
        fd("capitaux_propres", 100)
        fd("capitaux_propres", 130)
        fd("resultat_net", 55, status="rejected")
        await db.commit()
        ids = {"A": a.id, "B": b.id}
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


def base(pg_db, key="A"):
    return f"/api/v1/institutions/{pg_db['ids'][key]}"


@pytest.mark.asyncio
async def test_financials_values_unavailable_reasons_and_provenance(api: AsyncClient, pg_db: dict):
    r = await api.get(f"{base(pg_db)}/financials")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["period_year"] == 2024 and d["period_type"] == "annual" and d["data_scope"] == "individual"
    values = {v["metric_code"]: v for v in d["values"]}
    assert set(values) == {"total_actifs", "depots_clients"}
    ta = values["total_actifs"]
    assert Decimal(ta["value_normalized"]) == Decimal("1000") and ta["status"] == "verified"
    assert ta["value_original"] == "1000 (millions)" and ta["currency"] == "XOF"
    assert ta["provenance"]["page_number"] == 84 and ta["provenance"]["document_title"] == "Rapport annuel 2024"
    reasons = {u["metric_code"]: u["reason"] for u in d["unavailable"]}
    assert reasons == {"creances_clients": "needs_review", "capitaux_propres": "conflict",
                       "resultat_net": "rejected_only", "produit_net_bancaire": "missing"}
    # The provenance data_id resolves to the real record.
    detail = await api.get(f"/api/v1/financial-data/{ta['data_id']}")
    assert detail.status_code == 200 and detail.json()["page_number"] == 84


@pytest.mark.asyncio
async def test_financials_scope_and_period_are_separate(api: AsyncClient, pg_db: dict):
    cons = (await api.get(f"{base(pg_db)}/financials", params={"data_scope": "consolidated"})).json()
    assert [(v["metric_code"], Decimal(v["value_normalized"])) for v in cons["values"]] == [
        ("total_actifs", Decimal("9000"))]
    semi = (await api.get(f"{base(pg_db)}/financials", params={"period_type": "semi_annual"})).json()
    assert [(v["metric_code"], Decimal(v["value_normalized"])) for v in semi["values"]] == [
        ("total_actifs", Decimal("480"))]


@pytest.mark.asyncio
async def test_history_real_years_only_with_gap(api: AsyncClient, pg_db: dict):
    d = (await api.get(f"{base(pg_db)}/history", params={"indicator": "total_actifs"})).json()
    s = d["series"][0]
    assert [p["period_year"] for p in s["points"]] == [2021, 2022, 2024]  # no 2023 point, no zero
    assert s["missing_years"] == [2023] and s["currency"] == "XOF"


@pytest.mark.asyncio
async def test_ratios_existing_rules(api: AsyncClient, pg_db: dict):
    d = (await api.get(f"{base(pg_db)}/ratios", params={"period_year": 2024})).json()
    items = {i["ratio_code"]: i for i in d["items"]}
    assert items["DEPOTS_ACTIFS"]["value_percent"] == pytest.approx(60.0)
    assert items["ROA"]["value_percent"] is None and items["ROA"]["status"] == "unavailable"
    semi = (await api.get(f"{base(pg_db)}/ratios", params={"period_type": "semi_annual"})).json()
    assert semi["status"] == "unavailable" and semi["reason"] == "period_type_not_supported"


@pytest.mark.asyncio
async def test_growth_needs_both_periods(api: AsyncClient, pg_db: dict):
    g24 = (await api.get(f"{base(pg_db)}/growth", params={"period_year": 2024, "indicator": "total_actifs"})).json()
    assert g24["items"][0]["growth_percent"] is None  # 2023 absent: unavailable, never 0 %
    assert g24["items"][0]["status"] == "unavailable" and g24["status"] == "unavailable"
    g22 = (await api.get(f"{base(pg_db)}/growth", params={"period_year": 2022, "indicator": "total_actifs"})).json()
    assert g22["items"][0]["growth_percent"] == pytest.approx(6.25)


@pytest.mark.asyncio
async def test_coverage_quality_and_documents(api: AsyncClient, pg_db: dict):
    c = (await api.get(f"{base(pg_db)}/coverage")).json()
    assert c["available_years"] == [2021, 2022, 2024] and c["missing_years"] == [2023]
    assert (c["available_years_count"], c["expected_years_count"]) == (3, 4)
    assert c["coverage_ratio"] == pytest.approx(0.75)
    q = c["quality"]
    assert q["verified"] == 1 and q["rejected"] == 1 and q["needs_review"] == 1
    assert "score" not in str(c)
    assert [d["title"] for d in c["documents"]] == ["Rapport annuel 2024"]


@pytest.mark.asyncio
async def test_institution_without_data_is_unavailable(api: AsyncClient, pg_db: dict):
    f = (await api.get(f"{base(pg_db, 'B')}/financials")).json()
    assert f["status"] == "unavailable" and f["values"] == [] and f["period_year"] is None
    h = (await api.get(f"{base(pg_db, 'B')}/history")).json()
    assert h["status"] == "unavailable" and h["series"] == []
    c = (await api.get(f"{base(pg_db, 'B')}/coverage")).json()
    assert c["status"] == "unavailable" and c["coverage_ratio"] is None and c["documents"] == []


@pytest.mark.asyncio
async def test_unknown_institution_404(api: AsyncClient):
    for path in ("financials", "history", "ratios", "growth", "coverage"):
        r = await api.get(f"/api/v1/institutions/00000000-0000-0000-0000-000000000000/{path}")
        assert r.status_code == 404, path


@pytest.mark.asyncio
async def test_default_year_is_shared_by_key_figures_ratios_and_growth(api: AsyncClient, pg_db: dict):
    f = (await api.get(f"{base(pg_db)}/financials")).json()
    r = (await api.get(f"{base(pg_db)}/ratios")).json()
    g = (await api.get(f"{base(pg_db)}/growth")).json()
    assert f["period_year"] == r["period_year"] == g["period_year"] == 2024
    assert {i["period_year"] for i in r["items"]} == {2024}
    assert {i["current_year"] for i in g["items"]} == {2024}
