"""
Phase 14 — Markets & Public Debt (BRVM & UMOA-Titres) integration tests on PostgreSQL.

Tests:
- Seeding of official market sources (BRVM, UMOA-Titres, AMF-UMOA, DC/BR);
- Seeding of market infrastructures and 8 Sovereign Treasuries;
- Supervision and Clearing relationships graph;
- Seeding of 12 official market and sovereign debt metrics;
- End-to-end recording of market and public debt observations on FinancialData (observation_level='market' / 'country');
- End-to-end recording of sovereign bond and auction transactions on Deal Intelligence;
- Migration 0010 downgrade / re-upgrade idempotency.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.constants.markets import MARKET_METRIC_CODES
from app.models.country import Country
from app.models.deal import Deal, DealParticipant, DealSource
from app.models.document import Document
from app.models.entity import Entity
from app.models.entity_relationship import EntityRelationship
from app.models.financial_data import FinancialData
from app.models.metric_definition import MetricDefinition
from app.models.source import Source
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

    test_db = f"{params['base_db']}_phase14_markets_pytest"
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
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        sn = (await db.execute(select(Country).where(Country.code == "SN"))).scalar_one()

        brvm_src = (await db.execute(select(Source).where(Source.short_name == "BRVM"))).scalar_one()
        ut_src = (await db.execute(select(Source).where(Source.short_name == "UMOA-Titres"))).scalar_one()

        # Documents
        doc_brvm = Document(
            title="Bulletin Officiel de la Cote BRVM 2024",
            document_type="regulatory_report",
            source_id=brvm_src.id,
            download_status="downloaded",
            extraction_status="extracted",
            period_year=2024,
            period_type="annual",
        )
        doc_ut = Document(
            title="Rapport Annuel UMOA-Titres 2024",
            document_type="regulatory_report",
            source_id=ut_src.id,
            download_status="downloaded",
            extraction_status="extracted",
            period_year=2024,
            period_type="annual",
        )
        db.add_all([doc_brvm, doc_ut])
        await db.commit()

        ids["ci_id"] = ci.id
        ids["sn_id"] = sn.id
        ids["brvm_src_id"] = brvm_src.id
        ids["ut_src_id"] = ut_src.id
        ids["doc_brvm_id"] = doc_brvm.id
        ids["doc_ut_id"] = doc_ut.id

    await engine.dispose()
    return ids


@pytest.mark.asyncio
async def test_market_sources_seeded(pg_db):
    """Verify that all 4 official market sources are correctly seeded in the database."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        sources = (await db.execute(select(Source))).scalars().all()
        short_names = {s.short_name for s in sources}
        assert "BRVM" in short_names
        assert "UMOA-Titres" in short_names
        assert "AMF-UMOA" in short_names
        assert "DC/BR" in short_names

    await engine.dispose()


@pytest.mark.asyncio
async def test_core_market_and_sovereign_entities_seeded(pg_db):
    """Verify that BRVM, DC/BR, UMOA-Titres, AMF-UMOA and the 8 Sovereign Treasuries exist in entities."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        entities = (await db.execute(select(Entity))).scalars().all()
        names = {e.canonical_name for e in entities}

        # Market Infrastructures & Regulators
        assert "Bourse Régionale des Valeurs Mobilières" in names
        assert "Dépositaire Central / Banque de Règlement" in names
        assert "Agence UMOA-Titres" in names
        assert "Autorité des Marchés Financiers de l'UMOA" in names

        # 8 Sovereign Treasuries
        assert "Trésor Public de Côte d'Ivoire" in names
        assert "Trésor Public du Sénégal" in names
        assert "Trésor Public du Bénin" in names
        assert "Trésor Public du Burkina Faso" in names
        assert "Trésor Public du Togo" in names
        assert "Trésor Public du Mali" in names
        assert "Trésor Public du Niger" in names
        assert "Trésor Public de Guinée-Bissau" in names

    await engine.dispose()


@pytest.mark.asyncio
async def test_market_institutional_relationships_seeded(pg_db):
    """Verify institutional links: AMF-UMOA supervises BRVM/DCBR, and BRVM cleared by DCBR."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        rels = (await db.execute(select(EntityRelationship))).scalars().all()
        rel_types = {(r.relationship_type, r.role_context) for r in rels}

        assert ("supervises", "market_regulator") in rel_types
        assert ("cleared_by_depository", "settlement_and_custody") in rel_types

    await engine.dispose()


