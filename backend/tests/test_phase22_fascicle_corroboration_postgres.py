"""
Phase 22 — institution-document rows without a stated unit / scope proof, corroborated by the BCEAO
fascicle (same institution, metric, year), against a REAL PostgreSQL scratch database.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.constants.quality import FASCICLE_CONVENTION_REASON
from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _exec_admin,
    _reachable,
    _run_alembic,
    _server_params,
)

M = Decimal(1_000_000)


@pytest.fixture(scope="module")
def pg_db() -> Generator[dict, None, None]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    test_db = f"{params['base_db']}_phase22_corrob_pytest"
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)', f'CREATE DATABASE "{test_db}"'))
    os.environ["DATABASE_URL"] = _async_dsn(params, test_db)
    from app.core.config import get_settings

    get_settings.cache_clear()
    _run_alembic("upgrade")
    url = _async_dsn(params, test_db)
    ids = asyncio.run(_seed(url))
    yield {"url": url, "ids": ids}
    os.environ.pop("DATABASE_URL", None)
    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{test_db}" WITH (FORCE)'))


async def _seed(url: str) -> dict[str, str]:
    from app.models.country import Country
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution
    from app.models.source import Source

    engine = create_async_engine(url)
    async with async_sessionmaker(engine, expire_on_commit=False)() as db:
        bj = (await db.execute(select(Country).where(Country.code == "BJ"))).scalar_one()
        src = (await db.execute(select(Source).order_by(Source.name).limit(1))).scalar_one()
        bank = Institution(name_official="FIXTURE BANK BENIN", institution_type="bank", country_id=bj.id,
                           status="active")
        fasc = Document(title="Fascicule", document_type="regulatory_report", source_id=src.id, page_count=1,
                        download_status="downloaded", extraction_status="extracted",
                        document_scope="regulatory_aggregate")
        synoptic = Document(title="Bilan et Compte de résultat", document_type="annual_report", source_id=src.id,
                            page_count=1, download_status="downloaded", extraction_status="extracted",
                            document_scope="institution_specific")
        db.add_all([bank, fasc, synoptic])
        await db.flush()

        def fascicle(metric: str, millions: str) -> FinancialData:
            return FinancialData(
                institution_id=bank.id, source_id=src.id, document_id=fasc.id, metric_code=metric, scope="individual",
                period_type="annual", period_year=2022, value_original=millions, unit_original="millions",
                currency_original="XOF", value_normalized=Decimal(millions.replace(" ", "")) * M,
                unit_normalized="absolute", currency_normalized="XOF", page_number=33,
                extraction_method="pdf_text", status="reviewed", scope_evidence_class="C",
                scope_reason_code=FASCICLE_CONVENTION_REASON)

        def synoptic_row(metric: str, raw: str, status: str = "needs_review") -> FinancialData:
            return FinancialData(
                institution_id=bank.id, source_id=src.id, document_id=synoptic.id, metric_code=metric,
                scope="individual", period_type="annual", period_year=2022, value_original=raw,
                unit_original=None, currency_original=None, value_normalized=None, page_number=1,
                extraction_method="pdf_text", status=status, scope_evidence_class="D",
                scope_reason_code="scope_not_stated",
                quality_flags=[{"code": "unit_or_currency_not_stated", "detail": "p.1: not stated"}])

        rows = {
            "f_pnb": fascicle("produit_net_bancaire", "46 414"),
            "f_cash": fascicle("creances_clients", "305 260"),
            "f_dep": fascicle("depots_clients", "500 000"),
            "f_rex": fascicle("resultat_exploitation", "23 198"),
            "pnb": synoptic_row("produit_net_bancaire", "46 412 884 468"),  # rounding gap 1.1 M -> agrees
            "cash": synoptic_row("creances_clients", "305 259 732 459"),
            "dep": synoptic_row("depots_clients", "512 000 000 000"),  # 2.4 % off -> disagreement
            "orphan": synoptic_row("resultat_net", "19 143 162 703"),  # no fascicle value -> untouched
            "human": synoptic_row("resultat_exploitation", "23 196 758 789", status="rejected"),
        }
        db.add_all(rows.values())
        await db.commit()
        out = {k: v.id for k, v in rows.items()}
    await engine.dispose()
    return out


def _run(url: str, dry_run: bool):
    from scraping.universe.unit_repair import corroborate_with_fascicle

    async def go():
        engine = create_async_engine(url)
        async with async_sessionmaker(engine, expire_on_commit=False)() as db:
            report = await corroborate_with_fascicle(db, dry_run=dry_run)
        await engine.dispose()
        return report

    return asyncio.run(go())


def _rows(url: str, ids: dict[str, str]) -> dict:
    from app.models.financial_data import FinancialData

    async def go():
        engine = create_async_engine(url)
        async with async_sessionmaker(engine)() as db:
            got = {k: await db.get(FinancialData, v) for k, v in ids.items()}
        await engine.dispose()
        return got

    return asyncio.run(go())


def test_dry_run_reports_without_writing(pg_db) -> None:
    report = _run(pg_db["url"], dry_run=True)
    assert len(report.unit_set) == 2 and len(report.scope_set) == 2 and len(report.disagreements) == 1
    assert report.protected_skipped == 1
    assert _rows(pg_db["url"], pg_db["ids"])["pnb"].value_normalized is None


def test_agreement_establishes_unit_and_scope_only(pg_db) -> None:
    _run(pg_db["url"], dry_run=False)
    r = _rows(pg_db["url"], pg_db["ids"])
    pnb = r["pnb"]
    assert pnb.unit_original == "unit" and pnb.value_normalized == Decimal("46412884468")
    assert pnb.scope_evidence_class == "C" and pnb.scope_reason_code == "scope_corroborated_by_regulatory_fascicle"
    assert pnb.status == "needs_review" and pnb.value_original == "46 412 884 468"  # status / raw never changed
    codes = {f["code"] for f in pnb.quality_flags}
    assert "unit_corroborated" in codes and "unit_or_currency_not_stated" not in codes
    assert r["cash"].unit_original == "unit"
    for untouched in ("dep", "orphan"):
        assert r[untouched].value_normalized is None and r[untouched].scope_evidence_class == "D"
    assert r["human"].unit_original is None  # human decision: never touched


def test_rerun_is_idempotent(pg_db) -> None:
    report = _run(pg_db["url"], dry_run=False)
    assert not report.unit_set and not report.scope_set
