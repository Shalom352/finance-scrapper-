"""
Phase 20 — financing directory, internal mandates and targeting against a REAL PostgreSQL database.

Seed: SG CI (CI, equity 120 bn XOF needs_review 2024 + 100 bn verified 2023), Banque Sénégal (SN, no data),
Banque Togo (TG, a lender on a CI energy project). Directory seed from reference/financing_institutions.json.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from pathlib import Path

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

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    test_db = f"{params['base_db']}_phase20_targeting_pytest"
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"'))
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

    from app.directory.seed import seed
    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source
    from scraping.deals.importer import import_file

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        c = {k: (await db.execute(select(Country).where(Country.code == k))).scalar_one().id for k in ("CI", "SN", "TG")}
        src = (await db.execute(select(Source).order_by(Source.name).limit(1))).scalar_one()
        sgci = Institution(name_official="SOCIETE GENERALE COTE D'IVOIRE", institution_type="bank", country_id=c["CI"],
                           status="active")
        bsn = Institution(name_official="BANQUE SENEGAL", institution_type="bank", country_id=c["SN"], status="active")
        btg = Institution(name_official="BANQUE TOGO", institution_type="bank", country_id=c["TG"], status="active")
        bml = Institution(name_official="BANQUE MALI", institution_type="bank", country_id=c["TG"], status="active")
        doc = Document(title="Note", document_type="other", source_id=src.id, page_count=20,
                       download_status="downloaded", extraction_status="skipped")
        db.add_all([sgci, bsn, btg, bml, doc])
        await db.flush()
        for year, value, status in ((2024, "120000000000", "needs_review"), (2023, "100000000000", "verified")):
            db.add(FinancialData(institution_id=sgci.id, source_id=src.id, document_id=doc.id,
                                 metric_code="capitaux_propres", scope="individual", period_type="annual",
                                 period_year=year, value_original=value, value_normalized=Decimal(value),
                                 unit_normalized="absolute", currency_original="XOF", currency_normalized="XOF",
                                 status=status, extraction_method="manual",
                                 **({"verified_at": __import__("datetime").datetime(2026, 1, 1),
                                     "verified_by": "analyst"} if status == "verified" else {})))
        await db.commit()
        ids = {"sgci": sgci.id, "bsn": bsn.id, "btg": btg.id, "doc": doc.id, "src": src.id}
    entries = json.loads((BACKEND / "reference" / "financing_institutions.json").read_text(encoding="utf-8"))
    async with maker() as db:
        report = await seed(db, entries["institutions"])
        assert len(report.created) == len(entries["institutions"])
    async with maker() as db:
        from app.models.entity import Entity

        boad = (await db.execute(select(Entity).where(Entity.short_name == "BOAD"))).scalar_one()
        ids["boad"] = boad.id
        s = {"ref": "s", "document_id": ids["doc"], "source_id": ids["src"], "page": 3,
             "source_class": "primary_regulatory", "fields": ["title", "deal_type", "country_code", "sector"]}
        records = [
            {"title": "Centrale solaire CI", "deal_type": "project_finance", "country_code": "CI", "sector": "energy",
             "sources": [s], "participants": [
                 {"role": "lender", "name": "BANQUE TOGO", "institution_id": btg.id, "source_ref": "s"},
                 {"role": "lender", "name": "BOAD", "entity_id": boad.id, "source_ref": "s"},
                 {"role": "borrower", "name": "SPV Solaire", "source_ref": "s"}]},
            {"title": "Prêt agricole SN", "deal_type": "term_loan", "country_code": "SN", "sector": "agriculture",
             "sources": [s], "participants": [{"role": "borrower", "name": "BANQUE SENEGAL",
                                               "institution_id": bsn.id, "source_ref": "s"}]},
        ]
        await import_file(db, "seed.json", json.dumps(records), actor="analyst-1")
    await engine.dispose()
    return ids


@pytest_asyncio.fixture
async def maker(pg_db: dict):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(pg_db["url"])
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest_asyncio.fixture
async def api(maker) -> AsyncGenerator[AsyncClient, None]:
    from app.db.session import get_db_session
    from app.main import create_app

    async def override() -> AsyncGenerator:
        async with maker() as session:
            yield session

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


@pytest.mark.asyncio
async def test_directory_seed_is_idempotent_and_never_touches_existing_entities(maker):
    from app.directory.seed import seed, validate

    entries = json.loads((BACKEND / "reference" / "financing_institutions.json").read_text(encoding="utf-8"))
    async with maker() as db:
        report = await seed(db, entries["institutions"])
    assert report.created == [] and "BOAD" in report.existing
    with pytest.raises(ValueError, match="official https website"):
        validate([{"canonical_name": "X", "short_name": "X", "entity_type": "development_bank", "website": "x"}])


@pytest.mark.asyncio
async def test_mandate_import_resolves_exact_names_and_keeps_history(maker, pg_db):
    from app.mandates.importer import (
        ContactRow,
        MandateImportError,
        MandateRow,
        import_mandates,
        parse_csv,
    )

    mandates = parse_csv(
        "code,title,client_name,country_code,sector,deal_type,amount,currency,year\n"
        "IVC-2025,Campagne cotonnière,Ivoire Coton,CI,agriculture,trade_finance,15000000000,XOF,2025\n", MandateRow)
    contacts = parse_csv(
        "mandate_code,counterparty_name,institution_name,entity_name,stage,contact_date\n"
        "IVC-2025,SG CI,SOCIETE GENERALE COTE D'IVOIRE,,approached,2025-03-01\n"
        "IVC-2025,SG CI,SOCIETE GENERALE COTE D'IVOIRE,,term_sheet,2025-04-10\n"
        "IVC-2025,Banque Sénégal,BANQUE SENEGAL,,declined,2025-03-05\n"
        "IVC-2025,BOAD,,BOAD,interested,2025-03-20\n", ContactRow)
    async with maker() as db:
        r = await import_mandates(db, mandates, contacts, actor="analyst-1")
    assert (r.mandates_created, r.contacts_created) == (1, 4)
    async with maker() as db:
        again = await import_mandates(db, mandates, contacts, actor="analyst-1")
    assert (again.mandates_updated, again.contacts_created, again.contacts_skipped) == (1, 0, 4)
    bad = parse_csv("mandate_code,counterparty_name,institution_name,stage\nIVC-2025,X,SG CI,approached\n", ContactRow)
    async with maker() as db:
        with pytest.raises(MandateImportError, match="not found exactly once"):
            await import_mandates(db, [], bad, actor="analyst-1")
    with pytest.raises(MandateImportError, match="currency is required"):
        parse_csv("code,title,client_name,amount\nX,T,C,10\n", MandateRow)


@pytest.mark.asyncio
async def test_targeting_lists_criteria_with_evidence_and_no_score(api, pg_db):
    i = pg_db["ids"]
    r = await api.get("/api/v1/targeting", params={"country": "CI", "sector": "energy", "deal_type": "project_finance",
                                                   "amount": "20000000000", "currency": "XOF"})
    assert r.status_code == 200
    body = r.json()
    assert all("score" not in c for c in body["items"])  # no hidden score field
    by_id = {c["id"]: c for c in body["items"]}
    sg = by_id[i["sgci"]]["criteria"]
    assert sg["presence"]["status"] == "met"
    # latest equity is 2024 (needs_review) -> ceiling 30 bn, flagged to confirm; never 2023 silently
    assert sg["capacity"]["status"] == "met" and sg["capacity"]["equity_year"] == 2024
    assert Decimal(str(sg["capacity"]["indicative_ceiling"])) == Decimal("30000000000")
    assert sg["capacity"]["to_confirm"] is True
    assert sg["relationship"]["status"] == "met" and sg["relationship"]["history"][0]["stage"] == "term_sheet"
    assert sg["experience"]["status"] == "unknown"  # no recorded participation: unknown, not a refusal
    tg = by_id[i["btg"]]["criteria"]  # Togo bank: not in CI, but lender on a comparable CI energy project
    assert tg["presence"]["status"] == "not_met" and tg["experience"]["status"] == "met"
    assert tg["experience"]["deals"][0]["matches"] == ["sector", "deal_type", "country"]
    assert tg["experience"]["to_confirm"] == 1  # the deal is needs_review
    assert i["bsn"] in by_id and by_id[i["bsn"]]["criteria"]["relationship"]["declined"] == 1
    # The borrower role is not a financing role: Banque Sénégal has no experience
    assert by_id[i["bsn"]]["criteria"]["experience"]["status"] == "unknown"
    boad = by_id[i["boad"]]["criteria"]
    assert boad["presence"]["status"] == "met" and boad["experience"]["comparable_deals"] == 1
    assert boad["capacity"]["status"] == "unknown"
    # A bank of another country with nothing on record is not listed
    names = [c["name"] for c in body["items"]]
    assert "BANQUE MALI" not in names
    # Order: number of criteria met (no hidden weighting)
    mets = [c["criteria_met"] for c in body["items"]]
    assert mets == sorted(mets, reverse=True)


@pytest.mark.asyncio
async def test_capacity_never_converts_currencies_and_amount_above_ceiling_is_not_met(api, pg_db):
    i = pg_db["ids"]
    eur = (await api.get("/api/v1/targeting", params={"country": "CI", "amount": "1000", "currency": "EUR",
                                                      "kind": "banks"})).json()
    sg = {c["id"]: c for c in eur["items"]}[i["sgci"]]["criteria"]["capacity"]
    assert sg == {"status": "unknown", "reason": "currency_mismatch", "equity_currency": "XOF"}
    big = (await api.get("/api/v1/targeting", params={"country": "CI", "amount": "50000000000", "currency": "XOF",
                                                      "kind": "banks"})).json()
    assert {c["id"]: c for c in big["items"]}[i["sgci"]]["criteria"]["capacity"]["status"] == "not_met"


@pytest.mark.asyncio
async def test_mandates_endpoint(api):
    rows = (await api.get("/api/v1/mandates")).json()
    assert rows[0]["code"] == "IVC-2025" and len(rows[0]["counterparties"]) == 4


def test_downgrade_0017_refused_while_mandates_exist(pg_db):
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    with pytest.raises(RuntimeError, match="downgrade of 0017 refused"):
        command.downgrade(cfg, "0016_deal_sourcing_roles")


@pytest.mark.asyncio
async def test_directory_resolution_is_exact_after_typographic_normalization(maker, pg_db):
    from app.directory.resolve import resolve_names

    i = pg_db["ids"]
    async with maker() as db:
        got = await resolve_names(db, {"Société Générale Côte d’Ivoire", "Société Générale", "BOAD",
                                       "Banque Ouest Africaine de Développement", "BANQUE"})
    assert got["Société Générale Côte d’Ivoire"].institution_id == i["sgci"]  # accents / apostrophe only
    assert got["BOAD"].entity_id == got["Banque Ouest Africaine de Développement"].entity_id == i["boad"]
    assert "Société Générale" not in got and "BANQUE" not in got  # never a partial match
