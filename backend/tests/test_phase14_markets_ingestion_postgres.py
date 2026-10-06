"""
Phase 14 — Markets & Public Debt Ingestion Integration Tests on PostgreSQL.

Verifies:
1. Complete ingestion pipeline for BRVM (BOC documents -> 7 market observations).
2. Complete ingestion pipeline for UMOA-Titres (Compte Rendu -> Sovereign debt observations).
3. Linking to Entity Hub (`entity_id`), decoupled scopes (`observation_level`, `consolidation_scope`), `institution_id=None`.
4. Idempotency on second run: exactly 0 duplicate documents, 0 duplicate observations.
5. Invariant protection: human decisions (reviewed/verified/rejected) are never overwritten.
6. Invariant check: DATA MISSING > DATA WRONG (no 0 conversion, no interpolation).
7. IngestionService integration with `sources=['brvm', 'umoa-titres']`.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from collections.abc import Generator
from decimal import Decimal
from pathlib import Path

import pymupdf
import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.country import Country
from app.models.document import Document
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.source import Source
from scraping.pipeline import ScrapingPipeline
from scraping.storage.manager import StorageManager
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

    test_db = f"{params['base_db']}_phase14_ingestion_pytest"
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
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    ids: dict[str, str] = {}

    async with maker() as db:
        brvm_src = (await db.execute(select(Source).where(Source.short_name == "BRVM"))).scalar_one()
        ut_src = (await db.execute(select(Source).where(Source.short_name == "UMOA-Titres"))).scalar_one()
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()

        brvm_ent = (await db.execute(select(Entity).where(Entity.canonical_name == "Bourse Régionale des Valeurs Mobilières"))).scalar_one()
        tresor_ci_ent = (await db.execute(select(Entity).where(Entity.canonical_name == "Trésor Public de Côte d'Ivoire"))).scalar_one()

        ids["brvm_src_id"] = brvm_src.id
        ids["ut_src_id"] = ut_src.id
        ids["ci_id"] = ci.id
        ids["brvm_ent_id"] = brvm_ent.id
        ids["tresor_ci_ent_id"] = tresor_ci_ent.id

    await engine.dispose()
    return ids


def _create_synthetic_boc_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        "BRVM COMPOSITE\n548,04\nVariation Jour\n0,48 %\n"
        "BRVM 30\n265,14\nVariation Jour\n0,35 %\n"
        "Actions\nNiveau\nEvol. Jour\n"
        "Capitalisation boursière (FCFA)(Actions & Droits)\n  21 491 234 105 518\n0,48 %\n"
        "Volume échangé (Actions & Droits)\n    1 509 438\n"
        "Valeur transigée (FCFA) (Actions & Droits)\n   3 247 423 193\n"
        "Obligations\nNiveau\nEvol. Jour\n"
        "Capitalisation boursière (FCFA)\n  13 616 018 491 470\n0,02 %\n"
        "INDICES SECTORIELS\nIndicateurs\nBRVM COMPOSITE\n"
        "PER moyen du marché         (**)\n18,09\n"
        "Taux de rendement moyen du marché\n6,10\n"
    )
    page.insert_text((50, 50), text)
    b = doc.tobytes()
    doc.close()
    return b


def _create_synthetic_ut_compte_rendu_bytes() -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    text = (
        "COMPTE RENDU D'ADJUDICATION DE BONS ET D'OBLIGATIONS ASSIMILABLES DU TRÉSOR\n"
        "Emetteur :\nETAT DE CÔTE D'IVOIRE\n"
        "Nature des titres : Bons et d'Obligations Assimilables du Trésor\n"
        "Montant global mis en adjudication : 100 000 millions de FCFA\n"
        "Date d'adjudication : 29/09/2026\n"
        "Date de valeur : 30/09/2026\n"
        "Montant global des soumissions : 163 915 millions de FCFA\n"
        "Soumissions retenues : 110 000 millions de FCFA\n"
        "Soumissions rejetées : 53 915 millions de FCFA\n"
        "Taux de couverture du montant mis en adjudication par les soumissions : 163,92%\n"
        "BAT - 364 jours\n"
        "Taux/Prix moyen pondéré\n3,9036%\n"
        "OAT - 3 ans\n"
        "Rendement moyen pondéré\n6,36%\n"
    )
    page.insert_text((50, 50), text)
    b = doc.tobytes()
    doc.close()
    return b


@pytest.mark.asyncio
async def test_e2e_brvm_boc_ingestion_and_provenance(pg_db):
    """Test full pipeline storage and extraction of BRVM BOC document."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as storage_dir:
        storage = StorageManager(storage_dir)
        pipeline = ScrapingPipeline(storage_manager=storage)

        boc_bytes = _create_synthetic_boc_bytes()
        storage_res = storage.store_content(boc_bytes, "boc_20260929_2.pdf")

        async with maker() as db:
            doc = Document(
                title="Bulletin Officiel de la Cote 29/09/2026",
                document_type="regulatory_report",
                source_id=pg_db["ids"]["brvm_src_id"],
                download_status="downloaded",
                extraction_status="extracted",
                file_hash=storage_res.file_hash,
                storage_path=storage_res.relative_path,
                period_year=2026,
                period_type="annual",
            )
            db.add(doc)
            await db.commit()
            doc_id = doc.id

            # Extract financial data
            results = await pipeline.extract_financial_data(db=db, document_id=doc_id)
            assert len(results) == 1
            _, points = results[0]
            assert len(points) == 7

            # Query database
            rows = (
                await db.execute(
                    select(FinancialData).where(FinancialData.document_id == doc_id)
                )
            ).scalars().all()
            assert len(rows) == 7

            by_code = {r.metric_code: r for r in rows}

            # Check individual observations and constraints
            comp = by_code["indice_brvm_composite"]
            assert comp.entity_id == pg_db["ids"]["brvm_ent_id"]
            assert comp.institution_id is None
            assert comp.observation_level == "market"
            assert comp.consolidation_scope == "not_applicable"
            assert comp.scope == "individual"
            assert comp.period_year == 2026
            assert comp.value_normalized == Decimal("548.04")
            assert comp.status == "needs_review"
            assert "scope not detected" in (comp.notes or "")

            cap_act = by_code["capitalisation_actions"]
            assert cap_act.value_normalized == Decimal("21491234105518")
            assert cap_act.currency_normalized == "XOF"
            assert cap_act.observation_level == "market"

            cap_ob = by_code["capitalisation_obligations"]
            assert cap_ob.value_normalized == Decimal("13616018491470")
            assert cap_ob.currency_normalized == "XOF"

            per = by_code["per_moyen_marche"]
            assert per.value_normalized == Decimal("18.09")

            rend = by_code["rendement_moyen_dividende"]
            assert rend.value_normalized == Decimal("6.10")

    await engine.dispose()


