"""
UMOA-Titres auction ingestion: emission pages -> compte rendu PDF -> sovereign_bond deals.

Network and database orchestration around the pure parsers of ``umoa_titres_auctions``.
Deals are written ONLY through the Phase 13 importer (``import_deals``): needs_review,
field-level provenance, audit event, duplicate candidates. One import per auction (all its
OAT tranches or none). Re-running is idempotent: tranches whose ingestion_key already exists
are counted as already imported and nothing is written for them (no document either).

Every URL of the index receives exactly ONE outcome, so the funnel always reconciles:
index -> out of scope / in scope -> page failed / BAT only / OAT pages -> ... -> produced.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.country import Country
from app.models.deal import Deal
from app.models.entity import Entity
from app.models.source import Source
from scraping.deals.importer import DealImportError, import_deals, validate_records
from scraping.deals.umoa_titres_auctions import (
    INDEX_URL,
    LayoutError,
    build_auction_deals,
    emission_urls,
    parse_compte_rendu_document,
    parse_emission_page,
    slug_date,
)
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.http import OfficialFetcher

logger = get_logger(__name__)

ACTOR = "umoa_titres_auction_ingestor"
SOURCE_NAME = "UMOA-Titres"

# Outcomes, by funnel stage (each URL gets exactly one).
OUT_OF_SCOPE = ("out_of_scope_slug_date", "out_of_scope_page_date")
IN_SCOPE_NOT_OAT = ("page_fetch_failed", "bat_only")
OAT_BEFORE_PDF = ("results_not_published", "compte_rendu_missing", "compte_rendu_fetch_failed")
PDF_NOT_READ = ("layout_error",)
PDF_READ = ("buyback_only", "refused", "no_oat_issued", "already_imported", "produced", "import_refused", "error")

CONTRADICTION_PREFIXES = ("retained_amount_differs", "yield_differs", "maturity_date_differs", "value_date_differs",
                          "auction_date_differs")


def refusal_group(issue: str) -> str:
    if issue.startswith(CONTRADICTION_PREFIXES):
        return "contradiction_page_pdf"
    if issue == "page_and_compte_rendu_list_different_securities":
        return "not_pairable"
    if issue.startswith("issuer_not_recognised"):
        return "issuer_not_recognised"
    return issue


@dataclass
class Refusal:
    url: str
    country: str | None
    auction_date: date | None
    references: list[str]
    issue: str
    conflict: dict | None


@dataclass
class IngestionReport:
    since: date
    until: date | None
    urls_discovered: int = 0
    outcomes: dict[str, tuple[str, str | None]] = field(default_factory=dict)  # url -> (outcome, detail)
    deals_created: int = 0
    deal_ids: list[str] = field(default_factory=list)
    already_imported: int = 0  # tranches whose ingestion_key already existed
    tranches_skipped: Counter = field(default_factory=Counter)
    duplicate_candidates: int = 0
    documents_registered: int = 0
    flags: list[tuple[str, str]] = field(default_factory=list)  # (compte rendu url, parser flag)
    deals_by_country: Counter = field(default_factory=Counter)
    validation_flags: Counter = field(default_factory=Counter)
    auctions_with_buyback_rows: int = 0  # paired 'EC' auctions whose page also lists bought-back securities
    buyback_rows_ignored: int = 0
    refusals: list[Refusal] = field(default_factory=list)

    def set(self, url: str, outcome: str, detail: str | None = None) -> None:
        self.outcomes[url] = (outcome, detail)

    def count(self, *outcomes: str) -> int:
        return sum(1 for o, _ in self.outcomes.values() if o in outcomes)

    def urls(self, outcome: str) -> list[str]:
        return [u for u, (o, _) in self.outcomes.items() if o == outcome]

    # Compatibility counters (derived from the outcomes).
    @property
    def urls_in_scope(self) -> int:
        return self.urls_discovered - self.count(*OUT_OF_SCOPE)

    @property
    def pages_without_oat(self) -> int:
        return self.count("bat_only")

    @property
    def compte_rendus_parsed(self) -> int:
        return self.count(*PDF_READ)

    @property
    def auctions_refused(self) -> list[tuple[str, str]]:
        return [(r.url, r.issue) for r in self.refusals]

    def funnel(self) -> dict:
        oat_pages = self.count(*OAT_BEFORE_PDF, *PDF_NOT_READ, *PDF_READ)
        refused = Counter(refusal_group(r.issue) for r in self.refusals)
        return {
            "index_urls": self.urls_discovered,
            "out_of_scope": {o: self.count(o) for o in OUT_OF_SCOPE},
            "in_scope": self.urls_in_scope,
            "in_scope_breakdown": {
                "page_fetch_failed": self.count("page_fetch_failed"),
                "bat_only": self.count("bat_only"),
                "oat_pages": oat_pages,
            },
            "oat_pages_breakdown": {
                **{o: self.count(o) for o in OAT_BEFORE_PDF},
                "layout_error": self.count("layout_error"),
                "compte_rendu_read": self.count(*PDF_READ),
            },
            "compte_rendu_read_breakdown": {o: self.count(o) for o in PDF_READ},
            "refused_by_reason": dict(sorted(refused.items())),
            "unclassified": self.urls_discovered - len(self.outcomes),
        }

    def summary(self) -> dict:
        return {
            "since": self.since.isoformat(), "until": self.until.isoformat() if self.until else None,
            "funnel": self.funnel(),
            "deals_created": self.deals_created, "already_imported_tranches": self.already_imported,
            "tranches_skipped": dict(self.tranches_skipped), "duplicate_candidates": self.duplicate_candidates,
            "documents_registered": self.documents_registered,
            "validation_flags": dict(self.validation_flags),
            "auctions_with_buyback_rows": self.auctions_with_buyback_rows,
            "buyback_rows_ignored": self.buyback_rows_ignored,
            "parser_flags": len(self.flags),
            "deals_by_country": dict(sorted(self.deals_by_country.items())),
        }


async def sovereign_entities(db: AsyncSession) -> dict[str, tuple[str, str]]:
    """Country code -> (entity id, name) of the UNIQUE active sovereign_state entity of that country."""
    rows = (
        await db.execute(
            select(Country.code, Entity.id, Entity.canonical_name)
            .join(Country, Country.id == Entity.country_id)
            .where(Entity.entity_type == "sovereign_state", Entity.entity_class == "sovereign_entity",
                   Entity.deleted_at.is_(None))
        )
    ).all()
    by_country: dict[str, list[tuple[str, str]]] = {}
    for code, eid, name in rows:
        by_country.setdefault(code, []).append((eid, name))
    return {code: items[0] for code, items in by_country.items() if len(items) == 1}  # ambiguous -> none


class UmoaTitresAuctionIngestor:
    def __init__(self, fetcher: OfficialFetcher, registrar: DocumentRegistrar | None = None,
                 actor: str = ACTOR) -> None:
        self.fetcher = fetcher
        self.registrar = registrar or DocumentRegistrar()
        self.actor = actor

    async def discover(self) -> list[str]:
        res = await self.fetcher.get(INDEX_URL)
        if not res.ok:
            raise RuntimeError(f"emission index unavailable: {res.error}")
        return emission_urls(res.text)

    async def run(self, db: AsyncSession, *, since: date, until: date | None = None,
                  urls: list[str] | None = None) -> IngestionReport:
        report = IngestionReport(since=since, until=until)
        source = (await db.execute(select(Source).where(Source.name == SOURCE_NAME))).scalar_one_or_none()
        if source is None:
            raise RuntimeError(f"source '{SOURCE_NAME}' is not registered")
        source_id = source.id  # plain value: the ORM object is re-read after any rollback
        sovereigns = await sovereign_entities(db)
        await db.commit()  # read-only so far: no transaction kept open during the HTTP requests

        candidates = urls if urls is not None else await self.discover()
        report.urls_discovered = len(candidates)
        for url in candidates:
            known = slug_date(url)
            if known is not None and (known < since or (until is not None and known > until)):
                report.set(url, "out_of_scope_slug_date", str(known))
                continue
            try:
                source = await db.get(Source, source_id)  # identity map, or one SELECT after a rollback
                if db.in_transaction():
                    await db.commit()
                await self._auction(db, url, known, source, sovereigns, report)
            except Exception as err:  # one auction never stops the run; the failure is reported
                await db.rollback()
                logger.warning("umoa_titres_auction_failed", url=url, error=str(err))
                report.set(url, "error", f"{type(err).__name__}: {str(err)[:300]}")
            finally:
                # Writes are committed (or rolled back) by the importer; what may remain is a read-only
                # transaction (ingestion_key lookup, nothing pending). Close it so that no transaction
                # stays "idle in transaction" during the HTTP requests of the next auction.
                if db.in_transaction():
                    await db.commit()
        return report

    async def _auction(self, db, url, known, source, sovereigns, report: IngestionReport) -> None:
        res = await self.fetcher.get(url)
        if not res.ok:
            report.set(url, "page_fetch_failed", res.error)
            return
        page = parse_emission_page(res.text)
        when = known or page.operation_date
        if when is None or when < report.since or (report.until is not None and when > report.until):
            report.set(url, "out_of_scope_page_date", str(when))
            return

        offered = {t for t, _ in page.maturities} | {r.instrument_type for r in page.results}
        if "OAT" not in offered:
            report.set(url, "bat_only")
            return
        if not page.results:
            report.set(url, "results_not_published")
            return
        if not page.compte_rendu_url:
            report.set(url, "compte_rendu_missing")
            return

        pdf = await self.fetcher.get(page.compte_rendu_url)
        if not pdf.ok or not pdf.is_pdf:
            report.set(url, "compte_rendu_fetch_failed", pdf.error or "not a PDF")
            return
        try:
            document = parse_compte_rendu_document(pdf.content)
        except LayoutError as err:
            report.set(url, "layout_error", f"{page.compte_rendu_url} · {err}")
            return
        reports = document.reports
        for r in reports:
            for flag in r.flags:
                report.flags.append((page.compte_rendu_url, flag))

        # First pass with placeholder ids: decides whether anything is issued, before storing anything.
        def build(pdf_id: str, page_id: str):
            return build_auction_deals(
                reports=reports, page=page, buybacks=document.buybacks, sovereign_entities=sovereigns,
                pdf_document_id=pdf_id,
                page_document_id=page_id, source_id=source.id, emission_url=url,
                compte_rendu_url=page.compte_rendu_url,
            )

        draft = build("pending", "pending")
        if draft.issue == "no_security_in_compte_rendu":
            report.set(url, "buyback_only")
            return
        if draft.issue:
            tranches = [t for r in reports for t in r.tranches]
            report.refusals.append(Refusal(
                url=url, country=tranches[0].isin[:2] if tranches else None,
                auction_date=reports[0].auction_date if reports else None,
                references=[t.auction_reference for t in tranches], issue=draft.issue, conflict=draft.conflict,
            ))
            report.set(url, "refused", draft.issue)
            return
        for s in draft.skipped:
            report.tranches_skipped[s.reason] += 1
        if draft.buyback_rows:
            report.auctions_with_buyback_rows += 1
            report.buyback_rows_ignored += draft.buyback_rows
        if not draft.records:
            report.set(url, "no_oat_issued")
            return
        keys = [r["ingestion_key"] for r in draft.records]
        existing = set((await db.execute(
            select(Deal.ingestion_key).where(Deal.ingestion_key.in_(keys), Deal.deleted_at.is_(None))
        )).scalars())
        report.already_imported += len(existing)
        if all(k in existing for k in keys):
            report.set(url, "already_imported", f"{len(keys)} tranche(s)")
            return

        auction_year = reports[0].auction_date.year if reports[0].auction_date else None
        entity_id = draft.records[0]["participants"][0]["entity_id"]
        pdf_doc = await self.registrar.register_pdf(
            db, source=source, url=page.compte_rendu_url, content=pdf.content,
            title=f"Compte rendu d'adjudication — {reports[0].issuer_label} — {reports[0].auction_date}",
            document_type="regulatory_report", period_year=auction_year, period_type=None,
            entity_id=entity_id, document_scope="market",
        )
        pdf_doc.document.file_format = "pdf"
        pdf_doc.document.text_layer_status = "machine_readable"
        page_doc = await self.registrar.register_pdf(
            db, source=source, url=url, content=res.content,
            title=f"Page d'émission UMOA-Titres — {reports[0].issuer_label} — {reports[0].auction_date}",
            document_type="web_page", period_year=auction_year, period_type=None, entity_id=entity_id,
            document_scope="market", original_filename="emission.html",
        )
        page_doc.document.file_format = "html"

        final = build(pdf_doc.document.id, page_doc.document.id)
        records = [r for r in final.records if r["ingestion_key"] not in existing]
        try:
            imported = await import_deals(
                db, validate_records(records), actor=self.actor, origin=f"UMOA-Titres auction results {url}"
            )
        except DealImportError as err:
            report.set(url, "import_refused", "; ".join(f"{i.field}:{i.code}" for i in err.issues)[:500])
            return
        report.set(url, "produced", f"{len(imported.created_ids)} deal(s)")
        report.documents_registered += int(pdf_doc.is_new) + int(page_doc.is_new)  # committed with the deals
        report.deals_created += len(imported.created_ids)
        report.deal_ids.extend(imported.created_ids)
        report.duplicate_candidates += len(imported.duplicate_candidates)
        for r in records:
            report.deals_by_country[r["country_code"]] += 1
            for f in r.get("validation_flags", []):
                report.validation_flags[f["code"]] += 1
