"""
Phase 16 — migration 0012 (scope evidence, document scope), fascicle class C, quality flags,
protected statuses, value integrity and separate document coverage, against PostgreSQL.
Synthetic fixtures only ("FIXTURE" names, "Z 9" registration numbers). No network.
"""
from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import func, select

from app.models.discovery import DocumentEntity, EntityIdentifier
from app.models.document import Document
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.source import Source
from scraping.quality.scope import DocumentScopeContext
from scraping.universe.coverage import compute_coverage
from scraping.universe.fascicle import FascicleParser
from scraping.universe.strategies.base import DiscoveryContext
from scraping.universe.strategies.regulatory_fascicle import (
    FASCICLE_CONVENTION_EVIDENCE,
    BceaoFascicleStrategy,
)
from tests.fixtures_phase15 import build_fascicle_pdf
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

CHECKSUM = ("SELECT md5(string_agg(id || value_original || coalesce(value_normalized::text, '') || status, ',' "
            "ORDER BY id)) FROM financial_data")


# =========================================================================== migration 0012
def test_migration_0012_backfill_and_roundtrip_change_no_status_or_value() -> None:
    params, name = _fresh_db("phase16_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0011_entity_source_discovery")

        async def seed() -> None:
            import asyncpg

            conn = await asyncpg.connect(dsn=dsn)
            try:
                bj = await conn.fetchval("SELECT id FROM countries WHERE code = 'BJ'")
                bceao = await conn.fetchval("SELECT id FROM sources WHERE short_name = 'BCEAO'")
                brvm = await conn.fetchval("SELECT id FROM sources WHERE short_name = 'BRVM'")
                await conn.execute(
                    "INSERT INTO entities (id, created_at, updated_at, entity_class, entity_type, canonical_name, "
                    "country_id, status) VALUES ('fx-e', now(), now(), 'financial_institution', 'commercial_bank', "
                    "'FIXTURE BANK ALPHA', $1, 'active')", bj)
                for doc_id, src, title in (("fx-fasc", bceao, "FIXTURE FASCICLE"), ("fx-mkt", brvm, "FIXTURE BOC")):
                    await conn.execute(
                        "INSERT INTO documents (id, created_at, updated_at, title, document_type, source_id, "
                        "download_status, extraction_status) VALUES ($1, now(), now(), $2, 'financial_statement', "
                        "$3, 'downloaded', 'skipped')", doc_id, title, src)
                await conn.execute(
                    "INSERT INTO document_entities (id, created_at, updated_at, document_id, entity_id, link_type) "
                    "VALUES ('fx-de', now(), now(), 'fx-fasc', 'fx-e', 'financial_statement')")
                rows = [
                    ("fx-1", "fx-fasc", "total_actifs", "needs_review", "p | scope not detected", "individual", None),
                    ("fx-2", "fx-fasc", "resultat_net", "needs_review", "p | scope not detected", "individual", None),
                    ("fx-3", "fx-fasc", "depots_clients", "verified", "human", "individual", "fixture-reviewer"),
                    ("fx-4", "fx-mkt", "total_actifs", "needs_review", "scope not detected", "individual", None),
                    ("fx-5", "fx-mkt", "creances_clients", "extracted", "market", "not_applicable", None),
                ]
                for rid, doc, metric, status, notes, cscope, by in rows:
                    await conn.execute(
                        "INSERT INTO financial_data (id, created_at, updated_at, entity_id, source_id, document_id, "
                        "metric_code, scope, consolidation_scope, observation_level, period_type, period_year, "
                        "value_original, value_normalized, status, notes, verified_at, verified_by, "
                        "extraction_method) VALUES ($1, now(), now(), 'fx-e', $2, $3, $4, 'individual', $5, "
                        "'entity', 'annual', 2023, '1 000', 1000000000, $6, $7, "
                        "CASE WHEN $8::text IS NULL THEN NULL ELSE now() END, $8, 'pdf_text')",
                        rid, bceao if doc == "fx-fasc" else brvm, doc, metric, cscope, status, notes, by)
            finally:
                await conn.close()

        asyncio.run(seed())
        before = asyncio.run(_fetchval(dsn, CHECKSUM))

        _alembic("0012_scope_evidence_and_document_scope")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == \
            "0012_scope_evidence_and_document_scope"
        assert asyncio.run(_fetchval(dsn, CHECKSUM)) == before  # no status, no value changed
        q = "SELECT scope_evidence_class || ':' || scope_reason_code FROM financial_data WHERE id = $1"
        for rid in ("fx-1", "fx-2", "fx-3"):
            assert asyncio.run(_fetchval(dsn, q, rid)) == \
                "C:scope_inferred_from_regulatory_per_entity_reporting_convention"
        assert asyncio.run(_fetchval(dsn, q, "fx-4")) == "D:scope_not_stated"
        assert asyncio.run(_fetchval(dsn, "SELECT scope_reason_code FROM financial_data WHERE id='fx-5'")) == \
            "scope_not_applicable"
        assert asyncio.run(_fetchval(dsn, "SELECT document_scope FROM documents WHERE id='fx-fasc'")) == \
            "regulatory_aggregate"
        assert asyncio.run(_fetchval(dsn, "SELECT document_scope FROM documents WHERE id='fx-mkt'")) == "market"
        # automatic 'extracted' on C/D evidence is refused by the database
        import asyncpg

        async def forbidden() -> None:
            conn = await asyncpg.connect(dsn=dsn)
            try:
                with pytest.raises(asyncpg.CheckViolationError):
                    await conn.execute("UPDATE financial_data SET status = 'extracted' WHERE id = 'fx-1'")
            finally:
                await conn.close()

        asyncio.run(forbidden())

        _alembic("0011_entity_source_discovery", "downgrade")
        assert asyncio.run(_fetchval(dsn, CHECKSUM)) == before
        assert asyncio.run(_fetchval(
            dsn, "SELECT count(*) FROM information_schema.columns WHERE table_name='financial_data' "
                 "AND column_name='scope_evidence_class'")) == 0
        _alembic("0012_scope_evidence_and_document_scope")
        assert asyncio.run(_fetchval(dsn, CHECKSUM)) == before
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM financial_data WHERE scope_evidence_class='C'")) == 3
    finally:
        _drop(params, name)


