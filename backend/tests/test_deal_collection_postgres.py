"""
Automated deal collection (migration 0020) against a REAL PostgreSQL database (scratch databases only).

No network: a stub fetcher serves the captured pages of tests/fixtures/deals (and two synthetic pages
built in this file: a BOAD list and a BOC announcing the listing of a bond already indexed by the AMF).
Covers: migration 0020 round trip and downgrade refusal; the five collectors end to end (needs_review,
source class, field-level excerpts, coherence with the source documents); restricted pages reported and
never bypassed; idempotence through ingestion keys and checkpoints; cross-source duplicate candidates
never merged; verification only through the review workflow (an AMF index entry alone cannot be
verified); the "deals" phase of the ingestion run; the trigger API per source and scope.
"""
from __future__ import annotations

import asyncio
import html as html_lib
import json
from collections.abc import AsyncGenerator
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from app.models.deal import (
    Deal,
    DealCollectionCheckpoint,
    DealDuplicateCandidate,
    DealFieldSource,
    DealSource,
)
from app.models.source import Source
from scraping.deals.collect import amf_umoa, boad, brvm, ifc, proparco
from scraping.storage.manager import StorageManager
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.http import FetchResult
from tests.fixtures_umoa_titres import pdf_from_pages
from tests.test_migration_postgres_phase2 import _dsn, _fetchval
from tests.test_phase15_discovery_postgres import _alembic, _drop, _fresh_db, _session

FX = Path(__file__).parent / "fixtures" / "deals"
DQ = "/api/v1/data-quality"
SINCE = date(2010, 1, 1)
BOAD_AFG = boad.BASE_URL + boad.PROJECT_PREFIX + "mise-en-place-dune-ligne-de-refinancement-en-faveur-de-afg-bank-mali/"
BOAD_DONSIN = boad.BASE_URL + boad.PROJECT_PREFIX + "construction-de-laeroport-international-de-ouagadougou-donsin-au-burkina-faso/"
BOAD_LOCKED = boad.BASE_URL + boad.PROJECT_PREFIX + "projet-reserve/"
BOC = "https://www.brvm.org/sites/default/files/boc_{}_2.pdf"


def fx(*parts: str) -> bytes:
    return FX.joinpath(*parts).read_bytes()


def boad_list() -> bytes:
    def item(url: str, title: str, day: str, price: str) -> dict:
        return {"link": url.replace(boad.BASE_URL, ""), "title": title, "acf": {"date": day, "price": price}}

    page = {"component": "Page", "props": {"blocks": [{"acf_fc_layout": "projects_header_block", "projects": {
        "current_page": 1, "last_page": 1, "data": [
            item(BOAD_AFG, "Ligne AFG Bank Mali", "25/06/2025", "10 Mds"),
            item(BOAD_DONSIN, "Aéroport de Donsin", "09/10/2025", "5,9 Mds"),
            item(BOAD_LOCKED, "Projet réservé", "01/07/2025", "1 Md"),
        ]}}]}}
    return f'<div id="app" data-page="{html_lib.escape(json.dumps(page), quote=True)}"></div>'.encode()


def boc_index(*days: str) -> bytes:
    return "".join(f'<a href="{BOC.format(d)}">Télécharger</a>' for d in days).encode()


def pad_listing_boc() -> bytes:
    """A BOC announcing the first listing of the PAD bond indexed by the AMF (operation 359)."""
    return pdf_from_pages([["OPERATIONS EN COURS", "Emetteur", "Opération", "PORT AUTONOME DE DAKAR",
                            "Première cotation - PAD 6,60% 2020-2027 (PADS.O3) - Première cotation le 1er octobre 2020",
                            "AVIS", "jeudi 17 septembre 2020"]])


