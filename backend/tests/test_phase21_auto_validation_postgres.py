"""
Phase 21 — automatic validation (reversible by a human) against a REAL PostgreSQL scratch database.

Two real PDF files are generated on the fly (a "fascicle" page and an "annual report" page) and stored
like the platform stores documents; every check re-reads them.
"""
from __future__ import annotations

import asyncio
import hashlib
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

M = Decimal(1_000_000)


def _pdf(path: Path, lines: list[str]) -> str:
    import pymupdf

    doc = pymupdf.open()
    page = doc.new_page()
    for i, line in enumerate(lines):
        page.insert_text((50, 60 + 18 * i), line, fontsize=10)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(path)
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="module")
def storage(tmp_path_factory) -> Path:
    return tmp_path_factory.mktemp("storage")


@pytest.fixture(scope="module")
def pg_db(storage) -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    test_db = f"{params['base_db']}_phase21_auto_pytest"
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"'))
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    ids = asyncio.run(_seed(_async_dsn(params, test_db), storage))
    yield {"url": _async_dsn(params, test_db), "ids": ids}
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str, storage: Path) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source
    from scraping.deals.importer import import_file

    h1 = _pdf(storage / "aa" / "fascicle.pdf", [
        "BANQUE A", "TOTAL DE L'ACTIF 1 234 567", "CREANCES SUR LA CLIENTELE 700 000", "CREANCES INTERBANCAIRES 300 000",
        "DETTES A L'EGARD DE LA CLIENTELE 900 000", "CAPITAUX PROPRES 150 000", "PRODUIT NET BANCAIRE 80 000"])
    h2 = _pdf(storage / "bb" / "report.pdf", ["Rapport annuel Banque A", "Total bilan 1 234 567"])
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        s1, s2 = (await db.execute(select(Source).order_by(Source.name).limit(2))).scalars().all()
        bank = Institution(name_official="BANQUE A", institution_type="bank", country_id=ci.id, status="active")
        d1 = Document(title="Fascicule", document_type="regulatory_report", source_id=s1.id, page_count=1,
                      file_hash=h1, storage_path="aa/fascicle.pdf", download_status="downloaded",
                      extraction_status="extracted")
        d2 = Document(title="Rapport annuel", document_type="annual_report", source_id=s2.id, page_count=1,
                      file_hash=h2, storage_path="bb/report.pdf", download_status="downloaded",
                      extraction_status="extracted")
        d3 = Document(title="Sans fichier", document_type="other", source_id=s1.id, page_count=3,
                      download_status="pending", extraction_status="pending")
        db.add_all([bank, d1, d2, d3])
        await db.flush()

        def obs(metric, raw, doc, year=2023, status="needs_review", cls="C", **kw):
            return FinancialData(
                institution_id=bank.id, source_id=doc.source_id, document_id=doc.id, metric_code=metric,
                scope="individual", period_type="annual", period_year=year, value_original=raw,
                unit_original="millions", currency_original="XOF",
                value_normalized=Decimal(raw.replace(" ", "")) * M, unit_normalized="absolute",
                currency_normalized="XOF", page_number=1, extraction_method="pdf_table", status=status,
                scope_evidence_class=cls, notes="scope not detected", **kw)

        rows = {
            "total_fasc": obs("total_actifs", "1 234 567", d1),
            "total_report": obs("total_actifs", "1 234 567", d2, cls="B"),
            "creances": obs("creances_clients", "700 000", d1),
            "depots": obs("depots_clients", "900 000", d1),
            "equity": obs("capitaux_propres", "150 000", d1, cls="D"),  # scope class D -> refused
            "pnb": obs("produit_net_bancaire", "80 000", d1),
            "not_printed": obs("depots_banques", "12 345", d1),  # value not on the page
            "no_file": obs("total_actifs", "999", d3, year=2021),
            "interbank": obs("creances_banques", "300 000", d1),  # printed, but 2022 is x300 000 lower
            "jump": obs("creances_banques", "1", d1, year=2022),  # not printed and inconsistent with 2023
        }
        db.add_all(rows.values())
        await db.commit()
        ids = {k: v.id for k, v in rows.items()} | {"bank": bank.id, "d1": d1.id, "d2": d2.id, "s1": s1.id,
                                                    "s2": s2.id}
    async with maker() as db:
        base = {"deal_type": "sovereign_bond", "country_code": "CI"}
        f = ["title", "deal_type", "country_code"]
        records = [
            {**base, "title": "OAT auto", "ingestion_key": "umoa_titres:CI:ADJ-1:CI0000000001:2025-01-10",
             "sources": [{"ref": "pdf", "document_id": ids["d1"], "source_id": ids["s1"], "page": 1, "fields": f},
                         {"ref": "page", "document_id": ids["d2"], "source_id": ids["s2"], "page": 1, "fields": []}],
             "participants": [{"role": "issuer", "name": "ETAT", "source_ref": "pdf"}]},
            {**base, "title": "Presse seule",
             "sources": [{"ref": "p", "document_id": ids["d2"], "source_id": ids["s2"], "page": 1, "fields": f,
                          "source_class": "press_reported", "publisher": "X", "url": "https://x.example"}]},
            {**base, "title": "Logo", "deal_type": "sovereign_bond_ape",
             "sources": [{"ref": "n", "document_id": ids["d1"], "source_id": ids["s1"], "page": 1, "fields": f,
                          "source_class": "primary_regulatory"}],
             "participants": [{"role": "arranger", "name": "SGI", "source_ref": "n", "extraction_method": "visual_logo"}]},
            {**base, "title": "Note seule", "deal_type": "sovereign_bond_ape",
             "sources": [{"ref": "n", "document_id": ids["d1"], "source_id": ids["s1"], "page": 1, "fields": f,
                          "source_class": "primary_regulatory"}],
             "participants": [{"role": "arranger", "name": "SGI", "source_ref": "n", "extraction_method": "text"}]},
        ]
        rep = await import_file(db, "d.json", json.dumps(records), actor="analyst-1")
        ids.update(dict(zip(("deal_oat", "deal_press", "deal_logo", "deal_note"), rep.created_ids, strict=True)))
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