# =========================================================================== fascicle storage
FASCICLE = build_fascicle_pdf([
    {"country": "BURKINA FASO", "code": "FXB", "kind": "Bilans", "label": "FIXTURE BANK ALPHA BURKINA",
     "rows": {"TOTAL DE L'ACTIF": ["0", "1 000", "1 200"], "DETTES A L'EGARD DE LA CLIENTELE": ["0", "0", "700"],
              "CAPITAUX PROPRES ET RESSOURCES ASSIMILEES": ["-5", "10", "20"],
              "RESULTAT DE L'EXERCICE (+/-)": ["1", "2", "9"]}},
    {"country": "BURKINA FASO", "code": "FXB", "kind": "Comptes de résultat", "label": "FIXTURE BANK ALPHA BURKINA",
     "rows": {"PRODUITS NET BANCAIRE": ["50", "60", "70"], "RESULTAT NET": ["1", "2", "3"]}},
])


@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    params, name = _fresh_db("phase16_scope_pytest")
    _alembic("head")
    url = _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    storage = tmp_path_factory.mktemp("phase16_store")
    asyncio.run(_materialize(url, storage, LIST_2025))
    yield {"url": url, "storage": storage, "dsn": _dsn(params, name)}
    _drop(params, name)


async def _store(url: str, *, protect: dict[str, str] | None = None) -> tuple[int, str]:
    engine, maker = await _session(url)
    async with maker() as db:
        entity = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                   .where(EntityIdentifier.value == "Z 9101 A"))).scalar_one()
        bceao = (await db.execute(select(Source).where(Source.short_name == "BCEAO"))).scalar_one()
        doc = (await db.execute(select(Document).where(Document.title == "FIXTURE FASCICLE"))).scalar_one_or_none()
        if doc is None:
            doc = Document(title="FIXTURE FASCICLE", document_type="financial_statement", source_id=bceao.id,
                           download_status="downloaded", extraction_status="skipped",
                           document_scope="regulatory_aggregate")
            db.add(doc)
            await db.flush()
            db.add(DocumentEntity(document_id=doc.id, entity_id=entity.id, link_type="financial_statement",
                                  page_from=1, page_to=2))
        pages = FascicleParser().parse_bytes(FASCICLE).pages
        ctx = DiscoveryContext(db=db, fetcher=None, registrar=None, resolver=None, run=None,  # type: ignore[arg-type]
                               universe_code=UNIVERSE, country_codes=("BF",), target_years=[2023])
        scope_ctx = DocumentScopeContext.from_pdf_bytes(
            FASCICLE, convention_reason="scope_inferred_from_regulatory_per_entity_reporting_convention",
            convention_evidence=FASCICLE_CONVENTION_EVIDENCE)
        created = await BceaoFascicleStrategy()._store_values(ctx, doc, bceao, entity.id, pages, scope_ctx)
        for metric, status in (protect or {}).items():
            row = (await db.execute(select(FinancialData).where(
                FinancialData.document_id == doc.id, FinancialData.metric_code == metric,
                FinancialData.period_year == 2023))).scalar_one()
            row.status = status
            if status == "verified":
                from datetime import UTC, datetime

                row.verified_at, row.verified_by = datetime.now(UTC), "fixture-reviewer"
        await db.commit()
    await engine.dispose()
    return created, doc.id


