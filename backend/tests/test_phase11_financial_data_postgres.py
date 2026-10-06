"""
Phase 11 — Financial data explorer against a REAL PostgreSQL database.

Same scratch-database mechanism as Phases 8C / 9 / 10 (never the dev database).

Seed (all individual annual XOF unless stated):
  Banque A (CI)  total_actifs 2024: 1000 verified p.84 + 990 extracted (superseded)
                 total_actifs 2023: 900
                 total_actifs 2024 consolidated: 9000 · 2024 semi_annual: 480
                 capitaux_propres 2024: 100 vs 130 (conflict)
                 resultat_net 2024: 55 rejected
  Banque B (SN)  total_actifs 2024: 700 · depots_clients 2024: 500
  Banque C (CI)  total_actifs 2024: 2 EUR (other currency, never converted)
                 depots_clients 2024: needs_review, value 300
"""
from __future__ import annotations

import asyncio
import csv
import io
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

URL = "/api/v1/financial-data"


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")

    test_db = f"{params['base_db']}_phase11_pytest"
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
    ids: dict[str, str] = {}
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()
        source = (await db.execute(select(Source))).scalars().first()
        insts = {
            "A": Institution(name_official="Banque A", institution_type="bank", country_id=ci.id, status="active"),
            "B": Institution(name_official="Banque B", institution_type="bank", country_id=sn.id, status="active"),
            "C": Institution(name_official="Banque C", institution_type="bank", country_id=ci.id, status="active"),
        }
        db.add_all(insts.values())
        await db.flush()
        docs = {}
        for k, inst in insts.items():
            docs[k] = Document(title=f"Rapport annuel {k}", document_type="annual_report", source_id=source.id,
                               institution_id=inst.id, download_status="downloaded", extraction_status="extracted")
            db.add(docs[k])
        await db.flush()

        def fd(k, metric, value, *, year=2024, scope="individual", period_type="annual", status="extracted",
               page=12, currency="XOF"):
            extra = {"verified_at": datetime.now(UTC), "verified_by": "analyst"} if status == "verified" else {}
            row = FinancialData(
                institution_id=insts[k].id, source_id=source.id, document_id=docs[k].id, metric_code=metric,
                scope=scope, period_type=period_type, period_year=year, value_original=f"{value}",
                unit_original="unit", currency_original=currency, value_normalized=Decimal(str(value)),
                unit_normalized="unit", currency_normalized=currency, extraction_method="pdf_table",
                status=status, page_number=page, **extra,
            )
            db.add(row)
            return row

        v = fd("A", "total_actifs", 1000, status="verified", page=84)
        fd("A", "total_actifs", 990)
        fd("A", "total_actifs", 900, year=2023)
        fd("A", "total_actifs", 9000, scope="consolidated")
        fd("A", "total_actifs", 480, period_type="semi_annual")
        fd("A", "capitaux_propres", 100)
        fd("A", "capitaux_propres", 130)
        fd("A", "resultat_net", 55, status="rejected")
        fd("B", "total_actifs", 700)
        fd("B", "depots_clients", 500)
        fd("C", "total_actifs", 2, currency="EUR")
        fd("C", "depots_clients", 300, status="needs_review")
        await db.commit()
        ids = {k: i.id for k, i in insts.items()} | {"verified": v.id, "source_name": source.name}
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


EXPLORER = {"period_type": "annual", "scope": "individual", "include_rejected": "false"}


async def items(api, **params):
    r = await api.get(URL, params={"page_size": 100, **params})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_country_and_year_filter(api: AsyncClient):
    d = await items(api, country_code="SN", period_year=2024, **EXPLORER)
    assert d["total"] == 2
    assert {(i["institution_name"], i["country_code"]) for i in d["items"]} == {("Banque B", "SN")}
    d23 = await items(api, country_code="CI", period_year=2023, **EXPLORER)
    assert [(i["institution_name"], Decimal(i["value_normalized"])) for i in d23["items"]] == [
        ("Banque A", Decimal("900"))]


@pytest.mark.asyncio
async def test_institution_and_indicator_filter_multi(api: AsyncClient, pg_db: dict):
    ids = f"{pg_db['ids']['A']},{pg_db['ids']['B']}"
    d = await items(api, institution_ids=ids, metric_code="total_actifs", period_year=2024, **EXPLORER)
    assert sorted(Decimal(i["value_normalized"]) for i in d["items"]) == [Decimal("700"), Decimal("990"),
                                                                         Decimal("1000")]
    assert {i["metric_code"] for i in d["items"]} == {"total_actifs"}


