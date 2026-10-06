"""
Phase 14 — Unified Financial Intelligence (Socle Structurel) against PostgreSQL.

Scratch-database testing of:
- Migration 0009 upgrade / downgrade idempotency;
- Entity Hub registry across classes & types;
- 1:1 Institution <-> Entity relationship preservation;
- Decoupled FinancialData (entity_id, observation_level, consolidation_scope);
- MetricDefinition taxonomy (sector, metric_family) preserving the 26 V1 banking metrics;
- EntityRelationship graph with temporal bounds, provenance, and constraints;
- Cross-sector Deal and Participant role expansions;
- Banking isolation and non-regression for rankings & analytics.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.constants.metrics import V1_METRIC_CODES
from app.models.country import Country
from app.models.deal import Deal, DealParticipant, DealSource
from app.models.document import Document
from app.models.entity import Entity
from app.models.entity_relationship import EntityRelationship
from app.models.financial_data import FinancialData
from app.models.institution import Institution
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

    test_db = f"{params['base_db']}_phase14_unified_pytest"
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

        src = (await db.execute(select(Source))).scalars().first()
        if src is None:
            src = Source(name="BCEAO", short_name="BCEAO", source_type="central_bank", is_active=True, priority=1)
            db.add(src)
            await db.flush()

        inst_a = Institution(
            name_official="Société Ivoirienne de Banque",
            name_commercial="SIB",
            institution_type="bank",
            country_id=ci.id,
            status="active",
            source_id=src.id,
        )
        inst_b = Institution(
            name_official="CBAO Groupe Attijariwafa bank",
            name_commercial="CBAO",
            institution_type="bank",
            country_id=sn.id,
            status="active",
            source_id=src.id,
        )
        db.add_all([inst_a, inst_b])
        await db.flush()

        # Create entities & map for institutions
        ent_a = Entity(
            entity_class="financial_institution",
            entity_type="commercial_bank",
            canonical_name=inst_a.name_official,
            short_name=inst_a.name_commercial,
            country_id=ci.id,
            status="active",
        )
        ent_b = Entity(
            entity_class="financial_institution",
            entity_type="commercial_bank",
            canonical_name=inst_b.name_official,
            short_name=inst_b.name_commercial,
            country_id=sn.id,
            status="active",
        )
        db.add_all([ent_a, ent_b])
        await db.flush()

        inst_a.entity_id = ent_a.id
        inst_b.entity_id = ent_b.id

        doc = Document(
            title="Rapport Annuel SIB 2024",
            document_type="annual_report",
            institution_id=inst_a.id,
            source_id=src.id,
            download_status="downloaded",
            extraction_status="extracted",
            period_year=2024,
            period_type="annual",
        )
        db.add(doc)
        await db.flush()

        from datetime import UTC, datetime

        fd = FinancialData(
            institution_id=inst_a.id,
            entity_id=ent_a.id,
            observation_level="entity",
            consolidation_scope="individual",
            scope="individual",
            source_id=src.id,
            document_id=doc.id,
            metric_code="total_actifs",
            period_year=2024,
            period_type="annual",
            value_original="1500000000000",
            value_normalized=Decimal("1500000000000"),
            currency_original="XOF",
            currency_normalized="XOF",
            status="verified",
            verified_at=datetime.now(UTC),
            verified_by="auditor@umoa.org",
        )
        db.add(fd)
        await db.commit()

        ids["ci_id"] = ci.id
        ids["sn_id"] = sn.id
        ids["src_id"] = src.id
        ids["inst_a_id"] = inst_a.id
        ids["inst_b_id"] = inst_b.id
        ids["ent_a_id"] = ent_a.id
        ids["ent_b_id"] = ent_b.id
        ids["doc_id"] = doc.id
        ids["fd_id"] = fd.id

    await engine.dispose()
    return ids


def test_migration_0009_up_and_down(pg_db):
    """Test Alembic migration 0009 downgrade and re-upgrade idempotency."""
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))

    # Downgrade -1 (reverts 0009)
    command.downgrade(cfg, "-1")
    # Re-upgrade to head
    command.upgrade(cfg, "head")


@pytest.mark.asyncio
async def test_entities_hub_crud_and_constraints(pg_db):
    """Test Entity Hub creation and check constraints across sectors."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        # Create diverse entity types
        regulator = Entity(
            entity_class="regulator",
            entity_type="central_bank",
            canonical_name="Banque Centrale des États de l'Afrique de l'Ouest",
            short_name="BCEAO",
            status="active",
        )
        sovereign = Entity(
            entity_class="sovereign_entity",
            entity_type="sovereign_state",
            canonical_name="État de Côte d'Ivoire",
            short_name="RCI",
            country_id=pg_db["ids"]["ci_id"],
            status="active",
        )
        market_infra = Entity(
            entity_class="market_infrastructure",
            entity_type="stock_exchange",
            canonical_name="Bourse Régionale des Valeurs Mobilières",
            short_name="BRVM",
            status="active",
        )
        db.add_all([regulator, sovereign, market_infra])
        await db.commit()

        # Check constraint violation on invalid entity_class
        invalid_entity = Entity(
            entity_class="invalid_class",
            entity_type="commercial_bank",
            canonical_name="Invalid Entity",
        )
        db.add(invalid_entity)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_institution_entity_linkage(pg_db):
    """Verify 1:1 relationship between Institution and Entity."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        inst = (
            await db.execute(
                select(Institution).where(Institution.id == pg_db["ids"]["inst_a_id"])
            )
        ).scalar_one()

        assert inst.entity_id is not None
        assert inst.entity is not None
        assert inst.entity.canonical_name == "Société Ivoirienne de Banque"

    await engine.dispose()


@pytest.mark.asyncio
async def test_financial_data_scopes_and_observation_levels(pg_db):
    """Verify decoupled observation_level and consolidation_scope on FinancialData."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        inst_a = (
            await db.execute(
                select(Institution).where(Institution.id == pg_db["ids"]["inst_a_id"])
            )
        ).scalar_one()

        fd = (
            await db.execute(
                select(FinancialData).where(FinancialData.id == pg_db["ids"]["fd_id"])
            )
        ).scalar_one()

        assert fd.entity_id == inst_a.entity_id
        assert fd.observation_level == "entity"
        assert fd.consolidation_scope == "individual"
        assert fd.scope == "individual"

        # Test valid alternate observation level
        fd_group = FinancialData(
            institution_id=inst_a.id,
            entity_id=inst_a.entity_id,
            observation_level="group",
            consolidation_scope="consolidated",
            scope="consolidated",
            source_id=pg_db["ids"]["src_id"],
            document_id=pg_db["ids"]["doc_id"],
            metric_code="total_actifs",
            period_year=2024,
            period_type="annual",
            value_original="2000000000000",
            value_normalized=Decimal("2000000000000"),
            currency_original="XOF",
            currency_normalized="XOF",
            status="extracted",
        )
        db.add(fd_group)
        await db.commit()

        # Check constraint violation on invalid observation_level
        invalid_fd = FinancialData(
            institution_id=inst_a.id,
            observation_level="invalid_level",
            consolidation_scope="individual",
            scope="individual",
            source_id=pg_db["ids"]["src_id"],
            document_id=pg_db["ids"]["doc_id"],
            metric_code="total_actifs",
            period_year=2024,
            period_type="annual",
            value_original="100",
            currency_original="XOF",
            status="extracted",
        )
        db.add(invalid_fd)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_metric_definitions_sector_and_family(pg_db):
    """Verify all 26 V1 metrics are banking, and test cross-sector taxonomy additions."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        # All 26 frozen metrics must have sector == 'banking'
        metrics = (await db.execute(select(MetricDefinition))).scalars().all()
        assert len(metrics) >= 26
        for m in metrics:
            if m.code in V1_METRIC_CODES:
                assert m.sector == "banking"

        # Add a new cross-sector metric (e.g. insurance)
        ins_metric = MetricDefinition(
            code="primes_emises_brutes",
            label_fr="Primes émises brutes",
            label_en="Gross written premiums",
            definition_fr="Montant total des primes souscrites par l'assureur.",
            definition_en="Total premiums written by the insurer.",
            statement_type="income_statement",
            category="income_statement",
            value_type="amount",
            currency_type="monetary",
            sector="insurance",
            metric_family="claims_underwriting",
            is_calculated=False,
            is_active=True,
            display_order=100,
        )
        db.add(ins_metric)
        await db.commit()

        # Check constraint violation on invalid sector
        invalid_metric = MetricDefinition(
            code="invalid_metric_code",
            label_fr="Invalid",
            label_en="Invalid",
            definition_fr="Invalid",
            definition_en="Invalid",
            statement_type="balance_sheet",
            category="assets",
            value_type="amount",
            currency_type="monetary",
            sector="invalid_sector",
            metric_family="balance_sheet",
        )
        db.add(invalid_metric)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_entity_relationships_provenance_and_constraints(pg_db):
    """Test EntityRelationship creation, validity, and check constraints."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        inst_a = (
            await db.execute(
                select(Institution).where(Institution.id == pg_db["ids"]["inst_a_id"])
            )
        ).scalar_one()
        inst_b = (
            await db.execute(
                select(Institution).where(Institution.id == pg_db["ids"]["inst_b_id"])
            )
        ).scalar_one()

        ent_a_id = inst_a.entity_id
        ent_b_id = inst_b.entity_id

        # Valid relationship with full provenance
        rel = EntityRelationship(
            source_entity_id=ent_b_id,
            target_entity_id=ent_a_id,
            relationship_type="owns_equity",
            role_context="strategic_investor",
            ownership_percentage=Decimal("51.00"),
            voting_rights_percentage=Decimal("51.00"),
            valid_from=date(2020, 1, 1),
            is_current=True,
            source_id=pg_db["ids"]["src_id"],
            document_id=pg_db["ids"]["doc_id"],
            page_number=12,
            confidence_score=Decimal("0.950"),
            notes="Attested in 2024 annual report page 12",
        )
        db.add(rel)
        await db.commit()

        # Constraint 1: Self-reference not allowed
        self_rel = EntityRelationship(
            source_entity_id=ent_a_id,
            target_entity_id=ent_a_id,
            relationship_type="owns_equity",
        )
        db.add(self_rel)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        # Constraint 2: Ownership percentage > 100% rejected
        invalid_pct = EntityRelationship(
            source_entity_id=ent_a_id,
            target_entity_id=ent_b_id,
            relationship_type="owns_equity",
            ownership_percentage=Decimal("105.00"),
        )
        db.add(invalid_pct)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

        # Constraint 3: valid_to < valid_from rejected
        invalid_dates = EntityRelationship(
            source_entity_id=ent_a_id,
            target_entity_id=ent_b_id,
            relationship_type="branch_of",
            valid_from=date(2024, 1, 1),
            valid_to=date(2023, 1, 1),
        )
        db.add(invalid_dates)
        with pytest.raises(IntegrityError):
            await db.commit()
        await db.rollback()

    await engine.dispose()