def pages() -> dict[str, tuple[int, bytes]]:
    ok = {
        brvm.INDEX_URL: boc_index("20261014", "20261013"),
        BOC.format("20261014"): fx("brvm", "boc_20261014.pdf"),
        BOC.format("20261013"): fx("brvm", "boc_20261013.pdf"),
        amf_umoa.API_URL: fx("amf", "operations.json"),
        ifc.SITEMAP_URL: fx("ifc", "sitemap_index.xml"),
        "https://disclosures.ifc.org/content/dam/sitemap/disclosures/en/sitemap-disclosures-1.xml": fx("ifc", "sitemap.xml"),
        "https://disclosures.ifc.org/project-detail/SII/49673/orange-mali-s-a": fx("ifc", "sii_49673_orange_mali.html"),
        "https://disclosures.ifc.org/project-detail/SII/48019/star-garments-group-togo-cmt-expansion":
            fx("ifc", "sii_48019_star_garments_togo.html"),
        "https://disclosures.ifc.org/project-detail/SII/47431/gtfp-coris-cote-d-ivoire": fx("ifc", "sii_47431_gtfp_coris_ci.html"),
        "https://disclosures.ifc.org/project-detail/SII/50440/evolution-mobility": fx("ifc", "sii_50440_brazil.html"),
        f"{boad.LIST_URL}?page=1": boad_list(),
        BOAD_AFG: fx("boad", "project_afg_bank_mali.html"),
        BOAD_DONSIN: fx("boad", "project_aeroport_donsin.html"),
        proparco.SITEMAP_URL: fx("proparco", "sitemap_index.xml"),
        "https://www.proparco.fr/sitemap.xml?page=1": fx("proparco", "sitemap.xml"),
    }
    for slug in ("dakar-mobilite", "cofina-senegal", "coris-ci-g-trade-finance", "wiocc-2024"):
        ok[f"https://www.proparco.fr/fr/carte-des-projets/{slug}"] = fx("proparco", f"{slug}.html")
    out = {u: (200, b) for u, b in ok.items()}
    out[BOAD_LOCKED] = (403, b"Forbidden")  # restricted: reported, never bypassed
    return out


class StubFetcher:
    def __init__(self, served: dict[str, tuple[int, bytes]] | None = None) -> None:
        self.served = served if served is not None else pages()
        self.calls: list[str] = []

    async def get(self, url: str) -> FetchResult:
        self.calls.append(url)
        status, body = self.served.get(url, (404, b""))
        return FetchResult(url=url, final_url=url, status_code=status, content=body,
                           error=None if status == 200 else f"HTTP {status}")


# =========================================================================== migration 0020
def test_migration_0020_round_trip_and_downgrade_refusal() -> None:
    params, name = _fresh_db("deal_collection_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0019_fascicle_corroboration")
        _alembic("0020_deal_collection")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns WHERE table_name='deals' "
                                          "AND column_name IN ('debt_amount','equity_amount','debt_type')")) == 3
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns "
                                          "WHERE table_name='deal_field_sources' AND column_name='excerpt'")) == 1
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM sources WHERE short_name IN ('IFC','BOAD','Proparco') "
                                          "AND source_type='development_institution'")) == 3
        assert asyncio.run(_fetchval(dsn, "SELECT to_regclass('public.deal_collection_checkpoints') IS NOT NULL"))
        _alembic("0019_fascicle_corroboration", "downgrade")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM sources WHERE short_name IN ('IFC','BOAD','Proparco')")) == 0
        _alembic("0020_deal_collection")
        asyncio.run(_exec(dsn, "INSERT INTO deals (id, created_at, updated_at, title, debt_amount, currency, status) "
                               "VALUES ('d', now(), now(), 'Projet', 70, 'XOF', 'needs_review')"))
        with pytest.raises(RuntimeError, match="downgrade of 0020 refused"):
            _alembic("0019_fascicle_corroboration", "downgrade")
        asyncio.run(_exec(dsn, "DELETE FROM deals WHERE id = 'd'"))
        _alembic("0019_fascicle_corroboration", "downgrade")
        _alembic("head")
    finally:
        _drop(params, name)