async def rows(maker, model, ids):
    from sqlalchemy import select

    async with maker() as db:
        return {r.id: r for r in (await db.execute(select(model).where(model.id.in_(ids)))).scalars()}


@pytest.mark.asyncio
async def test_dry_run_changes_nothing(maker, pg_db, storage):
    from app.models.financial_data import FinancialData
    from scraping.validation.automatic import validate_financial_data

    async with maker() as db:
        report = await validate_financial_data(db, storage_root=storage, dry_run=True)
    assert report.examined == 10 and report.verified
    got = await rows(maker, FinancialData, list(pg_db["ids"].values()))
    assert {r.status for r in got.values()} == {"needs_review"}


@pytest.mark.asyncio
async def test_observations_validated_only_when_every_check_passes(maker, pg_db, storage):
    from app.models.financial_data import FinancialData
    from app.models.review_event import FinancialDataReviewEvent
    from scraping.validation.automatic import ACTOR, validate_financial_data

    i = pg_db["ids"]
    async with maker() as db:
        report = await validate_financial_data(db, storage_root=storage)
    got = await rows(maker, FinancialData, list(i.values()))
    # corroborated by an independent document -> verified (automatic)
    for k in ("total_fasc", "total_report"):
        assert (got[i[k]].status, got[i[k]].validation_method, got[i[k]].verified_by) == ("verified", "automatic", ACTOR)
    # single source, every check passes -> reviewed (automatic)
    for k in ("creances", "depots", "pnb"):
        assert (got[i[k]].status, got[i[k]].validation_method) == ("reviewed", "automatic"), k
    # refusals keep the status and explain why
    failed = {k: {c["check"] for c in got[i[k]].auto_validation["checks"] if c["result"] == "fail"}
              for k in ("equity", "not_printed", "no_file", "jump", "interbank")}
    assert failed["equity"] == {"scope_evidence"}
    assert failed["not_printed"] == {"source_text"}
    assert "source_text" in failed["no_file"]
    assert {"source_text", "time_series"} <= failed["jump"]
    assert failed["interbank"] == {"time_series"}
    for k in failed:
        assert got[i[k]].status == "needs_review" and got[i[k]].validation_method is None
    assert report.failures["scope_evidence"] == 1
    async with maker() as db:
        from sqlalchemy import func, select

        n = (await db.execute(select(func.count()).select_from(FinancialDataReviewEvent).where(
            FinancialDataReviewEvent.action == "auto_validate"))).scalar()
    assert n == 5