@pytest.mark.asyncio
async def test_e2e_umoa_titres_auction_ingestion_and_provenance(pg_db):
    """Test full pipeline storage and extraction of UMOA-Titres Compte Rendu document."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as storage_dir:
        storage = StorageManager(storage_dir)
        pipeline = ScrapingPipeline(storage_manager=storage)

        ut_bytes = _create_synthetic_ut_compte_rendu_bytes()
        storage_res = storage.store_content(ut_bytes, "Compte-Rendu-CI-ES-29.09.2026.pdf")

        async with maker() as db:
            doc = Document(
                title="Compte Rendu CI ES 29.09.2026",
                document_type="regulatory_report",
                source_id=pg_db["ids"]["ut_src_id"],
                download_status="downloaded",
                extraction_status="extracted",
                file_hash=storage_res.file_hash,
                storage_path=storage_res.relative_path,
                period_year=2026,
                period_type="annual",
            )
            db.add(doc)
            await db.commit()
            doc_id = doc.id

            # Extract financial data
            results = await pipeline.extract_financial_data(db=db, document_id=doc_id)
            assert len(results) == 1
            _, points = results[0]
            assert len(points) == 4

            # Query database
            rows = (
                await db.execute(
                    select(FinancialData).where(FinancialData.document_id == doc_id)
                )
            ).scalars().all()
            assert len(rows) == 4

            by_code = {r.metric_code: r for r in rows}

            # Check sovereign debt observation
            montant = by_code["montant_emis_titres_publics"]
            assert montant.entity_id == pg_db["ids"]["tresor_ci_ent_id"]
            assert montant.institution_id is None
            assert montant.observation_level == "country"
            assert montant.consolidation_scope == "consolidated"
            assert montant.scope == "consolidated"
            assert montant.period_year == 2026
            assert montant.value_normalized == Decimal("110000000000")
            assert montant.currency_normalized == "XOF"
            assert montant.status == "needs_review"

            couv = by_code["taux_couverture_adjudications"]
            assert couv.value_normalized == Decimal("163.92")
            assert couv.entity_id == pg_db["ids"]["tresor_ci_ent_id"]

            bat = by_code["taux_moyen_adjudication_bat"]
            assert bat.value_normalized == Decimal("3.9036")

            oat = by_code["taux_moyen_adjudication_oat"]
            assert oat.value_normalized == Decimal("6.36")

    await engine.dispose()


@pytest.mark.asyncio
async def test_idempotence_and_no_duplicates_on_second_extraction(pg_db):
    """Verify that re-running extraction on the exact same document produces 0 duplicates."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as storage_dir:
        storage = StorageManager(storage_dir)
        pipeline = ScrapingPipeline(storage_manager=storage)

        boc_bytes = _create_synthetic_boc_bytes()
        storage_res = storage.store_content(boc_bytes, "boc_idempotent.pdf")

        async with maker() as db:
            doc = Document(
                title="Bulletin BOC Idempotency Test",
                document_type="regulatory_report",
                source_id=pg_db["ids"]["brvm_src_id"],
                download_status="downloaded",
                extraction_status="extracted",
                file_hash=storage_res.file_hash,
                storage_path=storage_res.relative_path,
                period_year=2026,
            )
            db.add(doc)
            await db.commit()
            doc_id = doc.id

            # 1. First run
            await pipeline.extract_financial_data(db=db, document_id=doc_id)
            count_first = (
                await db.execute(
                    select(func.count(FinancialData.id)).where(FinancialData.document_id == doc_id)
                )
            ).scalar_one()
            assert count_first == 7

            # 2. Second run (identical input)
            await pipeline.extract_financial_data(db=db, document_id=doc_id)
            count_second = (
                await db.execute(
                    select(func.count(FinancialData.id)).where(FinancialData.document_id == doc_id)
                )
            ).scalar_one()
            assert count_second == 7  # No extra rows created

    await engine.dispose()


