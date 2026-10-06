"""
UMOA-Titres OAT auctions -> sovereign_bond deals against PostgreSQL: migration 0014 (upgrade /
downgrade / legacy deals), ingestion through the Phase 13 importer (needs_review, provenance,
audit), sovereign issuer link, idempotence, duplicate candidates, no impact on financial data
or rankings. Synthetic fixtures only; no network (stub fetcher).
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.models.deal import (
    Deal,
    DealDuplicateCandidate,
    DealFieldSource,
    DealParticipant,
    DealSource,
)
from app.models.document import Document
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.review_event import FinancialDataReviewEvent
from app.models.source import Source
from scraping.deals.importer import import_deals, validate_records
from scraping.deals.umoa_titres_auctions import INDEX_URL
from scraping.deals.umoa_titres_ingest import UmoaTitresAuctionIngestor
from scraping.rankings.definitions import get_indicator
from scraping.rankings.service import RankingService
from scraping.storage.manager import StorageManager
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.http import FetchResult
from tests.fixtures_umoa_titres import (
    FxTranche,
    buyback_lines,
    compte_rendu_lines,
    compte_rendu_pdf,
    emission_page_html,
    pdf_from_pages,
)
from tests.test_migration_postgres_phase2 import _dsn, _fetchval
from tests.test_phase15_discovery_postgres import _alembic, _drop, _fresh_db, _session

BASE = "https://www.umoatitres.org/fr/emission/"
URL_ML = BASE + "emission-simultanee-du-tresor-du-mali-du-11-06-2025/"
URL_SN = BASE + "emission-simultanee-du-tresor-du-senegal-du-03-07-2025/"
URL_TG = BASE + "emission-simultanee-du-tresor-du-togo-du-04-08-2025/"
URL_BF = BASE + "emission-simultanee-du-tresor-du-burkina-du-05-09-2025/"
URL_OLD = BASE + "emission-simultanee-du-tresor-du-mali-du-10-12-2024/"
URL_GW = BASE + "emission-simultanee-du-tresor-de-guinee-bissau-du-06-10-2025/"
URL_EC = BASE + "rachat-et-emission-simultanee-du-tresor-du-niger-du-10-11-2025/"
CR = "https://www.umoatitres.org/wp-content/uploads/2025/Compte-Rendu-{}-ES.pdf"

ML = [
    FxTranche("ML0000009917", "BAT", "364 jours", "10/06/2026", "20 010", "9,35%", ref_code="BT1A"),
    FxTranche("ML0000009925", "OAT", "3 ans", "12/06/2028", "10 345", "9,22%", "6,15%"),
    FxTranche("ML0000009933", "OAT", "5 ans", "12/06/2030", "0", "-", "6,35%", ref_code="OT5A"),
]
SN = [
    FxTranche("SN0000009911", "OAT", "3 ans", "04/07/2028", "12 000", "7,92%", "6,30%"),
    FxTranche("SN0000009929", "OAT", "5 ans", "04/07/2030", "8 500,50", "8,10%", "6,45%", ref_code="OT5A"),
]
TG = [FxTranche("TG0000009918", "OAT", "3 ans", "05/08/2028", "17 793,22", "8,13%", "5,70%")]
# 'EC' auction: the page also lists the security bought back (no retained amount); the PDF has an
# issuance page and a buyback page.
NE = [FxTranche("NE0000009916", "OAT", "3 ans", "11/11/2028", "9 000", "8,00%", "6,30%")]
NE_BUYBACK = [("NE0000009924", "OAT", "20/11/2025")]
# Truncated issuer label + global total printed rounded to the integer (38 728,67 -> "38 729").
GW = [FxTranche("GW0000009914", "OAT", "3 ans", "07/10/2028", "34 658,17", "7,90%", "6,25%"),
      FxTranche("GW0000009922", "OAT", "5 ans", "07/10/2030", "4 070,50", "8,10%", "6,45%", ref_code="OT5A")]


def _pages() -> dict[str, bytes]:
    pages = {
        URL_ML: emission_page_html(operation="11/06/2025", value="12/06/2025", compte_rendu_url=CR.format("ml"),
                                   results=[("BAT", "10/06/2026", "20 010,0000", "9,3523"),
                                            ("OAT", "12/06/2028", "10 345,0000", "9,2156"),
                                            ("OAT", "12/06/2030", "--", "--")]),
        # The page lists the two OAT in the reverse order of the compte rendu.
        URL_SN: emission_page_html(operation="03/07/2025", value="04/07/2025", compte_rendu_url=CR.format("sn"),
                                   results=[("OAT", "04/07/2030", "8 500,5000", "8,1000"),
                                            ("OAT", "04/07/2028", "12 000,0000", "7,9200")]),
        # Contradiction: the page prints another retained amount than the compte rendu.
        URL_TG: emission_page_html(operation="04/08/2025", value="05/08/2025", compte_rendu_url=CR.format("tg"),
                                   results=[("OAT", "05/08/2028", "5 000,0000", "8,1300")]),
        URL_BF: emission_page_html(operation="05/09/2025", value="06/09/2025", compte_rendu_url=CR.format("bf"),
                                   results=[("BAT", "04/09/2026", "18 978,0000", "7,5500")]),
        URL_GW: emission_page_html(operation="06/10/2025", value="07/10/2025", compte_rendu_url=CR.format("gw"),
                                   results=[("OAT", "07/10/2028", "34 658,1700", "7,9000"),
                                            ("OAT", "07/10/2030", "4 070,5000", "8,1000")]),
        URL_EC: emission_page_html(operation="10/11/2025", value="11/11/2025", compte_rendu_url=CR.format("ec"),
                                   results=[("OAT", "11/11/2028", "9 000,0000", "8,0000"),
                                            ("OAT", "20/11/2025", "--", "--")]),
        URL_OLD: emission_page_html(operation="10/12/2024", value="11/12/2024", compte_rendu_url=CR.format("old"),
                                    results=[("OAT", "11/12/2027", "9 000,0000", "8,0000")]),
    }
    out = {u: h.encode() for u, h in pages.items()}
    out[INDEX_URL] = "".join(f"<a href='{u}'>x</a>" for u in pages).encode()
    out[CR.format("ml")] = compte_rendu_pdf("ETAT DU MALI", "11/06/2025", "12/06/2025", ML)
    out[CR.format("sn")] = compte_rendu_pdf("ETAT DU SÉNÉGAL", "03/07/2025", "04/07/2025", SN)
    out[CR.format("tg")] = compte_rendu_pdf("ETAT DU TOGO", "04/08/2025", "05/08/2025", TG)
    out[CR.format("ec")] = pdf_from_pages([
        compte_rendu_lines("ETAT DU NIGER", "10/11/2025", "11/11/2025", NE),
        buyback_lines("ETAT DU NIGER", "10/11/2025", "11/11/2025", NE_BUYBACK),
    ])
    out[CR.format("gw")] = compte_rendu_pdf("ETAT DE GUINÉE-BISSA", "06/10/2025", "07/10/2025", GW, total="38 729")
    return out


class StubFetcher:
    def __init__(self) -> None:
        self.content = _pages()
        self.calls: list[str] = []

    async def get(self, url: str) -> FetchResult:
        self.calls.append(url)
        body = self.content.get(url)
        if body is None:
            return FetchResult(url=url, final_url=url, status_code=404, content=b"", error="HTTP 404")
        return FetchResult(url=url, final_url=url, status_code=200, content=body)


# =========================================================================== migration 0014
def test_migration_0014_upgrade_downgrade_and_legacy_deals() -> None:
    params, name = _fresh_db("phase18_migration_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("0013_institutional_discovery")
        # A Phase 13 deal written before the migration.
        asyncio.run(_exec(dsn, """
            INSERT INTO deals (id, created_at, updated_at, title, deal_type, amount, currency, unit, status)
            VALUES ('legacy-deal', now(), now(), 'Prêt syndiqué FIXTURE', 'syndicated_loan', 100, 'XOF',
                    'millions', 'needs_review')"""))
        _alembic("0014_public_debt_instruments")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0014_public_debt_instruments"
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns WHERE table_name='deals' "
                                          "AND column_name IN ('instrument_type','isin','auction_reference',"
                                          "'auction_date','value_date','maturity_date','yield_rate',"
                                          "'ingestion_key')")) == 8
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns "
                                          "WHERE table_name='deal_participants' AND column_name='entity_id'")) == 1
        # The legacy deal is unchanged and readable with NULL instrument fields.
        assert asyncio.run(_fetchval(dsn, "SELECT title || '|' || amount::text || '|' || coalesce(isin, 'NULL') "
                                          "FROM deals WHERE id='legacy-deal'")) == "Prêt syndiqué FIXTURE|100.000000|NULL"
        _alembic("0013_institutional_discovery", "downgrade")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns "
                                          "WHERE table_name='deals' AND column_name='isin'")) == 0
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM deals WHERE id='legacy-deal'")) == 1
        _alembic("0014_public_debt_instruments")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0014_public_debt_instruments"
    finally:
        _drop(params, name)


async def _exec(dsn: str, sql: str) -> None:
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


# =========================================================================== shared DB
@pytest.fixture(scope="module")
def pg(tmp_path_factory):
    params, name = _fresh_db("phase18_umoa_titres_pytest")
    _alembic("head")
    url = _dsn(params, name).replace("postgresql://", "postgresql+asyncpg://")
    storage = tmp_path_factory.mktemp("phase18_store")
    asyncio.run(_seed_financial_row(url))
    yield {"url": url, "storage": storage, "dsn": _dsn(params, name)}
    _drop(params, name)


async def _seed_financial_row(url: str) -> None:
    from app.models.country import Country

    engine, maker = await _session(url)
    async with maker() as db:
        ci = (await db.execute(select(Country).where(Country.code == "CI"))).scalar_one()
        source = (await db.execute(select(Source))).scalars().first()
        bank = Institution(name_official="Banque FIXTURE", institution_type="bank", country_id=ci.id, status="active")
        doc = Document(title="FIXTURE", document_type="annual_report", source_id=source.id,
                       download_status="downloaded", extraction_status="extracted")
        db.add_all([bank, doc])
        await db.flush()
        db.add(FinancialData(institution_id=bank.id, source_id=source.id, document_id=doc.id,
                             metric_code="total_actifs", scope="individual", period_type="annual", period_year=2024,
                             value_original="5000", value_normalized=Decimal("5000"), currency_normalized="XOF",
                             extraction_method="pdf_table", status="extracted", page_number=1))
        await db.commit()
    await engine.dispose()


CHECKSUM = ("SELECT count(*)::text || md5(string_agg(id || value_original || coalesce(value_normalized::text, '') "
            "|| status, ',' ORDER BY id)) FROM financial_data")


async def _ingest(pg, fetcher=None):
    engine, maker = await _session(pg["url"])
    fetcher = fetcher or StubFetcher()
    async with maker() as db:
        report = await UmoaTitresAuctionIngestor(
            fetcher, DocumentRegistrar(StorageManager(pg["storage"]))  # type: ignore[arg-type]
        ).run(db, since=date(2025, 1, 1))
    await engine.dispose()
    return report, fetcher


async def _ranking(pg):
    engine, maker = await _session(pg["url"])
    async with maker() as db:
        r = await RankingService().rank(db, get_indicator("total_actifs"), period_year=2024)
    await engine.dispose()
    return r.model_dump(exclude={"items": {"__all__": {"provenance"}}})


@pytest.fixture(scope="module")
def ingested(pg):
    before_checksum = asyncio.run(_fetchval(pg["dsn"], CHECKSUM))
    before_ranking = asyncio.run(_ranking(pg))
    report, fetcher = asyncio.run(_ingest(pg))
    return {"report": report, "fetcher": fetcher, "before_checksum": before_checksum,
            "before_ranking": before_ranking}


async def _deals(pg):
    engine, maker = await _session(pg["url"])
    async with maker() as db:
        deals = (await db.execute(select(Deal).where(Deal.isin.is_not(None)).order_by(Deal.isin))).scalars().all()
        out = {}
        for d in deals:
            parts = (await db.execute(select(DealParticipant).where(DealParticipant.deal_id == d.id))).scalars().all()
            sources = (await db.execute(select(DealSource).where(DealSource.deal_id == d.id))).scalars().all()
            fields = (await db.execute(
                select(DealFieldSource.field_name, DealFieldSource.deal_source_id)
                .where(DealFieldSource.deal_id == d.id))).all()
            events = (await db.execute(
                select(FinancialDataReviewEvent).where(FinancialDataReviewEvent.deal_id == d.id))).scalars().all()
            docs = {s.id: await db.get(Document, s.document_id) for s in sources}
            out[d.isin] = {"deal": d, "participants": parts, "sources": sources, "fields": fields,
                           "events": events, "docs": docs}
    await engine.dispose()
    return out


def test_report_counts(ingested):
    r = ingested["report"]
    assert r.urls_discovered == 7
    assert r.urls_in_scope == 6  # the 2024 auction is out of scope and never fetched
    assert URL_OLD not in ingested["fetcher"].calls
    assert r.pages_without_oat == 1 and CR.format("bf") not in ingested["fetcher"].calls  # BAT only
    assert r.compte_rendus_parsed == 5
    assert r.deals_created == 6  # ML OAT 3 ans + SN OAT 3 ans + SN OAT 5 ans + GW 2 OAT + NE (EC) 1 OAT
    assert dict(r.tranches_skipped) == {"not_oat": 1, "no_retained_amount": 1}
    assert [issue for _, issue in r.auctions_refused] == ["retained_amount_differs_TG0000009918"]
    assert dict(r.deals_by_country) == {"GW": 2, "ML": 1, "NE": 1, "SN": 2}
    assert dict(r.validation_flags) == {"issuer_label_truncated": 2, "global_total_rounded": 2,
                                        "page_lists_buyback_securities": 1}
    assert (r.auctions_with_buyback_rows, r.buyback_rows_ignored) == (1, 1)


def test_oat_deal_fields_issuer_and_status(pg, ingested):
    deals = asyncio.run(_deals(pg))
    assert sorted(deals) == ["GW0000009914", "GW0000009922", "ML0000009925", "NE0000009916", "SN0000009911",
                             "SN0000009929"]  # no deal for the 0 tranche, none for the bought-back security
    d = deals["ML0000009925"]["deal"]
    assert (d.deal_type, d.instrument_type, d.status) == ("sovereign_bond", "OAT", "needs_review")
    assert (d.amount, d.currency, d.unit, d.amount_original) == (
        Decimal("10345"), "XOF", "millions", "10 345 millions de F CFA")
    assert (d.interest_rate, d.interest_rate_type, d.yield_rate) == (Decimal("6.15"), "fixed", Decimal("9.22"))
    assert (d.auction_reference, d.auction_date, d.value_date, d.maturity_date, d.maturity_months) == (
        "ADJ-ML0000009925-OT3A-2025", date(2025, 6, 11), date(2025, 6, 12), date(2028, 6, 12), 36)
    assert d.verified_at is None and d.verified_by is None
    sn = deals["SN0000009929"]["deal"]
    assert (sn.amount, sn.yield_rate) == (Decimal("8500.50"), Decimal("8.10"))  # paired on maturity, not order
    assert all(v["deal"].status == "needs_review" for v in deals.values())


def test_issuer_is_the_existing_sovereign_entity(pg, ingested):
    deals = asyncio.run(_deals(pg))

    async def sovereign(code):
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            from app.models.country import Country

            row = (await db.execute(select(Entity.id).join(Country, Country.id == Entity.country_id).where(
                Entity.entity_type == "sovereign_state", Country.code == code))).scalar_one()
            count = (await db.execute(select(func.count()).select_from(Entity).where(
                Entity.entity_type == "sovereign_state"))).scalar_one()
        await engine.dispose()
        return row, count

    ml_entity, sovereign_count = asyncio.run(sovereign("ML"))
    assert sovereign_count == 8  # no entity created
    parts = deals["ML0000009925"]["participants"]
    assert [(p.role, p.participant_name, p.entity_id, p.institution_id) for p in parts] == [
        ("issuer", "ETAT DU MALI", ml_entity, None)]


def test_provenance_is_complete(pg, ingested):
    v = asyncio.run(_deals(pg))["ML0000009925"]
    by_ref = {s.excerpt.split(" ")[0]: s for s in v["sources"]}
    pdf, page = by_ref["pdf_text"], by_ref["web_html"]
    assert pdf.page_number == 1 and page.page_number == 1
    pdf_doc, page_doc = v["docs"][pdf.id], v["docs"][page.id]
    assert pdf_doc.url == CR.format("ml") and pdf_doc.file_format == "pdf" and pdf_doc.document_scope == "market"
    assert page_doc.url == URL_ML and page_doc.file_format == "html"
    assert "ADJ-ML0000009925-OT3A-2025" in pdf.excerpt and "ISIN ML0000009925" in pdf.excerpt
    attested = {}
    for f, sid in v["fields"]:
        attested.setdefault(f, set()).add(sid)
    for f in ("isin", "amount", "currency", "yield_rate", "value_date", "maturity_date", "auction_reference",
              "auction_date", "interest_rate", "instrument_type", "country_code"):
        assert pdf.id in attested[f], f
    for f in ("amount", "yield_rate", "value_date", "maturity_date"):
        assert page.id in attested[f], f  # cross-checked on the emission page
    assert [(e.action, e.previous_status, e.new_status) for e in v["events"]] == [
        ("import", "none", "needs_review")]


def test_missing_values_stay_null(pg, ingested):
    # The Mali OAT 5 ans has no retained amount: no deal at all (never a 0 amount).
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE isin='ML0000009933'")) == 0
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE amount = 0 OR yield_rate = 0")) == 0
    # The contradicted Togo auction created nothing.
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE isin LIKE 'TG%'")) == 0


def test_rerun_is_idempotent(pg, ingested):
    docs_before = asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM documents"))
    report, _ = asyncio.run(_ingest(pg))
    assert report.deals_created == 0 and report.already_imported == 6
    assert report.count("already_imported") == 4 and report.count("produced") == 0
    assert report.funnel()["unclassified"] == 0
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE isin IS NOT NULL")) == 6
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM documents")) == docs_before


def test_same_instrument_from_another_import_is_a_duplicate_candidate(pg, ingested):
    deals = asyncio.run(_deals(pg))
    original = deals["ML0000009925"]
    pdf_source = next(s for s in original["sources"] if s.excerpt.startswith("pdf_text"))

    async def run():
        engine, maker = await _session(pg["url"])
        async with maker() as db:
            record = {
                "title": "OAT 3 ans Mali (structured import FIXTURE)", "deal_type": "sovereign_bond",
                "country_code": "ML", "amount": "10345", "currency": "XOF", "unit": "millions",
                "instrument_type": "OAT", "isin": "ML0000009925", "value_date": "2025-06-12",
                "ingestion_key": "fixture:other-import:ML0000009925",
                "participants": [{"role": "issuer", "name": "Etat du Mali",
                                  "entity_id": original["participants"][0].entity_id, "source_ref": "s"}],
                "sources": [{"ref": "s", "document_id": pdf_source.document_id, "source_id": pdf_source.source_id,
                             "page": 1, "fields": ["title", "deal_type", "country_code", "amount", "currency",
                                                   "unit", "instrument_type", "isin", "value_date"]}],
            }
            rep = await import_deals(db, validate_records([json.loads(json.dumps(record))]), actor="analyst",
                                     origin="fixture")
            cands = (await db.execute(select(DealDuplicateCandidate))).scalars().all()
            merged = (await db.execute(select(func.count()).select_from(Deal).where(
                Deal.merged_into_deal_id.is_not(None)))).scalar_one()
        await engine.dispose()
        return rep, cands, merged

    rep, cands, merged = asyncio.run(run())
    assert len(rep.duplicate_candidates) == 1
    (cand,) = (c for c in cands if original["deal"].id in (c.deal_a_id, c.deal_b_id))
    assert cand.state == "duplicate_candidate" and "instrument" in cand.matched_criteria
    assert merged == 0  # never merged automatically


def test_no_impact_on_financial_data_and_rankings(pg, ingested):
    assert asyncio.run(_fetchval(pg["dsn"], CHECKSUM)) == ingested["before_checksum"]
    assert asyncio.run(_ranking(pg)) == ingested["before_ranking"]


def _alembic_on(pg, revision: str, direction: str) -> None:
    """Alembic bound explicitly to the test database (never the one of the environment)."""
    from app.core.config import get_settings

    os.environ["DATABASE_URL"] = pg["url"]
    get_settings.cache_clear()
    _alembic(revision, direction)


def test_downgrade_refused_while_instrument_data_exists(pg, ingested):
    flagged = asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE validation_flags IS NOT NULL"))
    assert flagged > 0
    # 0015 first: refused while deals carry validation flags (the whole downgrade is rolled back).
    with pytest.raises(RuntimeError, match="downgrade of 0015 refused"):
        _alembic_on(pg, "0014_public_debt_instruments", "downgrade")
    with pytest.raises(RuntimeError, match="downgrade of 0015 refused"):
        _alembic_on(pg, "0013_institutional_discovery", "downgrade")
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT version_num FROM alembic_version")) == \
        "0015_deal_validation_flags"
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE validation_flags IS NOT NULL")) == \
        flagged
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE isin IS NOT NULL")) == 7


def test_funnel_reconciles_exactly(ingested):
    r = ingested["report"]
    f = r.funnel()
    assert f["unclassified"] == 0 and len(r.outcomes) == f["index_urls"] == 7
    assert sum(f["out_of_scope"].values()) + f["in_scope"] == f["index_urls"]
    assert sum(f["in_scope_breakdown"].values()) == f["in_scope"]
    assert sum(f["oat_pages_breakdown"].values()) == f["in_scope_breakdown"]["oat_pages"]
    assert sum(f["compte_rendu_read_breakdown"].values()) == f["oat_pages_breakdown"]["compte_rendu_read"]
    assert f["compte_rendu_read_breakdown"]["refused"] == sum(f["refused_by_reason"].values())
    assert f["out_of_scope"]["out_of_scope_slug_date"] == 1 and f["in_scope_breakdown"]["bat_only"] == 1
    assert f["compte_rendu_read_breakdown"]["produced"] == 4
    assert f["refused_by_reason"] == {"contradiction_page_pdf": 1}
    (refusal,) = r.refusals
    assert (refusal.country, refusal.auction_date, refusal.references) == (
        "TG", date(2025, 8, 4), ["ADJ-TG0000009918-OT3A-2025"])
    assert refusal.conflict == {"field": "amount", "isin": "TG0000009918", "html": "5000.0000", "pdf": "17793.22"}


def test_validation_flags_and_issuer_rule_are_stored(pg, ingested):
    deals = asyncio.run(_deals(pg))
    v = deals["GW0000009914"]
    d = v["deal"]
    assert sorted(f["code"] for f in d.validation_flags) == ["global_total_rounded", "issuer_label_truncated"]
    assert d.amount == Decimal("34658.17")  # tranche amount kept as printed
    assert d.status == "needs_review"
    (part,) = v["participants"]
    assert part.participant_name == "ETAT DE GUINÉE-BISSA" and part.entity_id is not None
    pdf = next(s for s in v["sources"] if s.excerpt.startswith("pdf_text"))
    assert "truncated_label_confirmed_by_isin_prefix_GW" in pdf.excerpt
    assert deals["ML0000009925"]["deal"].validation_flags is None  # no rule applied, no flag
    # SQL NULL (never a JSON null) when no rule applied
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE validation_flags IS NOT NULL")) == 3


def test_migration_0015_roundtrip() -> None:
    params, name = _fresh_db("phase18_migration_0015_pytest")
    dsn = _dsn(params, name)
    try:
        _alembic("head")
        assert asyncio.run(_fetchval(dsn, "SELECT version_num FROM alembic_version")) == "0015_deal_validation_flags"
        _alembic("0014_public_debt_instruments", "downgrade")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns "
                                          "WHERE table_name='deals' AND column_name='validation_flags'")) == 0
        _alembic("head")
        assert asyncio.run(_fetchval(dsn, "SELECT count(*) FROM information_schema.columns "
                                          "WHERE table_name='deals' AND column_name='validation_flags'")) == 1
    finally:
        _drop(params, name)



def test_ec_auction_ignores_the_bought_back_security(pg, ingested):
    deals = asyncio.run(_deals(pg))
    d = deals["NE0000009916"]["deal"]
    assert (d.amount, d.yield_rate, d.status) == (Decimal("9000"), Decimal("8.00"), "needs_review")
    (flag,) = d.validation_flags
    assert flag["code"] == "page_lists_buyback_securities"
    assert "p.2 (RA-NE0000009924-14-2025)" in flag["detail"]
    assert asyncio.run(_fetchval(pg["dsn"], "SELECT count(*) FROM deals WHERE isin='NE0000009924' "
                                             "OR maturity_date='2025-11-20'")) == 0


def test_no_transaction_is_open_during_http_requests(pg, ingested):
    """Lot 0: the runner's session never stays 'idle in transaction' while it downloads."""

    class WatchingFetcher(StubFetcher):
        session = None
        open_during_get: list[str] = []

        async def get(self, url):
            if self.session is not None and self.session.in_transaction():
                self.open_during_get.append(url)
            return await super().get(url)

    async def run():
        engine, maker = await _session(pg["url"])
        fetcher = WatchingFetcher()
        async with maker() as db:
            fetcher.session = db
            report = await UmoaTitresAuctionIngestor(
                fetcher, DocumentRegistrar(StorageManager(pg["storage"]))  # type: ignore[arg-type]
            ).run(db, since=date(2025, 1, 1))
            still_open = db.in_transaction()
        await engine.dispose()
        return report, fetcher, still_open

    report, fetcher, still_open = asyncio.run(run())
    assert report.deals_created == 0  # idempotent re-run
    assert len(fetcher.calls) > 5
    assert fetcher.open_during_get == [] and not still_open
