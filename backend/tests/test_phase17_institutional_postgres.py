"""
Phase 17 — institution-specific documents against PostgreSQL: migration 0013, extraction of an
institution document (needs_review / class D / unit not stated → not normalized), idempotence,
hash dedup, scanned document, source lifecycle (ACTIVE only after parsing), protected statuses,
BRVM pagination, coverage levels. Synthetic fixtures only. No network (stub fetcher).
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.models.discovery import EntityIdentifier, EntitySource
from app.models.document import Document
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.source import Source
from scraping.storage.manager import StorageManager
from scraping.universe.coverage import compute_coverage
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.http import FetchResult
from scraping.universe.resolution import EntityResolver
from scraping.universe.strategies.base import DiscoveryContext
from scraping.universe.strategies.institution_documents import (
    BrvmIssuerFilingsStrategy,
    InstitutionDocumentExtractionStrategy,
)
from tests.fixtures_phase15 import build_synoptic_pdf, build_text_pdf
from tests.test_migration_postgres_phase2 import _dsn, _fetchval
from tests.test_phase15_discovery_postgres import (
    LIST_2025,
    UNIVERSE,
    _alembic,
    _drop,
    _fresh_db,
    _materialize,
    _session,
)
from tests.test_phase17_institutional_unit import LEFT, RIGHT

CHECKSUM = ("SELECT md5(string_agg(id || value_original || coalesce(value_normalized::text, '') || status, ',' "
            "ORDER BY id)) FROM financial_data")
SYNOPTIC = build_synoptic_pdf(LEFT, RIGHT, title="FIXTURE BANK ALPHA BURKINA")
SCANNED = build_text_pdf([[], []])


# =========================================================================== migration 0013
def test_migration_0013_roundtrip() -> None:
    params, name = _fresh_db("phase17_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0013_institutional_discovery")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0013_institutional_discovery"
        assert asyncio.run(_fetchval(
            dsn, "SELECT count(*) FROM information_schema.columns WHERE table_name='documents' "
                 "AND column_name IN ('text_layer_status','file_format','reporting_year')")) == 3
        _alembic("0012_scope_evidence_and_document_scope", "downgrade")
        assert asyncio.run(_fetchval(
            dsn, "SELECT count(*) FROM information_schema.columns WHERE table_name='documents' "
                 "AND column_name='text_layer_status'")) == 0
        _alembic("0013_institutional_discovery")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0013_institutional_discovery"
    finally:
        _drop(params, name)


# =========================================================================== shared DB
@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    params, name = _fresh_db("phase17_institutional_pytest")
    _alembic("head")
    url = _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    storage = tmp_path_factory.mktemp("phase17_store")
    asyncio.run(_materialize(url, storage, LIST_2025))
    yield {"url": url, "storage": storage, "dsn": _dsn(params, name)}
    _drop(params, name)


async def _ctx(db, storage) -> DiscoveryContext:
    resolver = EntityResolver()
    await resolver.load(db)
    run = type("R", (), {"id": None})()
    return DiscoveryContext(db=db, fetcher=None, registrar=DocumentRegistrar(StorageManager(storage)),  # type: ignore
                            resolver=resolver, run=run, universe_code=UNIVERSE, country_codes=("BF",),
                            target_years=[2022])


async def _entity(db, reg: str) -> Entity:
    return (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                             .where(EntityIdentifier.value == reg))).scalar_one()


async def _register(url: str, storage, content: bytes, title: str, link: str) -> str:
    engine, maker = await _session(url)
    async with maker() as db:
        ctx = await _ctx(db, storage)
        entity = await _entity(db, "Z 9101 A")
        bceao = (await db.execute(select(Source).where(Source.short_name == "BCEAO"))).scalar_one()
        reg = await ctx.registrar.register_pdf(db, source=bceao, url=link, content=content, title=title,
                                               document_type="annual_report", entity_id=entity.id,
                                               document_scope="institution_specific")
        db.add(EntitySource(entity_id=entity.id, source_id=bceao.id, url=link, link_role="official_publications",
                            priority=3, lifecycle_status="VERIFIED", discovery_method="fixture",
                            evidence_document_id=reg.document.id))
        await db.commit()
        doc_id = reg.document.id
    await engine.dispose()
    return doc_id


async def _extract(url: str, storage) -> dict:
    engine, maker = await _session(url)
    async with maker() as db:
        ctx = await _ctx(db, storage)
        res = await InstitutionDocumentExtractionStrategy().run(ctx, [])
        await db.commit()
    await engine.dispose()
    return {"created": res.new_observations, "details": res.details}


def test_hash_dedup_of_institution_documents(pg) -> None:
    a = asyncio.run(_register(pg["url"], pg["storage"], SYNOPTIC, "FIXTURE Bilan 2022", "https://fixture.invalid/a.pdf"))
    b = asyncio.run(_register(pg["url"], pg["storage"], SYNOPTIC, "FIXTURE Bilan 2022", "https://fixture.invalid/b.pdf"))
    assert a == b  # same bytes → same document (content-addressed)


def test_extraction_needs_review_class_d_and_unit_not_stated(pg) -> None:
    out = asyncio.run(_extract(pg["url"], pg["storage"]))
    assert out["created"] == 7  # 4 mapped lines × 2 years − blank capitaux_propres 2022 (check line not stored)

    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            rows = (await db.execute(select(FinancialData))).scalars().all()
            assert {r.status for r in rows} == {"needs_review"}
            assert {r.scope_evidence_class for r in rows} == {"D"}
            assert all(r.value_normalized is None and r.unit_original is None for r in rows)  # unit not stated
            assert all(any(f["code"] == "unit_or_currency_not_stated" for f in r.quality_flags) for r in rows)
            assert all(r.source_location and r.page_number == 1 for r in rows)
            doc = (await db.execute(select(Document).where(Document.document_scope == "institution_specific")))\
                .scalars().one()
            assert doc.text_layer_status == "machine_readable" and doc.extraction_status == "extracted"
            assert doc.extracted_at is not None
            links = (await db.execute(select(EntitySource).where(
                EntitySource.link_role == "official_publications"))).scalars().all()
            assert {lk.url for lk in links} == {"https://fixture.invalid/a.pdf", "https://fixture.invalid/b.pdf"}
            link = next(lk for lk in links if lk.url.endswith("/a.pdf"))
            assert link.lifecycle_status == "ACTIVE"  # source → document → parse → provenance proven
        await engine.dispose()

    asyncio.run(check())


def test_rerun_idempotent_and_protected(pg) -> None:
    async def protect() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            row = (await db.execute(select(FinancialData).where(FinancialData.metric_code == "total_actifs",
                                                                FinancialData.period_year == 2022))).scalar_one()
            row.status = "rejected"
            doc = (await db.execute(select(Document).where(Document.document_scope == "institution_specific")))\
                .scalars().one()
            doc.extracted_at = None  # force a second analysis of the same document
            await db.commit()
        await engine.dispose()

    asyncio.run(protect())
    before = asyncio.run(_fetchval(pg["dsn"], CHECKSUM))
    count = asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data"))
    out = asyncio.run(_extract(pg["url"], pg["storage"]))
    assert out["created"] == 0
    assert asyncio.run(_fetchval(pg["dsn"], CHECKSUM)) == before
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data")) == count
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT status FROM financial_data WHERE metric_code='total_actifs' "
                                            "AND period_year=2022")) == "rejected"


def test_scanned_document_yields_no_observation(pg) -> None:
    asyncio.run(_register(pg["url"], pg["storage"], SCANNED, "FIXTURE scanned report", "https://fixture.invalid/s.pdf"))
    count = asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data"))
    asyncio.run(_extract(pg["url"], pg["storage"]))
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data")) == count
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT text_layer_status FROM documents WHERE title='FIXTURE scanned report'")) \
        == "not_machine_readable"
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT lifecycle_status FROM entity_sources WHERE "
                                            "url='https://fixture.invalid/s.pdf'")) == "VERIFIED"  # never ACTIVE


def test_coverage_levels_and_gaps(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            snap = await compute_coverage(db, UNIVERSE)
            assert snap.level("institution_specific_document")["found"] == 1
            assert snap.level("machine_readable_document")["found"] == 1
            assert snap.level("regulatory_document")["found"] == 0
            assert snap.level("financial_observation")["found"] == 1
            assert snap.level("verified_source")["found"] == 1  # the ACTIVE publication
            assert snap.level("financial_validation")["found"] == 0
            n = await db.scalar(select(func.count()).select_from(FinancialData))
            assert snap.provenance["observations"] == n and snap.provenance["complete"] == n
        await engine.dispose()

    asyncio.run(check())


# =========================================================================== BRVM pagination (stub fetcher)
class _PagedFetcher:
    def __init__(self, pages: list[list[tuple[str, str]]]):
        self.pages = pages
        self.calls: list[str] = []

    async def get(self, url: str) -> FetchResult:
        self.calls.append(url)
        if "rapports-societes-cotees" in url:
            n = int(url.rsplit("page=", 1)[-1])
            items = self.pages[min(n, len(self.pages) - 1)]
            html = "".join(f'<a href="/fr/rapports-societe-cotes/{s}">{t}</a>' for s, t in items)
            return FetchResult(url=url, final_url=url, status_code=200, content=html.encode())
        return FetchResult(url=url, final_url=url, status_code=200, content=b"<html>no pdf</html>")


def test_brvm_listing_reads_every_page(pg) -> None:
    pages = [[("a", "FIXTURE A"), ("b", "FIXTURE B")], [("c", "FIXTURE C")], [("d", "FIXTURE D")],
             [("d", "FIXTURE D")]]  # page 3 repeats → end of listing

    async def run() -> dict:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            ctx = await _ctx(db, pg["storage"])
            ctx.fetcher = _PagedFetcher(pages)
            res = await BrvmIssuerFilingsStrategy().run(ctx, [])
            await db.rollback()
        await engine.dispose()
        return res.details

    details = asyncio.run(run())
    assert details["issuers_listed"] == 4 and details["listing_pages"] == 3
    assert details["attributed"] == [] and details["issuers_without_annual_filings"] == 4


# =========================================================================== engine robustness
class _Boom:
    code, description, priority, always_run, enabled, disabled_reason = "stub_boom", "raises", 3, False, True, None
    handles = frozenset({"SOURCE_NOT_FOUND"})

    async def run(self, ctx, targets):
        raise RuntimeError("fixture: source failure")


class _RefOk:
    code, description, priority, always_run, enabled, disabled_reason = "stub_ref", "ok", 1, True, True, None
    handles = frozenset()

    async def run(self, ctx, targets):
        from scraping.universe.strategies.base import StrategyResult

        return StrategyResult()


class _NoopFetcher:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None


class _BrokenFetcher:
    async def __aenter__(self):
        raise ConnectionError("fixture: database / network interruption")

    async def __aexit__(self, *exc):
        return None


def test_strategy_failure_is_recorded_and_run_completes(pg) -> None:
    from scraping.universe.engine import DiscoveryEngine

    async def go():
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            run = await DiscoveryEngine(strategies=[_RefOk(), _Boom()], fetcher_factory=_NoopFetcher,
                                        registrar=DocumentRegistrar(StorageManager(pg["storage"]))).run(
                db, universe_code=UNIVERSE, trigger_type="test")
            out = (run.status, run.stop_condition, run.errors)
        await engine.dispose()
        return out

    status, stop, errors = asyncio.run(go())
    assert status == "completed" and stop == "B_STRATEGIES_EXHAUSTED"
    assert any("fixture: source failure" in e["error"] for e in errors)


def test_interrupted_run_is_marked_failed_never_left_running(pg) -> None:
    from scraping.universe.engine import DiscoveryEngine

    async def go():
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            run = await DiscoveryEngine(strategies=[_RefOk()], fetcher_factory=_BrokenFetcher,
                                        registrar=DocumentRegistrar(StorageManager(pg["storage"]))).run(
                db, universe_code=UNIVERSE, trigger_type="test")
            out = (run.status, run.stop_reason, run.finished_at is not None)
        await engine.dispose()
        return out

    status, reason, finished = asyncio.run(go())
    assert status == "failed" and finished and "interrupted" in reason
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM discovery_runs WHERE status='running'")) == 0


# =========================================================================== unit re-read (repair)
MXOF = build_synoptic_pdf(LEFT, RIGHT, title="FIXTURE BANK ALPHA BURKINA MXOF",
                          unit_line="Données financières en millions (MXOF)")


def test_reread_units_corrects_rows_stored_with_a_wrong_unit(pg) -> None:
    from scraping.universe.unit_repair import reread_units

    doc_id = asyncio.run(_register(pg["url"], pg["storage"], MXOF, "FIXTURE etats financiers MXOF",
                                   "https://fixture.invalid/mxof.pdf"))
    asyncio.run(_extract(pg["url"], pg["storage"]))

    async def corrupt_then_repair(apply: bool) -> tuple[dict, list[tuple]]:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            rows = (await db.execute(select(FinancialData).where(FinancialData.document_id == doc_id)
                                     .order_by(FinancialData.metric_code, FinancialData.period_year))).scalars().all()
            assert rows and {r.unit_original for r in rows} == {"millions"}  # the fixed parser reads MXOF
            if apply:  # simulate rows stored by the former parser (unit read from a per-share label)
                for r in rows:
                    r.unit_original = "unit"
                    r.value_normalized = r.value_normalized / 1_000_000
                rows[0].status = "reviewed"  # human-protected: never touched
                await db.commit()
            registrar = DocumentRegistrar(StorageManager(pg["storage"]))
            dry = await reread_units(db, registrar, dry_run=True)
            assert len(dry.corrected) == len(rows) - 1 and dry.protected_skipped == 1
            still = (await db.execute(select(FinancialData.unit_original).where(
                FinancialData.document_id == doc_id))).scalars().all()
            assert set(still) == {"unit"}  # dry run writes nothing
            report = await reread_units(db, registrar, dry_run=False)
            after = (await db.execute(select(FinancialData).where(FinancialData.document_id == doc_id)
                                      .order_by(FinancialData.metric_code, FinancialData.period_year))).scalars().all()
            out = [(r.unit_original, r.value_normalized, r.status, r.quality_flags, r.notes) for r in after]
        await engine.dispose()
        return report.summary(), out

    summary, rows = asyncio.run(corrupt_then_repair(apply=True))
    assert summary["corrected"] == len(rows) - 1 and summary["protected_skipped"] == 1
    protected, *fixed = rows
    assert protected[0] == "unit" and protected[2] == "reviewed"
    for unit, value, _status, flags, notes in fixed:
        assert unit == "millions" and value >= 1_000_000
        assert any(f["code"] == "unit_reread" for f in flags) and "unit re-read" in notes
        assert not any(f["code"] == "unit_or_currency_not_stated" for f in flags)