@pytest.mark.asyncio
async def test_period_type_and_scope_are_never_mixed(api: AsyncClient, pg_db: dict):
    base = {"institution_ids": pg_db["ids"]["A"], "metric_code": "total_actifs", "period_year": 2024}
    cons = await items(api, **base, period_type="annual", scope="consolidated")
    assert [(i["scope"], Decimal(i["value_normalized"])) for i in cons["items"]] == [("consolidated", Decimal("9000"))]
    semi = await items(api, **base, period_type="semi_annual", scope="individual")
    assert [(i["period_type"], Decimal(i["value_normalized"])) for i in semi["items"]] == [
        ("semi_annual", Decimal("480"))]
    ind = await items(api, **base, **EXPLORER)
    assert {(i["scope"], i["period_type"]) for i in ind["items"]} == {("individual", "annual")}


@pytest.mark.asyncio
async def test_currency_filter_and_value_sort_keeps_currencies_apart(api: AsyncClient):
    eur = await items(api, currency_normalized="EUR", **EXPLORER)
    assert [(i["institution_name"], i["currency_normalized"]) for i in eur["items"]] == [("Banque C", "EUR")]
    d = await items(api, metric_code="total_actifs", period_year=2024, sort="value", order="desc", **EXPLORER)
    cur = [i["currency_normalized"] for i in d["items"]]
    assert cur == sorted(cur)  # grouped by currency: EUR block, then XOF block — never interleaved
    xof = [Decimal(i["value_normalized"]) for i in d["items"] if i["currency_normalized"] == "XOF"]
    assert xof == sorted(xof, reverse=True)
    assert "total" not in {k for i in d["items"] for k in i if k.startswith("sum")}


@pytest.mark.asyncio
async def test_rejected_excluded_by_explorer_but_labelled_when_requested(api: AsyncClient, pg_db: dict):
    no = await items(api, institution_ids=pg_db["ids"]["A"], metric_code="resultat_net", **EXPLORER)
    assert no["total"] == 0 and no["items"] == []
    yes = await items(api, institution_ids=pg_db["ids"]["A"], metric_code="resultat_net", status="rejected")
    assert [(i["status"], i["qualification"]) for i in yes["items"]] == [("rejected", "rejected")]


@pytest.mark.asyncio
async def test_qualification_reuses_the_authority_rule(api: AsyncClient, pg_db: dict):
    d = await items(api, institution_ids=f"{pg_db['ids']['A']},{pg_db['ids']['C']}", period_year=2024, **EXPLORER)
    by = {(i["institution_name"], i["metric_code"], i["value_normalized"]): i for i in d["items"]}
    assert by[("Banque A", "total_actifs", "1000.000000")]["qualification"] == "authoritative"
    sup = by[("Banque A", "total_actifs", "990.000000")]
    assert sup["qualification"] == "superseded" and sup["authoritative_data_id"] == pg_db["ids"]["verified"]
    assert {by[("Banque A", "capitaux_propres", v)]["qualification"] for v in ("100.000000", "130.000000")} == {
        "conflict"}
    assert by[("Banque C", "depots_clients", "300.000000")]["qualification"] == "needs_review"


@pytest.mark.asyncio
async def test_pagination_total_and_pages(api: AsyncClient):
    p1 = (await api.get(URL, params={"page": 1, "page_size": 3, "sort": "institution", **EXPLORER})).json()
    p2 = (await api.get(URL, params={"page": 2, "page_size": 3, "sort": "institution", **EXPLORER})).json()
    allr = await items(api, sort="institution", **EXPLORER)
    assert p1["total"] == p2["total"] == allr["total"] == 9
    assert p1["has_next"] and not p1["has_prev"] and p2["has_prev"]
    assert [i["id"] for i in p1["items"] + p2["items"]] == [i["id"] for i in allr["items"][:6]]


@pytest.mark.asyncio
async def test_empty_selection(api: AsyncClient):
    d = await items(api, country_code="BJ", **EXPLORER)
    assert d == {"items": [], "total": 0, "page": 1, "page_size": 100, "has_next": False, "has_prev": False}