async def _exec(dsn: str, sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


# =========================================================================== shared database
@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    params, name = _fresh_db("deal_collection_pytest")
    _alembic("head")
    url = _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    storage = tmp_path_factory.mktemp("deal_collection_store")
    yield {"url": url, "storage": storage}
    _drop(params, name)


@pytest_asyncio.fixture
async def maker(pg):
    engine, mk = await _session(pg["url"])
    yield mk
    await engine.dispose()


def registrar(pg) -> DocumentRegistrar:
    return DocumentRegistrar(StorageManager(str(pg["storage"])))


async def run_collect(maker, pg, sources: list[str], fetcher: StubFetcher | None = None, **kw):
    from app.services.deal_collection import collect

    async with maker() as db:
        return await collect(db, sources, since=kw.pop("since", SINCE), fetcher=fetcher or StubFetcher(),
                             lock_engine=False, registrar=registrar(pg), **kw)


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


SOURCES = ["brvm", "amf-umoa", "ifc", "boad", "proparco"]


@pytest.mark.asyncio
async def test_1_collect_every_source_end_to_end(maker, pg):
    result = await run_collect(maker, pg, SOURCES)
    assert result.errors == []
    s = result.summaries
    assert s["brvm"]["outcomes"] == {"not_a_deal": 1, "produced": 1}
    assert s["amf-umoa"]["outcomes"] == {"out_of_scope": 1, "produced": 7}
    assert s["ifc"]["outcomes"] == {"out_of_scope": 1, "produced": 3}  # the ESRS page is not an SII
    assert s["boad"]["outcomes"] == {"produced": 2, "restricted": 1}
    assert s["proparco"]["outcomes"] == {"out_of_scope": 1, "produced": 3}  # EN duplicates / news filtered
    assert {k: v["deals_created"] for k, v in s.items()} == {"brvm": 1, "amf-umoa": 7, "ifc": 3, "boad": 2,
                                                              "proparco": 3}
    for summary in s.values():
        assert summary["coherence"]["deals_without_source_document"] == []

    async with maker() as db:
        deals = (await db.execute(select(Deal).where(Deal.ingestion_key.is_not(None)))).scalars().all()
        assert len(deals) == 16 and {d.status for d in deals} == {"needs_review"}
        classes = dict((await db.execute(
            select(DealSource.source_class, func.count()).group_by(DealSource.source_class))).all())
        assert classes == {"primary_market": 1, "regulator_index": 7, "dfi_official": 8}
        # Every financial field of a DFI / market deal carries its own quotation.
        missing = (await db.execute(
            select(func.count()).select_from(DealFieldSource).join(DealSource, DealSource.id == DealFieldSource.deal_source_id)
            .where(DealFieldSource.field_name.in_(("amount", "currency", "interest_rate", "signing_date")),
                   DealFieldSource.excerpt.is_(None)))).scalar_one()
        assert missing == 0
        orange = (await db.execute(select(Deal).where(Deal.ingestion_key == "ifc:sii:49673"))).scalar_one()
        assert (orange.amount, orange.unit, orange.currency, orange.country_id is not None) == (
            Decimal("79.29"), "millions", "USD", True)  # as published: 79.29 million
        # Unpublished values stay NULL — never 0, never an estimate.
        gtfp = (await db.execute(select(Deal).where(Deal.ingestion_key == "ifc:sii:47431"))).scalar_one()
        assert gtfp.amount is None and gtfp.debt_amount is None and gtfp.equity_amount is None
        assert [f["code"] for f in gtfp.validation_flags] == ["program_level_amount"]
        swami = (await db.execute(select(Deal).where(Deal.ingestion_key == "brvm:first_listing:SWAS.O1"))).scalar_one()
        assert swami.amount is None and swami.isin is None and float(swami.interest_rate) == 7.0
        # Documents belong to the collecting sources.
        ifc_source = (await db.execute(select(Source).where(Source.short_name == "IFC"))).scalar_one()
        assert ifc_source.source_type == "development_institution"


@pytest.mark.asyncio
async def test_2_rerun_is_idempotent_and_restricted_pages_are_retried(maker, pg):
    fetcher = StubFetcher()
    result = await run_collect(maker, pg, SOURCES, fetcher=fetcher)
    assert sum(v["deals_created"] for v in result.summaries.values()) == 0
    assert result.summaries["ifc"]["skipped_unchanged"] == 4  # unchanged lastmod: not even fetched
    assert "https://disclosures.ifc.org/project-detail/SII/49673/orange-mali-s-a" not in fetcher.calls
    assert result.summaries["boad"]["outcomes"] == {"restricted": 1}  # retried, still not bypassed
    assert BOAD_LOCKED in fetcher.calls
    async with maker() as db:
        locked = (await db.execute(select(DealCollectionCheckpoint).where(
            DealCollectionCheckpoint.url == BOAD_LOCKED))).scalar_one()
        assert locked.outcome == "restricted" and "403" in locked.detail
        assert (await db.execute(select(func.count()).select_from(Deal))).scalar_one() == 16

    # A modified page (new lastmod) is read again; its deal already exists: nothing is written.
    served = pages()
    served["https://disclosures.ifc.org/content/dam/sitemap/disclosures/en/sitemap-disclosures-1.xml"] = (
        200, fx("ifc", "sitemap.xml").replace(b"2026-06-26", b"2026-10-20"))
    again = await run_collect(maker, pg, ["ifc"], fetcher=StubFetcher(served))
    assert again.summaries["ifc"]["outcomes"] == {"already_imported": 1}
    assert again.summaries["ifc"]["documents_registered"] == 0


@pytest.mark.asyncio
async def test_2b_a_new_parser_version_or_recheck_reads_final_pages_again(maker, pg, monkeypatch):
    """Audit 22/10/2026 (H1): a "final" outcome written by an older parser is not final for a newer one."""
    from scraping.deals.collect.ifc import IfcCollector

    async with maker() as db:
        versions = set((await db.execute(select(DealCollectionCheckpoint.parser_version).where(
            DealCollectionCheckpoint.source_key == "ifc"))).scalars())
    assert versions == {IfcCollector.parser_version}  # every checkpoint records the parser that wrote it

    fetcher = StubFetcher()
    # 3 unchanged (test_2 served a 4th page with another lastmod: that one is read again)
    assert (await run_collect(maker, pg, ["ifc"], fetcher=fetcher)).summaries["ifc"]["skipped_unchanged"] == 3
    monkeypatch.setattr(IfcCollector, "parser_version", IfcCollector.parser_version + 1)
    fetcher = StubFetcher()
    result = await run_collect(maker, pg, ["ifc"], fetcher=fetcher)
    assert result.summaries["ifc"]["skipped_unchanged"] == 0  # read again, nothing duplicated
    assert result.summaries["ifc"]["deals_created"] == 0
    assert "https://disclosures.ifc.org/project-detail/SII/49673/orange-mali-s-a" in fetcher.calls

    result = await run_collect(maker, pg, ["ifc"], fetcher=StubFetcher(), recheck=True)
    assert result.summaries["ifc"]["skipped_unchanged"] == 0


@pytest.mark.asyncio
async def test_3_same_bond_from_amf_and_brvm_is_a_candidate_never_merged(maker, pg):
    served = {brvm.INDEX_URL: (200, boc_index("20200917")), BOC.format("20200917"): (200, pad_listing_boc())}
    result = await run_collect(maker, pg, ["brvm"], fetcher=StubFetcher(served))
    assert result.summaries["brvm"]["deals_created"] == 1 and result.summaries["brvm"]["duplicate_candidates"] == 1
    async with maker() as db:
        amf = (await db.execute(select(Deal).where(Deal.ingestion_key == "amf-umoa:operation:359"))).scalar_one()
        listing = (await db.execute(select(Deal).where(Deal.ingestion_key == "brvm:first_listing:PADS.O3"))).scalar_one()
        cand = (await db.execute(select(DealDuplicateCandidate).where(
            DealDuplicateCandidate.deal_a_id.in_((amf.id, listing.id)),
            DealDuplicateCandidate.deal_b_id.in_((amf.id, listing.id))))).scalar_one()
        assert cand.state == "duplicate_candidate"
        assert cand.matched_criteria == ["label_issuer", "coupon", "tenor_years"]
        assert amf.merged_into_deal_id is None and listing.merged_into_deal_id is None
        assert {amf.status, listing.status} == {"needs_review"}


@pytest.mark.asyncio
async def test_4_verification_only_through_the_review_workflow(api, maker, pg):
    async with maker() as db:
        amf_only = (await db.execute(select(Deal.id).where(Deal.ingestion_key == "amf-umoa:operation:263"))).scalar_one()
        dfi = (await db.execute(select(Deal.id).where(Deal.ingestion_key == "proparco:project:PSN1083"))).scalar_one()
    body = {"actor": "analyst-1", "reason": "Relu sur la source"}
    assert (await api.post(f"{DQ}/deals/{amf_only}/review", json=body)).status_code == 200
    r = await api.post(f"{DQ}/deals/{amf_only}/verify", json=body)
    assert r.status_code == 409 and "secondary_source_only" in r.text  # an index entry is never enough
    assert (await api.post(f"{DQ}/deals/{dfi}/review", json=body)).status_code == 200
    assert (await api.post(f"{DQ}/deals/{dfi}/verify", json=body)).status_code == 200
    detail = (await api.get(f"/api/v1/deals/{dfi}")).json()
    assert detail["status"] == "verified" and detail["debt_equity_ratio"] is None
    assert detail["field_excerpts"]["amount"][0]["excerpt"] == "Montant du financement (€) : 5000000"
    assert detail["sources"][0]["source_class"] == "dfi_official"


class _NoBankPipeline:
    def __getattr__(self, name):
        raise AssertionError(f"the bank-statement pipeline must not run for a deal-only source ({name})")


@pytest.mark.asyncio
async def test_5_ingestion_run_deals_phase_for_one_source(maker, pg, monkeypatch):
    from app.services import deal_collection
    from app.services.ingestion import IngestionService

    real_collect = deal_collection.collect

    async def offline_collect(db, sources, **kw):
        return await real_collect(db, sources, fetcher=StubFetcher(), lock_engine=False, registrar=registrar(pg),
                                  **{**kw, "since": kw.get("since") or SINCE})

    monkeypatch.setattr(deal_collection, "collect", offline_collect)
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "deal_collection_enabled", True)  # off by default in tests
    async with maker() as db:
        run = await IngestionService(pipeline=_NoBankPipeline()).execute_run(
            db, trigger_type="manual", sources=["proparco"], scope="all", force=True)
    assert run.status == "completed" and run.documents_found == 0
    # The four sheets (three deals + one out of UMOA) are unchanged: none is fetched again.
    assert run.deal_summary["proparco"]["outcomes"] == {} and run.deal_summary["proparco"]["skipped_unchanged"] == 4
    assert "Deals created: 0" in run.summary_text


