"""
Phase 15 — Entity & Source Discovery Engine against PostgreSQL (scratch databases).

Synthetic fixtures only (tests/fixtures_phase15.py): names start with "FIXTURE", registration
numbers with "Z 9". No network access: engine tests use stub strategies and a stub fetcher.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Generator
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.country import Country
from app.models.discovery import (
    DiscoveryGap,
    DiscoveryRound,
    DocumentEntity,
    EntityIdentifier,
    EntityName,
    EntitySource,
    ReferenceUniverse,
    ReferenceUniverseMember,
)
from app.models.document import Document
from app.models.entity import Entity
from app.models.entity_relationship import EntityRelationship
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.source import Source
from scraping.storage.manager import StorageManager
from scraping.universe.coverage import compute_coverage
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.engine import DiscoveryEngine
from scraping.universe.fascicle import FasciclePage, FascicleValue
from scraping.universe.gaps import GapQueue
from scraping.universe.materializer import UniverseMaterializer, refresh_current_snapshot
from scraping.universe.reference_list import ReferenceListParser
from scraping.universe.resolution import EntityResolver
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult
from scraping.universe.strategies.market_and_web import upsert_entity_source
from scraping.universe.strategies.regulatory_fascicle import BceaoFascicleStrategy
from tests.fixtures_phase15 import build_reference_list_pdf, fixture_banks
from tests.test_migration_postgres_phase2 import (
    _async_dsn,
    _dsn,
    _exec_admin,
    _fetchval,
    _reachable,
    _server_params,
)

BACKEND = Path(__file__).resolve().parents[1]
UNIVERSE = "UMOA.BANKING"
FIXTURE_TOTAL = sum(len(v) for v in fixture_banks().values())  # 11 official fixture lines


def _banks_2026() -> dict:
    banks = fixture_banks()
    banks["BJ"] = [{**banks["BJ"][0], "name": "FIXTURE BANK OMEGA BÉNIN (FBO-BJ)"}]  # same registration number
    return banks


# Built once: re-materializing the SAME bytes must be idempotent (same file hash = same document).
LIST_2025 = build_reference_list_pdf()
LIST_2026 = build_reference_list_pdf(_banks_2026(), reference_label="30 JUIN 2026")


def _alembic(revision: str, direction: str = "upgrade") -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "migrations"))
    (command.upgrade if direction == "upgrade" else command.downgrade)(cfg, revision)


def _fresh_db(suffix: str) -> tuple[dict, str]:
    params = _server_params()
    if not _reachable(params):
        pytest.skip("No PostgreSQL server reachable — integration tests skipped")
    name = f"{params['base_db']}_{suffix}"
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)', f'CREATE DATABASE "{name}"'))
    os.environ["DATABASE_URL"] = _async_dsn(params, name)
    from app.core.config import get_settings

    get_settings.cache_clear()
    return params, name


def _drop(params: dict, name: str) -> None:
    os.environ.pop("DATABASE_URL", None)
    from app.core.config import get_settings

    get_settings.cache_clear()
    asyncio.run(_exec_admin(params, f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))


# =========================================================================== migration 0011
def test_migration_0011_roundtrip_preserves_existing_rows() -> None:
    params, name = _fresh_db("phase15_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0010_seed_markets_and_public_debt")

        async def seed() -> None:
            import asyncpg

            conn = await asyncpg.connect(dsn=dsn)
            try:
                ci = await conn.fetchval("SELECT id FROM countries WHERE code = 'CI'")
                src = await conn.fetchval("SELECT id FROM sources WHERE short_name = 'BCEAO'")
                await conn.execute(
                    "INSERT INTO entities (id, created_at, updated_at, entity_class, entity_type, canonical_name, "
                    "country_id, status) VALUES ('fx-ent', now(), now(), 'financial_institution', 'commercial_bank', "
                    "'FIXTURE LEGACY BANK', $1, 'active')", ci)
                await conn.execute(
                    "INSERT INTO institutions (id, created_at, updated_at, name_official, institution_type, "
                    "country_id, status, entity_id) VALUES ('fx-inst', now(), now(), 'FIXTURE LEGACY BANK', 'bank', "
                    "$1, 'active', 'fx-ent')", ci)
                await conn.execute(
                    "INSERT INTO documents (id, created_at, updated_at, title, document_type, institution_id, "
                    "source_id, download_status, extraction_status) VALUES ('fx-doc', now(), now(), 'FIXTURE DOC', "
                    "'annual_report', 'fx-inst', $1, 'downloaded', 'pending')", src)
            finally:
                await conn.close()

        asyncio.run(seed())
        _alembic("0011_entity_source_discovery")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0011_entity_source_discovery"
        assert asyncio.run(_fetchval(dsn, "SELECT entity_id FROM documents WHERE id = 'fx-doc'")) == "fx-ent"
        # lifecycle backfill is evidence based: BCEAO produced a downloaded document, CB-UMOA did not
        assert asyncio.run(_fetchval(dsn, "SELECT lifecycle_status FROM sources WHERE short_name='BCEAO'")) == "ACTIVE"
        assert asyncio.run(_fetchval(dsn, "SELECT lifecycle_status FROM sources WHERE short_name='CB-UMOA'")) == "VERIFIED"

        _alembic("0010_seed_markets_and_public_debt", "downgrade")
        assert asyncio.run(_fetchval(dsn, "SELECT to_regclass('reference_universes')")) is None
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM documents WHERE id = 'fx-doc'")) == 1
        assert asyncio.run(_fetchval(dsn, "SELECT entity_id FROM institutions WHERE id = 'fx-inst'")) == "fx-ent"

        _alembic("0011_entity_source_discovery")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM reference_universes")) == 0
    finally:
        _drop(params, name)


# =========================================================================== shared scratch DB
@pytest.fixture(scope="module")
def pg(tmp_path_factory) -> Generator[dict, None, None]:
    params, name = _fresh_db("phase15_discovery_pytest")
    _alembic("head")
    url = _async_dsn(params, name)
    storage = tmp_path_factory.mktemp("phase15_store")
    asyncio.run(_seed_pre_existing(url))
    yield {"url": url, "storage": storage}
    _drop(params, name)


async def _seed_pre_existing(url: str) -> None:
    """A demo bank (outside any official list) and a Togo entity whose name only partially overlaps."""
    engine = create_async_engine(url)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        countries = {c.code: c for c in (await db.execute(select(Country))).scalars().all()}
        bceao = (await db.execute(select(Source).where(Source.short_name == "BCEAO"))).scalar_one()
        demo = Entity(entity_class="financial_institution", entity_type="commercial_bank",
                      canonical_name="FIXTURE DEMO BANK", country_id=countries["CI"].id, status="active")
        near = Entity(entity_class="financial_institution", entity_type="commercial_bank",
                      canonical_name="FIXTURE BANK ALPHA TOGO INTERNATIONAL", country_id=countries["TG"].id,
                      status="active")
        db.add_all([demo, near])
        await db.flush()
        inst = Institution(name_official="FIXTURE DEMO BANK", institution_type="bank", country_id=countries["CI"].id,
                           status="active", entity_id=demo.id, source_id=bceao.id)
        db.add(inst)
        await db.flush()
        doc = Document(title="FIXTURE DEMO REPORT", document_type="annual_report", source_id=bceao.id,
                       institution_id=inst.id, entity_id=demo.id, download_status="downloaded",
                       extraction_status="extracted")
        db.add(doc)
        await db.flush()
        db.add(FinancialData(institution_id=inst.id, entity_id=demo.id, source_id=bceao.id, document_id=doc.id,
                             metric_code="total_actifs", period_year=2024, value_original="1", status="extracted"))
        await db.commit()
    await engine.dispose()


async def _session(url: str):
    engine = create_async_engine(url)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def _materialize(url: str, storage: Path, pdf: bytes, *, source_short: str = "BCEAO",
                       url_suffix: str = "list-2025.pdf"):
    engine, maker = await _session(url)
    async with maker() as db:
        source = (await db.execute(select(Source).where(Source.short_name == source_short))).scalar_one()
        registrar = DocumentRegistrar(StorageManager(storage))
        reg = await registrar.register_pdf(db, source=source, url=f"https://fixture.invalid/{url_suffix}",
                                           content=pdf, title="FIXTURE LIST", document_type="regulatory_report")
        resolver = EntityResolver()
        await resolver.load(db)
        parsed = ReferenceListParser().parse_bytes(pdf)
        result = await UniverseMaterializer(resolver, UNIVERSE).materialize(
            db, parsed=parsed, document=reg.document, source=source, run_id=None)
        await refresh_current_snapshot(db, UNIVERSE)
        await db.commit()
    await engine.dispose()
    return result


async def _count(url: str, model) -> int:
    engine, maker = await _session(url)
    async with maker() as db:
        n = (await db.execute(select(func.count()).select_from(model).where(model.deleted_at.is_(None)))).scalar_one()
    await engine.dispose()
    return n


# =========================================================================== materialization
def test_materialize_official_list(pg) -> None:
    result = asyncio.run(_materialize(pg["url"], pg["storage"], LIST_2025))
    assert result.snapshot_status == "INCOMPLETE"  # the Togo line is ambiguous (see below)
    assert result.members == FIXTURE_TOTAL
    assert result.entities_created == FIXTURE_TOTAL - 1 and result.ambiguous == 1

    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            umoa = (await db.execute(select(ReferenceUniverse).where(
                ReferenceUniverse.country_id.is_(None), ReferenceUniverse.is_current.is_(True)))).scalar_one()
            assert umoa.expected_count == FIXTURE_TOTAL and "TOTAL UMOA" in umoa.expected_count_evidence
            assert umoa.reference_date == date(2025, 12, 31)
            regs = set((await db.execute(select(EntityIdentifier.value))).scalars().all())
            assert regs == {r["reg"] for rows in fixture_banks().values() for r in rows if r["reg"] != "Z 9701 A"}
            inst = (await db.execute(select(Institution).where(Institution.regulatory_id == "Z 9001 A"))).scalar_one()
            assert inst.entity_id and inst.institution_type == "bank"
            listings = (await db.execute(select(EntitySource).where(
                EntitySource.link_role == "regulatory_listing"))).scalars().all()
            assert len(listings) == FIXTURE_TOTAL - 1 and {s.lifecycle_status for s in listings} == {"ACTIVE"}
            links = (await db.execute(select(func.count()).select_from(DocumentEntity).where(
                DocumentEntity.link_type == "reference_listing"))).scalar_one()
            assert links == FIXTURE_TOTAL - 1
        await engine.dispose()

    asyncio.run(check())


def test_second_materialization_is_idempotent(pg) -> None:
    models = (Entity, Institution, EntityIdentifier, EntityName, EntitySource, DocumentEntity,
              ReferenceUniverse, ReferenceUniverseMember, EntityRelationship, Document)
    before = {m.__name__: asyncio.run(_count(pg["url"], m)) for m in models}
    result = asyncio.run(_materialize(pg["url"], pg["storage"], LIST_2025))
    after = {m.__name__: asyncio.run(_count(pg["url"], m)) for m in models}
    assert before == after
    assert result.entities_created == 0


def test_branch_is_linked_to_parent_not_merged(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            branch = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9402 D"))).scalar_one()
            parent = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9602 C"))).scalar_one()
            assert branch.id != parent.id
            rel = (await db.execute(select(EntityRelationship).where(
                EntityRelationship.source_entity_id == branch.id))).scalar_one()
            assert rel.relationship_type == "branch_of" and rel.target_entity_id == parent.id
            assert rel.document_id and rel.page_number
        await engine.dispose()

    asyncio.run(check())


def test_ambiguous_line_goes_to_review_and_lowers_coverage(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            member = (await db.execute(select(ReferenceUniverseMember).join(
                ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id).where(
                ReferenceUniverse.is_current.is_(True), ReferenceUniverseMember.registration_number == "Z 9701 A"
            ))).scalar_one()
            assert member.resolution_status == "ambiguous" and member.entity_id is None
            assert "FIXTURE BANK ALPHA TOGO INTERNATIONAL" in {c["name"] for c in member.candidate_entity_ids}
            snap = await compute_coverage(db, UNIVERSE)
            tg = snap.countries["TG"]
            assert (tg.expected, tg.matched, tg.entity_ratio, tg.status) == (1, 0, 0.0, "INCOMPLETE")
            assert snap.entity_ratio == round((FIXTURE_TOTAL - 1) / FIXTURE_TOTAL, 4)
            await GapQueue().reconcile(db, snap)
            await db.commit()
            gap = (await db.execute(select(DiscoveryGap).where(DiscoveryGap.member_id == member.id))).scalar_one()
            assert gap.gap_type == "ENTITY_UNRESOLVED" and gap.status == "OPEN"
        await engine.dispose()

    asyncio.run(check())


def test_demo_entities_have_zero_influence(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            snap = await compute_coverage(db, UNIVERSE)
            names = {e.name for e in snap.entities}
            assert "FIXTURE DEMO BANK" not in names
            assert "FIXTURE DEMO BANK" in {o["name"] for o in snap.orphan_institutions}
            assert snap.expected_total == FIXTURE_TOTAL and len(snap.entities) == FIXTURE_TOTAL - 1
            assert snap.level("financial_data")["found"] == 0  # the demo observation is never counted
            assert snap.level("financial_document")["found"] == 0
        await engine.dispose()

    asyncio.run(check())


def test_newer_snapshot_keeps_name_history(pg) -> None:
    result = asyncio.run(_materialize(pg["url"], pg["storage"], LIST_2026, url_suffix="list-2026.pdf"))
    assert result.entities_created == 0

    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            entity = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9001 A"))).scalar_one()
            assert entity.canonical_name == "FIXTURE BANK OMEGA BÉNIN"
            officials = (await db.execute(select(EntityName).where(
                EntityName.entity_id == entity.id, EntityName.name_type == "official"))).scalars().all()
            by_name = {n.name: n for n in officials}
            old, new = by_name["FIXTURE BANK ALPHA BÉNIN"], by_name["FIXTURE BANK OMEGA BÉNIN"]
            assert old.valid_from == date(2025, 12, 31) and old.valid_to is not None and old.valid_to < new.valid_from
            assert new.valid_from == date(2026, 6, 30) and new.valid_to is None
            current = (await db.execute(select(ReferenceUniverse).where(
                ReferenceUniverse.country_id.is_(None), ReferenceUniverse.is_current.is_(True)))).scalar_one()
            assert current.reference_date == date(2026, 6, 30)
            former = (await db.execute(select(EntityName).where(
                EntityName.name_type == "former", EntityName.name == "FIXTURE BANQUE ANCIENNE"))).scalar_one()
            assert former.valid_to is not None
        await engine.dispose()

    asyncio.run(check())


# =========================================================================== data integrity
def test_fascicle_values_respect_protected_statuses_and_missing_cells(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            entity = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9101 A"))).scalar_one()
            inst = (await db.execute(select(Institution).where(Institution.entity_id == entity.id))).scalar_one()
            bceao = (await db.execute(select(Source).where(Source.short_name == "BCEAO"))).scalar_one()
            doc = Document(title="FIXTURE FASCICLE", document_type="financial_statement", source_id=bceao.id,
                           download_status="downloaded", extraction_status="skipped")
            db.add(doc)
            await db.flush()
            now = datetime.now(UTC)
            verified = FinancialData(
                institution_id=inst.id, entity_id=entity.id, source_id=bceao.id, document_id=doc.id,
                metric_code="total_actifs", period_year=2023, value_original="1 000", value_normalized=Decimal(1),
                status="verified", verified_at=now, verified_by="fixture-reviewer")
            rejected = FinancialData(
                institution_id=inst.id, entity_id=entity.id, source_id=bceao.id, document_id=doc.id,
                metric_code="resultat_net", period_year=2023, value_original="5", status="rejected")
            db.add_all([verified, rejected])
            await db.flush()
            page = FasciclePage(10, "BF", "FX", "balance_sheet", "FIXTURE", True, values=[
                FascicleValue("total_actifs", "TOTAL DE L'ACTIF", 2023, "999 999", Decimal(999999)),
                FascicleValue("resultat_net", "RESULTAT NET", 2023, "777", Decimal(777)),
                FascicleValue("creances_clients", "CREANCES SUR LA CLIENTELE", 2022, "0", Decimal(0)),
            ])
            ctx = DiscoveryContext(db=db, fetcher=None, registrar=None, resolver=None, run=None,  # type: ignore[arg-type]
                                   universe_code=UNIVERSE, country_codes=("BF",), target_years=[2023])
            created = await BceaoFascicleStrategy()._store_values(ctx, doc, bceao, entity.id, [page])
            await db.commit()
            assert created == 1  # only the unprotected, printed value
            await db.refresh(verified)
            await db.refresh(rejected)
            assert (verified.status, verified.value_original) == ("verified", "1 000")
            assert (rejected.status, rejected.value_original) == ("rejected", "5")
            new = (await db.execute(select(FinancialData).where(
                FinancialData.document_id == doc.id, FinancialData.metric_code == "creances_clients"))).scalar_one()
            # a printed "0" is a published value; the scope guard holds it for review
            assert new.value_normalized == Decimal(0) and new.status == "needs_review"
            assert new.scope_evidence_class == "C" and "scope_inferred_from_regulatory" in new.notes
            # metrics absent from the page are absent from the database (never NULL → 0)
            missing = (await db.execute(select(func.count()).select_from(FinancialData).where(
                FinancialData.document_id == doc.id, FinancialData.metric_code == "depots_clients"))).scalar_one()
            assert missing == 0
        await engine.dispose()

    asyncio.run(check())


def test_source_lifecycle_transitions(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            entity = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9301 A"))).scalar_one()
            ctx = DiscoveryContext(db=db, fetcher=None, registrar=None, resolver=None, run=None,  # type: ignore[arg-type]
                                   universe_code=UNIVERSE, country_codes=("GW",), target_years=[2023])
            ctx.run = type("R", (), {"id": None})()
            url = "https://fixture.invalid/"
            args = dict(entity_id=entity.id, role="official_website", url=url, source_id=None, method="test")
            assert await upsert_entity_source(ctx, status="CANDIDATE", evidence="found", **args)
            assert not await upsert_entity_source(ctx, status="VERIFIED", evidence="name on page", **args)
            await upsert_entity_source(ctx, status="ACTIVE", evidence="pdf stored", **args)
            await upsert_entity_source(ctx, status="CANDIDATE", evidence="temporarily unreachable", **args)
            link = (await db.execute(select(EntitySource).where(EntitySource.url == url))).scalar_one()
            assert link.lifecycle_status == "ACTIVE" and link.verified_at is not None  # never silently downgraded
            await upsert_entity_source(ctx, status="BLOCKED", evidence="HTTP 403", **args)
            assert link.lifecycle_status == "BLOCKED"
            await db.rollback()
        await engine.dispose()

    asyncio.run(check())


# =========================================================================== search loop (stubs)
class _StubFetcher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class _Reference(DiscoveryStrategy):
    code, description, priority, always_run = "stub_reference", "stub reference", 1, True

    def __init__(self, available: bool = True) -> None:
        self.available = available

    async def run(self, ctx, targets):
        return StrategyResult(reference_unavailable=not self.available,
                              reference_reason=None if self.available else "stub: official list unreachable")


class _Searcher(DiscoveryStrategy):
    def __init__(self, code: str, handles: set[str], progress_calls: int = 0) -> None:
        self.code, self.description, self.priority = code, f"stub {code}", 3
        self.handles = frozenset(handles)
        self.progress_calls = progress_calls
        self.calls = 0

    async def run(self, ctx, targets):
        self.calls += 1
        return StrategyResult(targets=len(targets), sources_found=1 if self.calls <= self.progress_calls else 0)


async def _run_engine(url: str, strategies, universe=UNIVERSE):
    engine, maker = await _session(url)
    async with maker() as db:
        run = await DiscoveryEngine(strategies=strategies, fetcher_factory=_StubFetcher,
                                    registrar=DocumentRegistrar(StorageManager("."))).run(
            db, universe_code=universe, trigger_type="test")
        rounds = (await db.execute(select(DiscoveryRound).where(DiscoveryRound.run_id == run.id)
                                   .order_by(DiscoveryRound.round_number))).scalars().all()
        gaps = (await db.execute(select(DiscoveryGap))).scalars().all()
    await engine.dispose()
    return run, rounds, gaps


def test_engine_stops_c_when_official_reference_unavailable(pg) -> None:
    run, rounds, _ = asyncio.run(_run_engine(
        pg["url"], [_Reference(available=False), _Searcher("stub_docs", {"FINANCIAL_DOCUMENT"})],
        universe="FIXTURE.EMPTY"))
    assert run.stop_condition == "C_REFERENCE_UNAVAILABLE"
    assert "COVERAGE INCOMPLETE" in run.stop_reason and "unreachable" in run.stop_reason
    assert [r.strategy_code for r in rounds] == ["stub_reference"]  # nothing is searched without a universe


def test_engine_keeps_searching_while_gaps_remain_then_stops_b(pg) -> None:
    docs = _Searcher("stub_docs", {"FINANCIAL_DOCUMENT", "FINANCIAL_DATA"}, progress_calls=1)
    web = _Searcher("stub_web", {"SOURCE_NOT_FOUND", "DOCUMENT_NOT_FOUND"})
    run, rounds, gaps = asyncio.run(_run_engine(pg["url"], [_Reference(), docs, web]))
    codes = [r.strategy_code for r in rounds]
    # pass 1 (docs made progress) → pass 2 → no progress → stop B; never stopped after a fixed count
    assert codes == ["stub_reference", "stub_docs", "stub_web", "stub_docs", "stub_web"]
    assert run.stop_condition == "B_STRATEGIES_EXHAUSTED"
    assert all(r.coverage_before and r.coverage_after for r in rounds)
    doc_gaps = [g for g in gaps if g.gap_type == "FINANCIAL_DOCUMENT"]
    assert doc_gaps and {g.status for g in doc_gaps} == {"NOT_FOUND"}
    assert all(g.next_attempt_at is not None and "stub_docs" in g.strategies_tried for g in doc_gaps)
    unresolved = [g for g in gaps if g.gap_type == "ENTITY_UNRESOLVED"]
    current = [g for g in unresolved if g.status != "RESOLVED"]
    assert len(current) == 1 and current[0].status == "OPEN"  # human-only: never NOT_FOUND
    # the same ambiguous line in the superseded 2025 snapshot is closed with an explicit reason
    assert all("superseded" in g.reason for g in unresolved if g.status == "RESOLVED")


def test_engine_stops_a_once_every_official_line_is_resolved(pg) -> None:
    async def human_resolution() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            member = (await db.execute(select(ReferenceUniverseMember).join(
                ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id).where(
                ReferenceUniverse.is_current.is_(True), ReferenceUniverseMember.registration_number == "Z 9701 A"
            ))).scalar_one()
            near = (await db.execute(select(Entity).where(
                Entity.canonical_name == "FIXTURE BANK ALPHA TOGO INTERNATIONAL"))).scalar_one()
            member.entity_id, member.resolution_status = near.id, "matched"
            member.resolution_method, member.review_decision = "human_review", "confirmed"
            member.decided_by, member.decided_at = "fixture-reviewer", datetime.now(UTC)
            await db.commit()
        await engine.dispose()

    asyncio.run(human_resolution())
    # Before the official list is read again, the confirmed entity has no regulatory source yet:
    # the engine refuses to call the universe covered.
    run, _, _ = asyncio.run(_run_engine(pg["url"], [_Reference(), _Searcher("stub_reg", {"REGULATORY_SOURCE"})]))
    assert run.stop_condition == "B_STRATEGIES_EXHAUSTED"

    # The reference round re-reads the same official list: the human decision is kept and the
    # confirmed link now carries the official evidence (registration number, regulatory listing).
    asyncio.run(_materialize(pg["url"], pg["storage"], LIST_2026, url_suffix="list-2026.pdf"))
    run, _, _ = asyncio.run(_run_engine(pg["url"], [_Reference(), _Searcher("stub_reg", {"REGULATORY_SOURCE"})]))
    assert run.stop_condition == "A_UNIVERSE_COVERED", run.stop_reason
    assert run.coverage_after["matched"] == run.coverage_after["expected"] == FIXTURE_TOTAL

    async def still_confirmed() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            member = (await db.execute(select(ReferenceUniverseMember).join(
                ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id).where(
                ReferenceUniverse.is_current.is_(True), ReferenceUniverseMember.registration_number == "Z 9701 A"
            ))).scalar_one()
            assert member.review_decision == "confirmed" and member.resolution_status == "matched"
            ident = (await db.execute(select(EntityIdentifier).where(EntityIdentifier.value == "Z 9701 A"))).scalar_one()
            assert ident.entity_id == member.entity_id
        await engine.dispose()

    asyncio.run(still_confirmed())