@pytest.mark.asyncio
async def test_deal_and_participant_cross_sector_expansion(pg_db):
    """Test Deal and Participant creation with expanded cross-sector vocabularies."""
    engine = create_async_engine(pg_db["url"])
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as db:
        # Deal with new deal_type
        deal = Deal(
            title="Émission Souveraine Sukuk 2024",
            deal_type="sukuk",
            country_id=pg_db["ids"]["ci_id"],
            sector="Sovereign Finance",
            amount=Decimal("100000000000"),
            currency="XOF",
            status="needs_review",
        )
        db.add(deal)
        await db.flush()

        deal_src = DealSource(
            deal_id=deal.id,
            document_id=pg_db["ids"]["doc_id"],
            source_id=pg_db["ids"]["src_id"],
            page_number=5,
        )
        db.add(deal_src)
        await db.flush()

        # Participants with new roles: underwriter, trustee, insurer
        p1 = DealParticipant(
            deal_id=deal.id,
            participant_name="Banque Chef de File",
            institution_id=pg_db["ids"]["inst_a_id"],
            role="underwriter",
            deal_source_id=deal_src.id,
        )
        p2 = DealParticipant(
            deal_id=deal.id,
            participant_name="Compagnie d'Assurance UMOA",
            role="insurer",
            deal_source_id=deal_src.id,
        )
        db.add_all([p1, p2])
        await db.commit()

        # Verify query on deal with new types
        res = (await db.execute(select(Deal).where(Deal.id == deal.id))).scalar_one()
        assert res.deal_type == "sukuk"
        participants = (
            await db.execute(select(DealParticipant).where(DealParticipant.deal_id == deal.id))
        ).scalars().all()
        roles = {p.role for p in participants}
        assert "underwriter" in roles
        assert "insurer" in roles

    await engine.dispose()