@pytest.mark.asyncio
async def test_6_trigger_api_per_source_and_scope(api, monkeypatch):
    from app.api.v1 import ingestion as ingestion_api

    calls: list[tuple] = []

    async def fake_background(*args):
        calls.append(args)

    monkeypatch.setattr(ingestion_api, "_run_in_background", fake_background)
    r = await api.post("/api/v1/ingestion/trigger", params={"source": "boad", "scope": "deals", "since": "2025-01-01"})
    assert r.status_code == 200 and calls[-1][2:] == ("boad", None, False, "deals", date(2025, 1, 1), None)
    # The first run is still recorded "running" (the background task is faked): a second one is refused
    # instead of being created and left "running" next to it (audit 22/10/2026, F1); force bypasses.
    r = await api.post("/api/v1/ingestion/trigger", params={"source": "umoa-titres"})
    assert r.status_code == 409 and len(calls) == 1
    r = await api.post("/api/v1/ingestion/trigger", params={"source": "umoa-titres", "force": True})
    assert r.status_code == 200 and calls[-1][2] == "umoa-titres" and calls[-1][4] is True and calls[-1][5] == "all"
    assert (await api.post("/api/v1/ingestion/trigger", params={"source": "ifc", "scope": "financial"})).status_code == 422
    assert (await api.post("/api/v1/ingestion/trigger", params={"source": "afdb"})).status_code == 422
    assert (await api.post("/api/v1/ingestion/trigger",
                           params={"source": "brvm", "since": "2026-01-02", "until": "2026-01-01"})).status_code == 422


