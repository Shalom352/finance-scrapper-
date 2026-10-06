"""
Phase 19 — deal sourcing (migration 0016) against a REAL PostgreSQL database.

Scratch database, never the dev database. Covers: new types / roles / provenance fields,
source classes, the press-only verification guard (409), institution_links constraints and
the downgrade refusal while the new vocabulary is used.
"""
from __future__ import annotations

import asyncio
import json
import os
from collections.abc import AsyncGenerator, Generator
from datetime import date

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

DQ = "/api/v1/data-quality"


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    test_db = f"{params['base_db']}_phase19_sourcing_pytest"
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

    from app.models.country import Country
    from app.models.document import Document
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()
        s1, s2 = (await db.execute(select(Source).order_by(Source.name).limit(2))).scalars().all()
        sgsn = Institution(name_official="SOCIETE GENERALE SENEGAL", institution_type="bank", country_id=sn.id,
                           status="active")
        db.add(sgsn)
        note = Document(title="Note d'information APE SN 2025", document_type="other", source_id=s1.id,
                        page_count=60, download_status="downloaded", extraction_status="skipped")
        article = Document(title="Article de presse", document_type="web_page", source_id=s2.id, page_count=1,
                           download_status="downloaded", extraction_status="skipped")
        db.add_all([note, article])
        await db.commit()
        ids = {"sgsn": sgsn.id, "s1": s1.id, "s2": s2.id, "note": note.id, "article": article.id}
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
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app = create_app()
    app.dependency_overrides[get_db_session] = override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        yield client


async def do_import(maker, records: list[dict]):
    from scraping.deals.importer import import_file

    async with maker() as db:
        return await import_file(db, "pilot.json", json.dumps(records, default=str), actor="analyst-1")


def _press(i: dict) -> dict:
    return {"ref": "p", "document_id": i["article"], "source_id": i["s2"], "page": 1,
            "source_class": "press_reported", "publisher": "Sika Finance",
            "url": "https://www.sikafinance.com/marches/x", "published_at": "2024-12-13",
            "excerpt": "Arrangée par SGI Niger qui en est le chef de file", "fields": ["title", "deal_type"]}


@pytest.mark.asyncio
async def test_import_note_with_named_roles_use_of_proceeds_and_filing_agent(api, maker, pg_db):
    i = pg_db["ids"]
    note = {"ref": "n", "document_id": i["note"], "source_id": i["s1"], "page": 52,
            "source_class": "primary_regulatory",
            "excerpt": "Co-arrangeur : Société Générale Sénégal",
            "fields": ["title", "deal_type", "country_code", "use_of_proceeds", "use_of_proceeds_categories"]}
    report = await do_import(maker, [{
        "title": "État du Sénégal — APE juin 2025", "deal_type": "sovereign_bond_ape", "country_code": "SN",
        "use_of_proceeds": "financer les besoins de trésorerie prévus dans la Loi de Finances 2025",
        "use_of_proceeds_categories": ["budget_financing"],
        "sources": [note],
        "participants": [
            {"role": "arranger", "name": "CGF Bourse", "source_ref": "n", "page": 15, "extraction_method": "text"},
            {"role": "lead_manager", "name": "CGF Bourse", "source_ref": "n", "page": 15, "extraction_method": "text"},
            {"role": "co_arranger", "name": "Société Générale Sénégal", "institution_id": i["sgsn"],
             "source_ref": "n", "page": 52, "excerpt": "Co-arrangeur", "extraction_method": "text"},
            {"role": "placement_syndicate_member", "name": "ABCO Bourse", "source_ref": "n", "page": 16},
        ],
    }])
    deal_id = report.created_ids[0]
    d = (await api.get(f"/api/v1/deals/{deal_id}")).json()
    assert d["status"] == "needs_review"
    assert d["use_of_proceeds_categories"] == ["budget_financing"] and d["filing_agent_raw"] is None
    assert d["sources"][0]["source_class"] == "primary_regulatory"
    roles = sorted((p["role"], p["page_number"]) for p in d["participants"])
    assert roles == [("arranger", 15), ("co_arranger", 52), ("lead_manager", 15), ("placement_syndicate_member", 16)]
    assert set(d["field_provenance"]) >= {"use_of_proceeds", "use_of_proceeds_categories"}
    pg_db["ids"]["primary_deal"] = deal_id


@pytest.mark.asyncio
async def test_press_only_deal_cannot_be_verified_until_a_primary_source_exists(api, maker, pg_db):
    i = pg_db["ids"]
    report = await do_import(maker, [{"title": "Niger 200 Md (presse)", "deal_type": "sovereign_bond_ape",
                                      "sources": [_press(i)],
                                      "participants": [{"role": "arranger", "name": "SGI Niger", "source_ref": "p"}]}])
    deal_id = report.created_ids[0]
    body = {"actor": "analyst-1", "reason": "Lu dans l'article"}
    assert (await api.post(f"{DQ}/deals/{deal_id}/review", json=body)).status_code == 200
    r = await api.post(f"{DQ}/deals/{deal_id}/verify", json=body)
    assert r.status_code == 409 and "secondary_source_only" in r.text
    # A deal with a primary source verifies normally (review first).
    primary = pg_db["ids"]["primary_deal"]
    assert (await api.post(f"{DQ}/deals/{primary}/review", json=body)).status_code == 200
    assert (await api.post(f"{DQ}/deals/{primary}/verify", json=body)).status_code == 200


@pytest.mark.asyncio
async def test_institution_links_two_levels_are_enforced(maker, pg_db):
    from sqlalchemy.exc import IntegrityError

    from app.models.deal import InstitutionLink

    i = pg_db["ids"]
    common = {"relation": "subsidiary", "source_url": "https://www.bicibourse.ci/nous-connaitre/bici-bourse/",
              "excerpt": "Sa filiation à la BICICI", "observed_at": date(2026, 10, 5)}
    async with maker() as db:
        db.add(InstitutionLink(from_name="BICI BOURSE", link_level="documented_bank", to_institution_id=i["sgsn"],
                               pct=70, **common))
        db.add(InstitutionLink(from_name="CORIS BOURSE", link_level="documented_group_only",
                               group_label="Groupe Coris", **common))
        await db.commit()
    for bad in (
        {"link_level": "documented_group_only", "to_institution_id": i["sgsn"], "group_label": "Groupe X"},
        {"link_level": "documented_bank", "group_label": "Groupe X"},
    ):
        async with maker() as db:
            db.add(InstitutionLink(from_name="SGI X", **bad, **common))
            with pytest.raises(IntegrityError):
                await db.commit()


def test_downgrade_is_refused_while_new_vocabulary_is_used(pg_db):
    from alembic import command
    from alembic.config import Config as AlembicConfig

    from tests.test_migration_postgres_phase2 import BACKEND_DIR

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    with pytest.raises(RuntimeError, match="downgrade of 0016 refused"):
        command.downgrade(cfg, "0015_deal_validation_flags")