@pytest.mark.asyncio
async def test_provenance_summary_resolves_to_the_record(api: AsyncClient, pg_db: dict):
    d = await items(api, institution_ids=pg_db["ids"]["A"], status="verified")
    row = d["items"][0]
    assert row["page_number"] == 84 and row["document_title"] == "Rapport annuel A"
    assert row["source_name"] == pg_db["ids"]["source_name"]
    detail = (await api.get(f"{URL}/{row['id']}")).json()
    assert detail["page_number"] == 84 and detail["document_id"] == row["document_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("sort", ["institution", "country", "indicator", "year", "value"])
async def test_sort_is_deterministic(api: AsyncClient, sort: str):
    runs = [[i["id"] for i in (await items(api, sort=sort, order="desc"))["items"]] for _ in range(3)]
    assert runs[0] == runs[1] == runs[2] and len(runs[0]) == 12


@pytest.mark.asyncio
async def test_backward_compatible_default_listing(api: AsyncClient):
    d = await items(api)
    assert d["total"] == 12  # rejected still listed by default for existing callers
    assert (await api.get(URL, params={"status": "rejected", "page_size": 1})).json()["total"] == 1


@pytest.mark.asyncio
async def test_export_same_filters_rejected_excluded(api: AsyncClient):
    r = await api.get(f"{URL}/export", params={"period_type": "annual", "scope": "individual"})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(r.text)))
    assert len(rows) == 9 and "rejected" not in {x["status"] for x in rows}
    eur = [x for x in rows if x["currency"] == "EUR"]
    assert [(x["institution"], x["value_normalized"]) for x in eur] == [("Banque C", "2.000000")]
    sn = await api.get(f"{URL}/export", params={"country_code": "SN", **EXPLORER})
    assert len(list(csv.DictReader(io.StringIO(sn.text)))) == 2


@pytest.mark.asyncio
async def test_export_refused_above_limit(api: AsyncClient, monkeypatch):
    import app.services.financial_data as svc

    monkeypatch.setattr(svc, "EXPORT_MAX_ROWS", 3)
    r = await api.get(f"{URL}/export", params=EXPLORER)
    assert r.status_code == 413 and r.json()["error"]["message"].startswith("export_too_large")


@pytest.mark.asyncio
async def test_facets_list_only_stored_values(api: AsyncClient):
    f = (await api.get(f"{URL}/facets")).json()
    assert f["currencies"] == ["EUR", "XOF"]
    assert f["period_years"] == [2024, 2023]
    assert f["scopes"] == ["consolidated", "individual"]
    assert f["period_types"] == ["annual", "semi_annual"]
    assert f["statuses"] == ["extracted", "needs_review", "rejected", "verified"]
    assert "total_actifs" in f["metric_codes"] and "produit_net_bancaire" not in f["metric_codes"]


@pytest.mark.asyncio
async def test_explorer_indexes_exist(pg_db: dict):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(pg_db["url"])
    async with engine.connect() as conn:
        names = set((await conn.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 'financial_data'"))).scalars())
    await engine.dispose()
    assert {"ix_financial_data_period_scope_year", "ix_financial_data_logical_key",
            "ix_financial_data_currency_value"} <= names


@pytest.mark.asyncio
@pytest.mark.parametrize("page_size", [2, 12])
async def test_constant_query_count_and_no_full_document_load(pg_db: dict, page_size: int):
    """No N+1: count + page + sibling lookup (+ its 2 selectin loads), whatever the page size;
    the heavy document columns (storage path, hash…) are never selected."""
    from sqlalchemy import event
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.services.financial_data import get_financial_data

    engine = create_async_engine(pg_db["url"])
    statements: list[str] = []
    event.listen(engine.sync_engine, "before_cursor_execute",
                 lambda conn, cursor, stmt, params, ctx, many: statements.append(stmt))
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        res = await get_financial_data(db, page_size=page_size, period_type="annual", scope="individual",
                                       include_rejected=False)
    await engine.dispose()
    assert len(res.items) == min(page_size, 9)
    selects = [s for s in statements if s.lstrip().upper().startswith("SELECT")]
    assert len(selects) == 5, selects
    assert not any("documents.file_hash" in s or "documents.storage_path" in s for s in selects)