# =========================================================================== press (decision D4)
def press_pages() -> dict[str, tuple[int, bytes]]:
    from scraping.deals.collect import press
    from scraping.deals.collect.press import meta

    articles = {}
    for name in ("sika_niger_200md.html", "sika_emergence_plaza.html", "ecofin_baobab_slb.html",
                 "ecofin_afinhab.html", "fa_ci_adjudication.html"):
        body = fx("press", name)
        articles[meta(body.decode(), "og:url")] = body
    locked_url = "https://www.sikafinance.com/marches/article-premium_1"
    locked = fx("press", "sika_emergence_plaza.html").decode().replace(
        "arrangé par la SGI HUDSON", "Cet article est réservé aux abonnés. arrangé par la SGI HUDSON")
    articles[locked_url] = locked.encode()
    titles = {url: meta(body.decode(), "og:title") for url, body in articles.items()}
    titles[locked_url] = "Côte d’Ivoire : un emprunt obligataire de 15 milliards FCFA en préparation"
    items = "".join(
        f"<item><title>{html_lib.escape(t)}</title><link>{u}</link><pubDate>Mon, 13 Jul 2026 10:00:00 GMT</pubDate>"
        f"<description>BRVM</description></item>" for u, t in titles.items())
    served = {u: (200, b) for u, b in articles.items()}
    served[press.FEEDS[0]] = (200, f"<rss><channel>{items}</channel></rss>".encode())
    return served  # the two other feeds answer 404: reported, the run goes on