@pytest.mark.asyncio
async def test_a_human_withdraws_an_automatic_validation_and_the_robot_never_comes_back(api, maker, pg_db, storage):
    from app.models.financial_data import FinancialData
    from scraping.validation.automatic import validate_financial_data

    i = pg_db["ids"]
    body = {"actor": "analyst-1", "reason": "Je préfère relire ce chiffre"}
    r = await api.post(f"/api/v1/data-quality/{i['creances']}/revoke-automatic", json=body)
    assert r.status_code == 200
    assert (r.json()["status"], r.json()["validation_method"], r.json()["auto_validation_blocked"]) == \
        ("needs_review", None, True)
    assert r.json()["auto_validation"]["revoked_by"] == "analyst-1"
    # A human decision cannot be "revoked" as automatic
    assert (await api.post(f"/api/v1/data-quality/{i['equity']}/revoke-automatic", json=body)).status_code == 422
    async with maker() as db:
        await validate_financial_data(db, storage_root=storage)
    got = await rows(maker, FinancialData, [i["creances"]])
    assert got[i["creances"]].status == "needs_review"  # blocked: never re-validated automatically
    hist = (await api.get(f"/api/v1/data-quality/{i['creances']}/history")).json()
    assert [e["action"] for e in hist][-2:] in (["auto_validate", "revoke_automatic"],
                                                ["revoke_automatic", "auto_validate"])


@pytest.mark.asyncio
async def test_human_review_is_recorded_as_human(api, maker, pg_db):
    from app.models.financial_data import FinancialData

    i = pg_db["ids"]
    r = await api.post(f"/api/v1/data-quality/{i['equity']}/review", json={"actor": "analyst-1", "reason": "ok"})
    assert r.status_code == 200
    got = await rows(maker, FinancialData, [i["equity"]])
    assert (got[i["equity"]].status, got[i["equity"]].validation_method) == ("reviewed", "human")


@pytest.mark.asyncio
async def test_deals_validated_only_with_a_primary_source_and_text_roles(api, maker, pg_db):
    from app.models.deal import Deal
    from scraping.validation.automatic import validate_deals

    i = pg_db["ids"]
    async with maker() as db:
        await validate_deals(db)
    got = await rows(maker, Deal, [i["deal_oat"], i["deal_press"], i["deal_logo"], i["deal_note"]])
    assert (got[i["deal_oat"]].status, got[i["deal_oat"]].validation_method) == ("verified", "automatic")
    assert got[i["deal_note"]].status == "reviewed"  # one primary document: reviewed, not verified
    assert got[i["deal_press"]].status == "needs_review"
    assert {c["check"] for c in got[i["deal_press"]].auto_validation["checks"] if c["result"] == "fail"} == \
        {"primary_source"}
    assert got[i["deal_logo"]].status == "needs_review"
    d = (await api.get(f"/api/v1/deals/{i['deal_oat']}")).json()
    assert d["validation_method"] == "automatic" and d["auto_validation"]["outcome"] == "verified"
    r = await api.post(f"/api/v1/data-quality/deals/{i['deal_oat']}/revoke-automatic",
                       json={"actor": "analyst-1", "reason": "à relire"})
    assert r.status_code == 200 and r.json()["status"] == "needs_review"


@pytest.mark.asyncio
async def test_revoke_all_is_a_kill_switch(maker, pg_db):
    from sqlalchemy import func, select

    from app.models.financial_data import FinancialData
    from scraping.validation.automatic import RevokeError, revoke_all

    async with maker() as db:
        with pytest.raises(RevokeError):
            await revoke_all(db, actor="", reason="")
    async with maker() as db:
        counts = await revoke_all(db, actor="analyst-1", reason="Désactivation de la validation automatique")
    assert counts["financial_data"] == 4 and counts["deals"] == 1
    async with maker() as db:
        left = (await db.execute(select(func.count()).select_from(FinancialData).where(
            FinancialData.validation_method == "automatic"))).scalar()
    assert left == 0


def test_downgrade_0018_refused_while_traces_exist(pg_db):
    from alembic import command
    from alembic.config import Config as AlembicConfig

    backend = Path(__file__).resolve().parents[1]
    cfg = AlembicConfig(str(backend / "alembic.ini"))
    cfg.set_main_option("script_location", str(backend / "migrations"))
    with pytest.raises(RuntimeError, match="downgrade of 0018 refused"):
        command.downgrade(cfg, "0017_directory_and_mandates")