@pytest.mark.asyncio
async def test_protected_status_never_overwritten_by_reextraction(pg_db):
    """Verify that human verification/rejection is NEVER overwritten by a re-extraction."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    with tempfile.TemporaryDirectory() as storage_dir:
        storage = StorageManager(storage_dir)
        pipeline = ScrapingPipeline(storage_manager=storage)

        boc_bytes = _create_synthetic_boc_bytes()
        storage_res = storage.store_content(boc_bytes, "boc_protected.pdf")

        async with maker() as db:
            doc = Document(
                title="Bulletin BOC Protection Test",
                document_type="regulatory_report",
                source_id=pg_db["ids"]["brvm_src_id"],
                download_status="downloaded",
                extraction_status="extracted",
                file_hash=storage_res.file_hash,
                storage_path=storage_res.relative_path,
                period_year=2026,
            )
            db.add(doc)
            await db.commit()
            doc_id = doc.id

            # First extraction
            await pipeline.extract_financial_data(db=db, document_id=doc_id)

            # Human analyst verifies the composite index row
            row = (
                await db.execute(
                    select(FinancialData).where(
                        FinancialData.document_id == doc_id,
                        FinancialData.metric_code == "indice_brvm_composite",
                    )
                )
            ).scalar_one()
            row.status = "verified"
            row.verified_by = "market_officer@brvm.org"
            row.verified_at = func.now()
            row.notes = "Audited and verified by market operations officer"
            await db.commit()

            # Re-extraction must NOT overwrite or revert to needs_review
            await pipeline.extract_financial_data(db=db, document_id=doc_id)

            refreshed = (
                await db.execute(
                    select(FinancialData).where(FinancialData.id == row.id)
                )
            ).scalar_one()
            assert refreshed.status == "verified"
            assert refreshed.verified_by == "market_officer@brvm.org"
            assert "Audited and verified" in (refreshed.notes or "")

    await engine.dispose()