@pytest.mark.asyncio
async def test_7_press_articles_become_press_reported_deals_never_verifiable(api, maker, pg):
    result = await run_collect(maker, pg, ["press"], fetcher=StubFetcher(press_pages()))
    # The two other feeds answer 404: the run goes on, and the partial failure is reported (never silent).
    assert [(e["source"], e["phase"]) for e in result.errors] == [("press", "deals_discovery")] * 2
    s = result.summaries["press"]
    # The auction report is dropped by the feed pre-filter; the paywalled article gives nothing.
    assert s["candidates"] == 5 and s["outcomes"] == {"produced": 4, "restricted": 1}
    async with maker() as db:
        deals = (await db.execute(select(Deal).where(Deal.ingestion_key.like("press:%")))).scalars().all()
        assert len(deals) == 4 and {d.status for d in deals} == {"needs_review"}
        niger = next(d for d in deals if d.country_id and d.title.startswith("Le Niger"))
        sources = (await db.execute(select(DealSource).where(DealSource.deal_id == niger.id))).scalars().all()
        assert [(x.source_class, x.publisher) for x in sources] == [("press_reported", "Sika Finance")]
        # Only a JSON evidence record is stored — never the article body.
        from app.models.document import Document

        doc = await db.get(Document, sources[0].document_id)
        stored = registrar(pg).read_bytes(doc)
        assert doc.file_format == "json" and b"Tranche B" not in stored and b"quotations" in stored
    body = {"actor": "analyst-1", "reason": "Lu dans l'article"}
    assert (await api.post(f"{DQ}/deals/{niger.id}/review", json=body)).status_code == 200
    r = await api.post(f"{DQ}/deals/{niger.id}/verify", json=body)
    assert r.status_code == 409 and "secondary_source_only" in r.text
