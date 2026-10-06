"""Phase 19 — pilot loader (controlled entry) against a REAL PostgreSQL scratch database."""
from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from pathlib import Path

import pytest

from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

ARTICLE = """<html><body><script>var x=1;</script><p>Arrangeurs et Chefs de File : SGCS et FGI</p>
<p>Investisseur de r&eacute;f&eacute;rence : Soci&eacute;t&eacute; G&eacute;n&eacute;rale C&ocirc;te d&rsquo;Ivoire</p>
<p>Social Bond de 40 milliards FCFA</p></body></html>"""


def manifest(excerpt: str = "Investisseur de référence : Société Générale Côte d'Ivoire") -> dict:
    return {
        "sources": [{"key": "eco", "name": "Agence Ecofin", "url": "https://www.agenceecofin.com",
                     "source_type": "secondary", "priority": 3}],
        "documents": [{"key": "a", "source": "eco", "title": "Article", "document_type": "web_page",
                       "url": "https://www.agenceecofin.com/a", "local_file": "a.html", "page_count": 1}],
        "deals": [{
            "key": "T1", "title": "AFINHAB Social Bond", "deal_type": "corporate_bond_ape", "amount": "40000000000",
            "currency": "XOF", "unit": "units",
            "sources": [{"ref": "eco", "document": "a", "page": 1, "source_class": "press_reported",
                         "publisher": "Agence Ecofin", "url": "https://www.agenceecofin.com/a",
                         "excerpt": "Social Bond de 40 milliards FCFA",
                         "fields": ["title", "deal_type", "amount", "currency", "unit"]}],
            "participants": [
                {"role": "arranger", "name": "SGCS", "source_ref": "eco", "excerpt": "Arrangeurs et Chefs de File"},
                {"role": "anchor_investor", "name": "Société Générale Côte d'Ivoire", "source_ref": "eco",
                 "excerpt": excerpt, "institution_name": "SOCIETE GENERALE COTE D'IVOIRE"},
                {"role": "lender", "name": "Banque Inconnue", "source_ref": "eco", "excerpt": "SGCS et FGI",
                 "institution_name": "BANQUE INCONNUE"},
            ],
        }],
        "institution_links": [
            {"from_name": "SGI X", "link_level": "documented_bank", "relation": "subsidiary",
             "to_institution_name": "BANQUE ABSENTE", "source_url": "https://x.example", "excerpt": "filiale",
             "observed_at": "2026-10-05"},
            {"from_name": "SGI Y", "link_level": "documented_group_only", "relation": "subsidiary",
             "group_label": "Groupe Y", "source_url": "https://y.example", "excerpt": "filiale du groupe Y",
             "observed_at": "2026-10-05"},
        ],
    }


@pytest.fixture(scope="module")
def pg_db() -> Generator[str, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    test_db = f"{params['base_db']}_phase19_pilot_pytest"
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"'))
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    asyncio.run(_seed(_async_dsn(params, test_db)))
    yield _async_dsn(params, test_db)
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str) -> None:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.models.country import Country
    from app.models.institution import Institution

    engine = create_async_engine(url)
    async with async_sessionmaker(engine)() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        db.add(Institution(name_official="SOCIETE GENERALE COTE D'IVOIRE", institution_type="bank",
                           country_id=ci.id, status="active"))
        await db.commit()
    await engine.dispose()


async def _run(url: str, m: dict, files: Path, *, dry_run: bool = False):
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.deals.pilot_load import load

    engine = create_async_engine(url)
    try:
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            return await load(db, m, files_root=files, actor="analyst-1", dry_run=dry_run)
    finally:
        await engine.dispose()


async def _scalar(url: str, sql: str):
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return (await conn.execute(text(sql))).scalar()
    finally:
        await engine.dispose()


def test_a_quotation_missing_from_its_page_refuses_everything(pg_db, tmp_path):
    from app.deals.pilot_load import PilotError

    (tmp_path / "a.html").write_text(ARTICLE, encoding="utf-8")
    with pytest.raises(PilotError, match="quotation not found"):
        asyncio.run(_run(pg_db, manifest("Investisseur de référence : BICICI"), tmp_path))
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM deals")) == 0
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM documents WHERE url LIKE '%agenceecofin%'")) == 0


def test_dry_run_writes_nothing(pg_db, tmp_path):
    (tmp_path / "a.html").write_text(ARTICLE, encoding="utf-8")
    report = asyncio.run(_run(pg_db, manifest(), tmp_path, dry_run=True))
    assert report.quotations_checked == 4 and len(report.deals_created) == 1
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM deals")) == 0
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM institution_links")) == 0


def test_load_resolves_exact_names_only_and_is_idempotent(pg_db, tmp_path):
    (tmp_path / "a.html").write_text(ARTICLE, encoding="utf-8")
    report = asyncio.run(_run(pg_db, manifest(), tmp_path))
    assert len(report.deals_created) == 1 and report.documents_created == 1
    assert sorted(set(report.unresolved_names)) == ["BANQUE ABSENTE", "BANQUE INCONNUE"]
    assert report.links_created == 1 and report.links_skipped == 1  # never a documented_bank without the bank
    assert asyncio.run(_scalar(pg_db, "SELECT status FROM deals")) == "needs_review"
    assert asyncio.run(_scalar(pg_db, "SELECT ingestion_key FROM deals")) == "pilot:T1"
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM deal_participants WHERE institution_id IS NOT NULL")) == 1
    assert asyncio.run(_scalar(pg_db, "SELECT file_hash IS NOT NULL FROM documents WHERE url LIKE '%agenceecofin%'"))
    again = asyncio.run(_run(pg_db, manifest(), tmp_path))
    assert again.deals_skipped == ["T1"] and again.links_created == 0 and again.documents_created == 0
    assert asyncio.run(_scalar(pg_db, "SELECT count(*) FROM deals")) == 1


def test_the_shipped_manifest_is_valid():
    """pilot/pilot_manifest.json stays in sync with build_manifest.py and passes the import schema."""
    import json

    from scraping.deals.schemas import DealImportRecord

    root = Path(__file__).resolve().parents[1] / "pilot"
    m = json.loads((root / "pilot_manifest.json").read_text(encoding="utf-8"))
    docs = {d["key"] for d in m["documents"]}
    assert len(m["deals"]) == 13
    for deal in m["deals"]:
        rec = {k: v for k, v in deal.items() if k not in ("key", "case")}
        rec["sources"] = [{**{k: v for k, v in s.items() if k != "document"}, "document_id": "x", "source_id": "y"}
                          for s in deal["sources"]]
        assert all(s["document"] in docs for s in deal["sources"])
        rec["participants"] = [{k: v for k, v in p.items() if k != "institution_name"} for p in deal["participants"]]
        DealImportRecord.model_validate(rec)