def test_fascicle_rows_are_class_c_needs_review_with_location_and_flags(pg) -> None:
    created, doc_id = asyncio.run(_store(pg["url"]))
    assert created == 15  # 5 mapped lines (incl. the PNB variant) × 3 years; the check line is not stored

    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            rows = (await db.execute(select(FinancialData).where(FinancialData.document_id == doc_id))).scalars().all()
            assert {r.status for r in rows} == {"needs_review"}
            assert {r.scope_evidence_class for r in rows} == {"C"}
            assert {r.scope_reason_code for r in rows} == {"scope_inferred_from_regulatory_per_entity_reporting_convention"}
            assert all(r.source_location and r.source_location.startswith("p.") for r in rows)
            pnb = [r for r in rows if r.metric_code == "produit_net_bancaire"]
            assert len(pnb) == 3  # "PRODUITS NET BANCAIRE" variant extracted
            by = {(r.metric_code, r.period_year): r for r in rows}
            codes = lambda r: {f["code"] for f in r.quality_flags or []}  # noqa: E731
            assert "zero_on_structural_metric" in codes(by[("total_actifs", 2021)])
            assert "zero_on_structural_metric" in codes(by[("depots_clients", 2022)])
            assert "negative_equity" in codes(by[("capitaux_propres", 2021)])
            assert "cross_statement_mismatch" in codes(by[("resultat_net", 2023)])  # 3 vs balance sheet 9
            assert "cross_statement_mismatch" not in codes(by[("resultat_net", 2022)])
            # values exactly as printed; zeros and negatives kept
            assert by[("total_actifs", 2021)].value_original == "0"
            assert by[("capitaux_propres", 2021)].value_original == "-5"
        await engine.dispose()

    asyncio.run(check())


def test_rerun_is_idempotent_and_protected_statuses_untouched(pg) -> None:
    checksum = lambda: asyncio.run(_fetchval(pg["dsn"], CHECKSUM))  # noqa: E731
    asyncio.run(_store(pg["url"], protect={"total_actifs": "verified", "resultat_net": "rejected",
                                          "depots_clients": "reviewed"}))
    before = checksum()
    count_before = asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data"))
    created, _ = asyncio.run(_store(pg["url"]))
    assert created == 0
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM financial_data")) == count_before
    assert checksum() == before  # values and statuses unchanged, protected rows untouched
    statuses = asyncio.run(_fetchval(pg["dsn"], "SELECT string_agg(DISTINCT status, ',' ORDER BY status) "
                                                "FROM financial_data WHERE period_year = 2023"))
    assert statuses == "needs_review,rejected,reviewed,verified"


def test_coverage_separates_regulatory_from_institution_specific(pg) -> None:
    async def check() -> None:
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            snap = await compute_coverage(db, UNIVERSE)
            assert snap.level("regulatory_document")["found"] == 1
            assert snap.level("institution_specific_document")["found"] == 0
            assert snap.level("financial_observation")["found"] == 1
            assert snap.level("financial_validation")["found"] == 1  # the human-verified fixture row
            assert snap.scope_class_counts == {"C": sum(snap.observation_status_counts.values())}

            entity = (await db.execute(select(Entity).join(EntityIdentifier, EntityIdentifier.entity_id == Entity.id)
                                       .where(EntityIdentifier.value == "Z 9101 A"))).scalar_one()
            bceao = (await db.execute(select(Source).where(Source.short_name == "BCEAO"))).scalar_one()
            own = Document(title="FIXTURE OWN ANNUAL REPORT", document_type="annual_report", source_id=bceao.id,
                           entity_id=entity.id, download_status="downloaded", extraction_status="skipped",
                           document_scope="institution_specific")
            db.add(own)
            await db.flush()
            snap = await compute_coverage(db, UNIVERSE)
            assert snap.level("institution_specific_document")["found"] == 1
            assert snap.level("regulatory_document")["found"] == 1
            n = await db.scalar(select(func.count()).select_from(FinancialData))
            assert snap.provenance["observations"] == n
            await db.rollback()
        await engine.dispose()

    asyncio.run(check())
