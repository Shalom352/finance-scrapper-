"""
Automated deal collection — one entry point for the API, the scheduler and the CLI.

    collect(db, ["boad", "ifc"], since=..., until=...) -> DealCollectionResult

Each source runs under its own PostgreSQL advisory lock (UMOA-Titres shares the lock of
``app.deals.umoa_titres_run``: the two never run together). A failing source never stops the
others; its error is returned. Every deal is written by the Phase 13 importer: needs_review,
field-level provenance, audit event, duplicate candidates (never a merge).
After each source, a coherence check verifies that every created deal is attested by at least one
document of that source.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Awaitable, Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.deal import DealSource
from app.models.document import Document
from app.models.source import Source

logger = get_logger(__name__)

# Bank-statement pipeline sources (discover -> download -> financial extraction), unchanged.
FINANCIAL_SOURCES = ("bceao", "cb-umoa", "brvm", "umoa-titres")
# Deal collectors, by key.
DEAL_SOURCES = ("umoa-titres", "brvm", "amf-umoa", "ifc", "boad", "proparco", "bidc", "press")
ALL_SOURCES = tuple(dict.fromkeys(FINANCIAL_SOURCES + DEAL_SOURCES))
SOURCE_SHORT_NAMES = {
    "umoa-titres": "UMOA-Titres", "brvm": "BRVM", "amf-umoa": "AMF-UMOA", "ifc": "IFC", "boad": "BOAD",
    "proparco": "Proparco", "bidc": "BIDC", "press": "Presse financière",
}


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class DealCollectionResult:
    summaries: dict[str, dict[str, Any]] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def deals_created(self) -> int:
        return sum(int(s.get("deals_created") or 0) for s in self.summaries.values())

    @property
    def deals_enriched(self) -> int:
        return sum(int(s.get("deals_enriched") or 0) for s in self.summaries.values())

    @property
    def fields_enriched(self) -> int:
        return sum(int(s.get("fields_enriched") or 0) for s in self.summaries.values())

    def as_json(self) -> dict[str, Any]:
        return {**self.summaries, "_errors": self.errors} if self.errors else dict(self.summaries)


def configured_sources() -> list[str]:
    raw = get_settings().deal_collection_sources
    return [s.strip() for s in raw.split(",") if s.strip() in DEAL_SOURCES]


def default_since(today: date | None = None) -> date:
    return (today or utcnow().date()) - timedelta(days=get_settings().deal_collection_lookback_days)


def build_collector(key: str, fetcher, registrar=None):
    """The collector of one source key (imports kept local: the scraping stack is heavy)."""
    if key == "umoa-titres":
        return UmoaTitresCollector(fetcher, registrar)
    if key == "brvm":
        from scraping.deals.collect.brvm import BrvmBondListingCollector

        return BrvmBondListingCollector(fetcher, registrar)
    if key == "amf-umoa":
        from scraping.deals.collect.amf_umoa import AmfUmoaCollector

        return AmfUmoaCollector(fetcher, registrar)
    if key == "ifc":
        from scraping.deals.collect.ifc import IfcCollector

        return IfcCollector(fetcher, registrar)
    if key == "boad":
        from scraping.deals.collect.boad import BoadCollector

        return BoadCollector(fetcher, registrar)
    if key == "proparco":
        from scraping.deals.collect.proparco import ProparcoCollector

        return ProparcoCollector(fetcher, registrar)
    if key == "bidc":
        from scraping.deals.collect.bidc import BidcCollector

        return BidcCollector(fetcher, registrar)
    if key == "press":
        from scraping.deals.collect.press import PressCollector

        return PressCollector(fetcher, registrar)
    raise ValueError(f"unknown deal source '{key}' (expected one of {', '.join(DEAL_SOURCES)})")


class UmoaTitresCollector:
    """The auction-specific UMOA-Titres ingestor behind the common collector interface."""

    source_key = "umoa-titres"
    source_short_name = "UMOA-Titres"

    def __init__(self, fetcher, registrar=None) -> None:
        from scraping.deals.umoa_titres_ingest import UmoaTitresAuctionIngestor

        self.ingestor = UmoaTitresAuctionIngestor(fetcher, registrar)

    async def run(self, db: AsyncSession, *, since: date | None = None, until: date | None = None,
                  limit: int | None = None, recheck: bool = False, on_progress=None):
        # Same interface as the other collectors. The ingestor keeps no checkpoint: every auction of the
        # window is read anyway, so ``recheck`` has nothing more to do.
        report = await self.ingestor.run(db, since=since or default_since(), until=until, on_progress=on_progress)
        return _UmoaTitresReport(report)


class _UmoaTitresReport:
    def __init__(self, report) -> None:
        self.report = report
        self.deal_ids = report.deal_ids
        self.discovery_warnings: list[str] = []  # the ingestor reports its failures per auction

    def summary(self) -> dict[str, Any]:
        return {"source": "umoa-titres", **self.report.summary()}


async def coherence(db: AsyncSession, source_short_name: str, deal_ids: list[str]) -> dict[str, Any]:
    """Deals of the run NOT attested by any document of the collecting source (expected: none)."""
    if not deal_ids:
        return {"deals_checked": 0, "deals_without_source_document": []}
    rows = (await db.execute(
        select(DealSource.deal_id)
        .join(Document, Document.id == DealSource.document_id)
        .join(Source, Source.id == Document.source_id)
        .where(DealSource.deal_id.in_(deal_ids), Source.short_name == source_short_name,
               Document.deleted_at.is_(None))
    )).scalars().all()
    attested = set(rows)
    await db.commit()
    return {"deals_checked": len(deal_ids), "deals_without_source_document": sorted(set(deal_ids) - attested)}


async def collect(
    db: AsyncSession,
    sources: list[str] | None = None,
    *,
    since: date | None = None,
    until: date | None = None,
    limit: int | None = None,
    fetcher=None,
    lock_engine=None,
    registrar=None,
    recheck: bool = False,
    progress: Callable[[str, bool, dict[str, Any] | None], Awaitable[None]] | None = None,
) -> DealCollectionResult:
    """Run the deal collectors of ``sources`` (default: the configured list) one after the other.

    ``fetcher`` (tests) replaces the network fetcher (still wrapped by the polite one); ``lock_engine``
    (default: the app engine) holds the advisory locks, ``False`` runs without locks (tests on a
    private DB); ``registrar`` (tests) stores the documents elsewhere than the configured storage;
    ``recheck`` reads every candidate again whatever its checkpoint (after a parser fix).
    """
    from app.deals.run_lock import UMOA_TITRES_LOCK, single_run_lock
    from scraping.deals.collect.base import PoliteFetcher
    from scraping.deals.collect.press import HOST_DELAYS as PRESS_DELAYS
    from scraping.universe.http import OfficialFetcher

    settings = get_settings()
    keys = [k for k in (sources or configured_sources())]
    unknown = [k for k in keys if k not in DEAL_SOURCES]
    if unknown:
        raise ValueError(f"unknown deal source(s): {', '.join(unknown)}")
    since = since or default_since()
    if limit is None and settings.deal_collection_max_pages > 0:
        limit = settings.deal_collection_max_pages
    if lock_engine is None:
        from app.db.engine import engine as lock_engine
    result = DealCollectionResult()

    async def run_one(key: str, polite) -> None:
        collector = build_collector(key, polite, registrar)

        async def report_progress(raw_report) -> None:
            if progress:
                await progress(key, False, raw_report.summary())

        report = await collector.run(db, since=since, until=until, limit=limit, recheck=recheck,
                                    on_progress=report_progress)
        summary = report.summary()
        summary["coherence"] = await coherence(db, SOURCE_SHORT_NAMES[key], list(report.deal_ids))
        result.summaries[key] = summary
        raw_report = getattr(report, "report", report)
        outcomes = getattr(raw_report, "outcomes", {})
        failure_names = {
            "error", "fetch_failed", "restricted", "refused", "import_refused",
            "page_fetch_failed", "compte_rendu_fetch_failed", "layout_error",
        }
        for outcome in sorted(failure_names):
            affected = [(url, detail) for url, (state, detail) in outcomes.items() if state == outcome]
            if affected:
                examples = "; ".join(f"{url}: {detail or outcome}" for url, detail in affected[:2])
                result.errors.append({"source": key, "phase": "deals_pages",
                                      "error": f"{len(affected)} page(s) ended as {outcome}. {examples}"[:1000],
                                      "timestamp": utcnow().isoformat()})
        # Deferred candidates are normal checkpointed backlog, not failed pages. They remain visible
        # in the per-source summary and are processed on later runs; counting them as errors made a
        # healthy incremental collection look like a failed source in the run history.
        for warning in report.discovery_warnings:  # partial: the run ends as partial_failure, not completed
            result.errors.append({"source": key, "phase": "deals_discovery", "error": warning[:1000],
                                  "timestamp": utcnow().isoformat()})

    async def guarded(key: str, polite) -> None:
        started = utcnow()
        try:
            if progress:
                await progress(key, False, None)
            if lock_engine is False:
                await run_one(key, polite)
            else:
                lock_name = UMOA_TITRES_LOCK if key == "umoa-titres" else f"deal_collection:{key}"
                async with single_run_lock(lock_engine, lock_name) as lock:
                    if not lock.acquired:
                        result.summaries[key] = {"source": key, "skipped": "another run holds the lock",
                                                 "lock_holders": lock.holders}
                        # Not collected: reported, never counted as a successful source.
                        result.errors.append({"source": key, "phase": "deals_lock",
                                              "error": "skipped: another run holds the lock",
                                              "timestamp": utcnow().isoformat()})
                        return
                    await run_one(key, polite)
        except Exception as err:  # one source never stops the others; reported in the run errors
            await db.rollback()
            logger.error("deal_collection_source_failed", source=key, error=str(err))
            message = f"{type(err).__name__}: {err}"[:1000]
            result.summaries[key] = {"source": key, "error": message}
            result.errors.append({"source": key, "phase": "deals", "error": message,
                                  "timestamp": utcnow().isoformat()})
        finally:
            if progress:
                await progress(key, True, result.summaries.get(key))
            logger.info("deal_collection_source_finished", source=key,
                        seconds=round((utcnow() - started).total_seconds(), 1))

    if fetcher is not None:
        polite = PoliteFetcher(fetcher, min_delay=0.0)  # tests: no waiting
        for key in keys:
            await guarded(key, polite)
        return result

    # UMOA-Titres keeps its own fetcher settings; the polite wrapper adds robots.txt and Crawl-delay.
    async with OfficialFetcher(delay_seconds=0.0) as official:
        polite = PoliteFetcher(official, min_delay=settings.deal_collection_delay_seconds, host_delays=PRESS_DELAYS)
        for key in keys:
            await guarded(key, polite)
    return result