@pytest.mark.asyncio
async def test_market_metrics_catalogue_seeded(pg_db):
    """Verify that all 12 market and sovereign metrics are seeded in metric_definitions."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        metrics = (await db.execute(select(MetricDefinition))).scalars().all()
        metric_codes = {m.code for m in metrics}

        for code in MARKET_METRIC_CODES:
            assert code in metric_codes

        # Check sector tags
        market_sector_metrics = [m for m in metrics if m.sector == "markets"]
        sovereign_sector_metrics = [m for m in metrics if m.sector == "sovereign"]
        assert len(market_sector_metrics) == 7
        assert len(sovereign_sector_metrics) == 5

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_market_and_sovereign_observations(pg_db):
    """Record market observations on FinancialData with decoupled scopes."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        brvm = (
            await db.execute(
                select(Entity).where(Entity.canonical_name == "Bourse Régionale des Valeurs Mobilières")
            )
        ).scalar_one()
        tresor_ci = (
            await db.execute(
                select(Entity).where(Entity.canonical_name == "Trésor Public de Côte d'Ivoire")
            )
        ).scalar_one()

        # 1. Market-level observation: BRVM Composite Index
        fd_composite = FinancialData(
            entity_id=brvm.id,
            observation_level="market",
            consolidation_scope="not_applicable",
            scope="individual",  # backward-compatible V1 field
            source_id=pg_db["ids"]["brvm_src_id"],
            document_id=pg_db["ids"]["doc_brvm_id"],
            metric_code="indice_brvm_composite",
            period_year=2024,
            period_type="annual",
            value_original="215.45",
            value_normalized=Decimal("215.45"),
            currency_original="XOF",
            currency_normalized="XOF",
            status="verified",
            verified_at=datetime.now(UTC),
            verified_by="market_analyst@umoa.org",
        )

        # 2. Sovereign-level observation: Côte d'Ivoire Public Debt Securities Outstanding
        fd_debt = FinancialData(
            entity_id=tresor_ci.id,
            observation_level="country",
            consolidation_scope="consolidated",
            scope="consolidated",
            source_id=pg_db["ids"]["ut_src_id"],
            document_id=pg_db["ids"]["doc_ut_id"],
            metric_code="encours_titres_publics",
            period_year=2024,
            period_type="annual",
            value_original="5600000000000",
            value_normalized=Decimal("5600000000000"),
            currency_original="XOF",
            currency_normalized="XOF",
            status="verified",
            verified_at=datetime.now(UTC),
            verified_by="sovereign_analyst@umoa.org",
        )

        db.add_all([fd_composite, fd_debt])
        await db.commit()

        # Query and verify
        saved_comp = (
            await db.execute(
                select(FinancialData).where(FinancialData.metric_code == "indice_brvm_composite")
            )
        ).scalar_one()
        assert saved_comp.observation_level == "market"
        assert saved_comp.entity_id == brvm.id

        saved_debt = (
            await db.execute(
                select(FinancialData).where(FinancialData.metric_code == "encours_titres_publics")
            )
        ).scalar_one()
        assert saved_debt.observation_level == "country"
        assert saved_debt.entity_id == tresor_ci.id

    await engine.dispose()


@pytest.mark.asyncio
async def test_record_sovereign_bond_deal(pg_db):
    """Record a sovereign bond emission deal with UMOA-Titres provenance and participants."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        deal = Deal(
            title="Émission Obligataire Souveraine TPBF 6.00% 2024-2031",
            deal_type="sovereign_bond",
            country_id=pg_db["ids"]["ci_id"],
            sector="Sovereign Debt",
            amount=Decimal("75000000000"),
            currency="XOF",
            interest_rate=Decimal("6.0000"),
            interest_rate_type="fixed",
            maturity_months=84,
            status="needs_review",
        )
        db.add(deal)
        await db.flush()

        deal_src = DealSource(
            deal_id=deal.id,
            document_id=pg_db["ids"]["doc_ut_id"],
            source_id=pg_db["ids"]["ut_src_id"],
            page_number=1,
        )
        db.add(deal_src)
        await db.flush()

        p_issuer = DealParticipant(
            deal_id=deal.id,
            participant_name="Trésor Public du Burkina Faso",
            role="issuer",
            deal_source_id=deal_src.id,
        )
        p_agent = DealParticipant(
            deal_id=deal.id,
            participant_name="Agence UMOA-Titres",
            role="facility_agent",
            deal_source_id=deal_src.id,
        )
        db.add_all([p_issuer, p_agent])
        await db.commit()

        # Query verification
        saved_deal = (await db.execute(select(Deal).where(Deal.id == deal.id))).scalar_one()
        assert saved_deal.deal_type == "sovereign_bond"
        parts = (
            await db.execute(select(DealParticipant).where(DealParticipant.deal_id == deal.id))
        ).scalars().all()
        roles = {p.role for p in parts}
        assert "issuer" in roles
        assert "facility_agent" in roles

    await engine.dispose()


def test_migration_0010_downgrade_and_upgrade(pg_db):
    """Test Alembic migration 0010 downgrade and re-upgrade idempotency."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))

    # Downgrade -1 (reverts 0010)
    command.downgrade(cfg, "-1")
    # Re-upgrade to head
    command.upgrade(cfg, "head")
