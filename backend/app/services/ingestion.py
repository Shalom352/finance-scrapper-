"""
UMOA Banking Intelligence — Automated Ingestion Service

Orchestrates automated and manual ingestion executions:
  1. Computes target years (current year down to current year - historical_years).
  2. Enforces concurrency protection (single running ingestion at any time).
  3. Discovers documents from registered official sources (BCEAO, CB-UMOA, BRVM, UMOA-Titres).
  4. Downloads new/modified documents idempotently (SHA-256 hash tracking).
  5. Parses PDF documents and extracts financial metrics.
  6. Applies Phase 13 scope guard (needs_review + "scope not detected").
  7. Protects reviewed, verified, and rejected observations against overwriting.
  8. Tracks granular metrics and source-level errors (supporting partial failures).
  9. Deal collection phase (migration 0020): BRVM, UMOA-Titres, AMF-UMOA, IFC, BOAD, Proparco
     (app.services.deal_collection) — every deal needs_review, duplicates flagged, never merged.

``scope`` selects the phases: "financial" (bank statements), "deals", or "all" (default). A source
key belongs to one phase or both (BRVM and UMOA-Titres feed both); a deal-only source (IFC...)
never enters the bank-statement pipeline.
"""

import asyncio
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import desc, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.ingestion_run import IngestionRun
from scraping.pipeline import ScrapingPipeline

logger = get_logger(__name__)

# Global in-process lock to prevent overlapping runs within the same instance
_INGESTION_LOCK = asyncio.Lock()


def utcnow() -> datetime:
    return datetime.now(UTC)


def get_target_years(current_year: int | None = None, historical_years: int | None = None) -> list[int]:
    """
    Calculate the list of calendar years to search:
      [current_year, current_year - 1, ..., current_year - historical_years]
    """
    settings = get_settings()
    curr = current_year or utcnow().year
    hist = historical_years if historical_years is not None else settings.ingestion_historical_years
    if hist < 0:
        hist = 0
    return [curr - i for i in range(hist + 1)]


async def list_ingestion_runs(
    db: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[IngestionRun], int]:
    """Retrieve paginated list of ingestion runs, ordered by started_at desc."""
    total = (await db.execute(select(func.count(IngestionRun.id)))).scalar_one()
    query = (
        select(IngestionRun)
        .order_by(desc(IngestionRun.started_at))
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    res = await db.execute(query)
    return list(res.scalars().all()), total


async def get_latest_ingestion_run(db: AsyncSession) -> IngestionRun | None:
    """Retrieve the most recent ingestion run."""
    query = select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(1)
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def get_ingestion_run_by_id(db: AsyncSession, run_id: str) -> IngestionRun | None:
    """Retrieve an ingestion run by ID."""
    query = select(IngestionRun).where(IngestionRun.id == run_id)
    res = await db.execute(query)
    return res.scalar_one_or_none()


async def expire_stale_runs(db: AsyncSession, max_age_hours: int | None = None) -> int:
    """Mark failed the runs still "running" after ``max_age_hours`` (interrupted process). Returns the count."""
    hours = max_age_hours if max_age_hours is not None else get_settings().ingestion_stale_run_hours
    now = utcnow()
    res = await db.execute(
        update(IngestionRun)
        .where(IngestionRun.status == "running",
               func.coalesce(IngestionRun.last_progress_at, IngestionRun.started_at) < now - timedelta(hours=hours))
        .values(status="failed", finished_at=now,
                summary_text=f"Run marked failed: still 'running' after {hours} h (process interrupted).",
                errors=[{"source": "all", "phase": "timeout",
                         "error": f"No progress was recorded before the {hours} h inactivity limit.",
                         "timestamp": now.isoformat()}])
    )
    count = res.rowcount or 0
    if count:
        await db.commit()
        logger.warning("ingestion_stale_runs_expired", count=count, max_age_hours=hours)
    return count


async def expire_stale_run(db: AsyncSession, run_id: str, max_age_hours: int | None = None) -> bool:
    """Expire one interrupted run when its live status is requested."""
    hours = max_age_hours if max_age_hours is not None else get_settings().ingestion_stale_run_hours
    now = utcnow()
    res = await db.execute(
        update(IngestionRun)
        .where(
            IngestionRun.id == run_id,
            IngestionRun.status == "running",
            func.coalesce(IngestionRun.last_progress_at, IngestionRun.started_at) < now - timedelta(hours=hours),
        )
        .values(
            status="failed",
            finished_at=now,
            summary_text=f"Run marked failed: still 'running' after {hours} h (process interrupted).",
            errors=[{"source": "all", "phase": "timeout",
                     "error": f"No progress was recorded before the {hours} h inactivity limit.",
                     "timestamp": now.isoformat()}],
        )
    )
    expired = bool(res.rowcount)
    if expired:
        await db.commit()
        logger.warning("ingestion_stale_run_expired", run_id=run_id, max_age_hours=hours)
    return expired


async def abort_run(db: AsyncSession, run_id: str, *, actor: str | None) -> IngestionRun | None:
    """Close a run recorded as "running" (manual decision from the settings page). None when unknown."""
    run = await get_ingestion_run_by_id(db, run_id)
    if run is None or run.status != "running":
        return run
    run.status = "failed"
    run.finished_at = utcnow()
    run.summary_text = f"Run marked failed by {actor or 'an operator'} (was still 'running')."
    await db.commit()
    logger.warning("ingestion_run_aborted", run_id=run_id, actor=actor)
    return run


class IngestionService:
    """Core execution engine for automated & on-demand ingestion."""

    def __init__(self, pipeline: ScrapingPipeline | None = None) -> None:
        self.pipeline = pipeline or ScrapingPipeline()

    async def execute_run(
        self,
        db: AsyncSession,
        trigger_type: str = "scheduled",
        target_years: list[int] | None = None,
        sources: list[str] | None = None,
        limit_per_source: int | None = None,
        force: bool = False,
        run_id: str | None = None,
        scope: str = "all",
        deal_since: date | None = None,
        deal_until: date | None = None,
    ) -> IngestionRun:
        """
        Execute an end-to-end ingestion run across official sources and target years.
        A run that raises is closed as "failed" (never left "running").
        """
        if scope not in ("all", "financial", "deals"):
            raise ValueError(f"unknown scope '{scope}'")
        years = target_years or get_target_years()
        years_str = ", ".join(str(y) for y in years)

        # 1. Concurrency: one run at a time in this process, and none while another is recorded running
        if _INGESTION_LOCK.locked() and not force:
            logger.warning("ingestion_skipped_concurrency_lock")
            return await self._skip(db, run_id, trigger_type, years_str,
                                    "Run skipped: another ingestion run is currently in progress.")

        async with _INGESTION_LOCK:
            # A run left "running" by an interrupted process never blocks the next ones
            await expire_stale_runs(db)
            active_query = select(IngestionRun).where(IngestionRun.status == "running")
            if run_id:
                active_query = active_query.where(IngestionRun.id != run_id)
            active_res = await db.execute(active_query.order_by(IngestionRun.started_at).limit(1))
            active_existing = active_res.scalar_one_or_none()
            if active_existing and not force:
                logger.warning("ingestion_skipped_database_running_state", active_id=active_existing.id)
                return await self._skip(db, run_id, trigger_type, years_str,
                                        f"Run skipped: active run {active_existing.id} in database.")

            # 2. Initialize or fetch IngestionRun record
            run = None
            if run_id:
                run_res = await db.execute(select(IngestionRun).where(IngestionRun.id == run_id))
                run = run_res.scalar_one_or_none()

            if run is None:
                run = IngestionRun(
                    trigger_type=trigger_type,
                    status="running",
                    started_at=utcnow(),
                    last_progress_at=utcnow(),
                    target_years=years_str,
                )
                db.add(run)
                await db.commit()

            active_run_id = run.id
            try:
                return await self._run_phases(
                    db, run, trigger_type=trigger_type, years=years, sources=sources,
                    limit_per_source=limit_per_source, scope=scope, deal_since=deal_since, deal_until=deal_until,
                )
            except asyncio.CancelledError:
                logger.warning("ingestion_run_cancelled", run_id=active_run_id)
                try:
                    await self._mark_failed(
                        db, active_run_id, RuntimeError("Ingestion interrupted by task cancellation.")
                    )
                except Exception as cleanup_error:
                    logger.error(
                        "ingestion_run_cancel_cleanup_failed",
                        run_id=active_run_id,
                        error=str(cleanup_error),
                    )
                raise
            except Exception as err:  # the run never stays "running": it is closed as failed
                logger.error("ingestion_run_crashed", run_id=active_run_id, error=str(err))
                return await self._mark_failed(db, active_run_id, err)

    async def _skip(self, db: AsyncSession, run_id: str | None, trigger_type: str, years_str: str,
                    summary: str) -> IngestionRun:
        """Record a skipped run. The run created by the API trigger is closed, never left running."""
        run = None
        if run_id:
            run = (await db.execute(select(IngestionRun).where(IngestionRun.id == run_id))).scalar_one_or_none()
        if run is None:
            run = IngestionRun(trigger_type=trigger_type, started_at=utcnow(), target_years=years_str)
            db.add(run)
        run.status = "skipped_concurrent"
        run.finished_at = utcnow()
        run.summary_text = summary
        await db.commit()
        return run

    async def _mark_failed(self, db: AsyncSession, run_id: str, err: BaseException) -> IngestionRun:
        await db.rollback()
        run = (await db.execute(select(IngestionRun).where(IngestionRun.id == run_id))).scalar_one()
        run.status = "failed"
        run.finished_at = utcnow()
        run.errors = [*(run.errors or []), {"source": "all", "phase": "run", "error": f"{type(err).__name__}: {err}",
                                           "timestamp": utcnow().isoformat()}]
        run.summary_text = f"Ingestion FAILED: {type(err).__name__}: {err}"[:2000]
        await db.commit()
        return run

    async def _run_phases(
        self,
        db: AsyncSession,
        run: IngestionRun,
        *,
        trigger_type: str,
        years: list[int],
        sources: list[str] | None,
        limit_per_source: int | None,
        scope: str,
        deal_since: date | None,
        deal_until: date | None,
    ) -> IngestionRun:
        from app.services.deal_collection import DEAL_SOURCES, FINANCIAL_SOURCES, configured_sources

        progress_run_id = run.id
        logger.info("ingestion_run_started", run_id=progress_run_id, trigger_type=trigger_type, years=years)

        # 3. Determine official sources to query, per phase
        settings = get_settings()
        sources_to_check = (
            [s for s in (sources or FINANCIAL_SOURCES) if s in FINANCIAL_SOURCES] if scope != "deals" else []
        )
        deal_sources = (
            [s for s in (sources or configured_sources()) if s in DEAL_SOURCES]
            if scope != "financial" and settings.deal_collection_enabled else []
        )
        errors: list[dict[str, Any]] = []
        total_discovered = 0
        total_new_docs = 0
        successful: set[str] = set()  # a source counts once, even when it feeds both phases
        completed_sources: set[str] = set()
        run.sources_total = len(set(sources_to_check) | set(deal_sources))
        run.sources_checked = 0
        run.current_phase = "discovery" if sources_to_check else ("deal_collection" if deal_sources else "finalizing")
        run.current_source = None
        run.current_items_done = 0
        run.current_items_total = 0
        run.last_progress_at = utcnow()
        await db.commit()

        # Count existing documents before discovery
        existing_doc_count = (await db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None)))).scalar_one()

        # 4. Phase: Discovery across sources
        for src in sources_to_check:
            try:
                run.current_phase = "discovery"
                run.current_source = src
                run.last_progress_at = utcnow()
                await db.commit()
                logger.info("ingestion_discovering_source", source=src, run_id=run.id)

                async def discovery_progress(done: int, total: int) -> None:
                    run.current_items_done = done
                    run.current_items_total = total
                    run.last_progress_at = utcnow()
                    await db.commit()

                discovered = await self.pipeline.discover_source(
                    source_name=src,
                    db=db,
                    limit=limit_per_source,
                    years=years,
                    on_progress=discovery_progress if src == "umoa-titres" else None,
                )
                total_discovered += len(discovered)
                successful.add(src)
                run.documents_found = total_discovered
                run.current_source = None
                run.current_items_done = 0
                run.current_items_total = 0
                run.last_progress_at = utcnow()
                await db.commit()
            except Exception as err:
                await db.rollback()
                await db.refresh(run)
                logger.error("ingestion_source_discovery_failed", source=src, error=str(err))
                errors.append({
                    "source": src,
                    "phase": "discovery",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

        # Calculate newly added documents in DB
        new_doc_count = (await db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None)))).scalar_one()
        total_new_docs = max(0, new_doc_count - existing_doc_count)
        run.documents_found = total_discovered
        run.documents_new = total_new_docs
        run.current_source = None
        run.current_items_done = 0
        run.current_items_total = 0
        run.last_progress_at = utcnow()

        total_downloaded = total_download_failed = total_extracted = total_needing_review = 0
        duplicate_downloads_skipped = 0
        run.documents_downloaded = run.documents_failed = run.documents_skipped = 0
        run.data_points_extracted = run.data_points_needing_review = 0
        if sources_to_check:  # a deal-only run never touches the bank-statement pipeline
            # 5. Phase: Download pending documents
            run.current_phase = "download"
            run.last_progress_at = utcnow()
            await db.commit()
            total_downloaded = 0
            total_download_failed = 0
            try:
                logger.info("ingestion_downloading_pending_documents", run_id=run.id)
                download_results = await self.pipeline.download_pending_documents(db=db, years=years)
                for _, dl_res, storage_res in download_results:
                    if dl_res.success and storage_res:
                        total_downloaded += 1
                    elif dl_res.is_duplicate:
                        duplicate_downloads_skipped += 1
                    else:
                        total_download_failed += 1
            except Exception as err:
                await db.rollback()
                await db.refresh(run)
                logger.error("ingestion_download_batch_failed", error=str(err))
                errors.append({
                    "source": "all",
                    "phase": "download",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

            run.documents_downloaded = total_downloaded
            run.documents_failed = total_download_failed
            run.documents_skipped = max(0, total_discovered - total_new_docs) + duplicate_downloads_skipped

            # 6. Phase: Parsing & Classification
            try:
                run.current_phase = "parsing"
                run.last_progress_at = utcnow()
                await db.commit()
                logger.info("ingestion_parsing_downloaded_documents", run_id=run.id)
                await self.pipeline.parse_downloaded_documents(db=db, years=years)
            except Exception as err:
                await db.rollback()
                await db.refresh(run)
                logger.error("ingestion_parsing_batch_failed", error=str(err))
                errors.append({
                    "source": "all",
                    "phase": "parsing",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

            # 7. Phase: Financial Data Extraction & Scope Guard
            total_extracted = 0
            total_needing_review = 0
            try:
                run.current_phase = "extraction"
                run.last_progress_at = utcnow()
                await db.commit()
                logger.info("ingestion_extracting_financial_data", run_id=run.id)
                extraction_results = await self.pipeline.extract_financial_data(db=db, years=years)
                for _, points in extraction_results:
                    total_extracted += len(points)
                    for pt in points:
                        if getattr(pt, "status", None) == "needs_review":
                            total_needing_review += 1
            except Exception as err:
                await db.rollback()
                await db.refresh(run)
                logger.error("ingestion_extraction_batch_failed", error=str(err))
                errors.append({
                    "source": "all",
                    "phase": "extraction",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

            run.data_points_extracted = total_extracted
            run.data_points_needing_review = total_needing_review
            completed_sources.update(sources_to_check)
            run.sources_checked = len(completed_sources)
            run.current_source = None
            run.last_progress_at = utcnow()
            await db.commit()

        # 8. Phase: Deal collection (migration 0020)
        deal_result = None
        if deal_sources:
            from app.services.deal_collection import collect

            logger.info("ingestion_collecting_deals", run_id=run.id, sources=deal_sources)
            run.current_phase = "deal_collection"
            run.current_source = None
            run.last_progress_at = utcnow()
            await db.commit()  # the collectors manage their own transactions

            # Keep progress state locally and write it by primary key. The collector commits
            # through this same AsyncSession, so ORM attributes expire between callbacks;
            # reading run.deal_summary there triggers forbidden implicit async I/O.
            deal_progress_summary: dict[str, Any] = {}

            async def update_deal_progress(source: str, completed: bool,
                                           summary: dict[str, Any] | None) -> None:
                if summary is not None:
                    deal_progress_summary[source] = summary
                if completed:
                    completed_sources.add(source)
                values: dict[str, Any] = {
                    "current_phase": "deal_collection",
                    "current_source": None if completed else source,
                    "sources_checked": len(completed_sources),
                    "last_progress_at": utcnow(),
                }
                if summary is not None:
                    values["deal_summary"] = dict(deal_progress_summary)
                await db.execute(update(IngestionRun).where(IngestionRun.id == progress_run_id).values(**values))
                await db.commit()

            deal_result = await collect(db, deal_sources, since=deal_since, until=deal_until,
                                        progress=update_deal_progress)
            await db.refresh(run)  # a collector rollback expires the loaded objects
            run.deal_summary = deal_result.as_json()
            errors.extend(deal_result.errors)
            failed = {e["source"] for e in deal_result.errors}
            successful.update(s for s in deal_sources if s not in failed)

        # 9. Determine final run status
        run.current_phase = "finalizing"
        run.current_source = None
        run.finished_at = utcnow()
        run.last_progress_at = run.finished_at
        run.errors = errors if errors else None

        if not errors:
            run.status = "completed"
        elif successful:
            run.status = "partial_failure"
        else:
            run.status = "failed"

        duration_s = (run.finished_at - run.started_at).total_seconds()
        run.summary_text = (
            f"Ingestion {run.status.upper()} in {duration_s:.1f}s | "
            f"Sources: {len(successful)}/{run.sources_total} OK | "
            f"Docs found: {run.documents_found}, new: {run.documents_new}, "
            f"downloaded: {run.documents_downloaded} | "
            f"Points extracted: {run.data_points_extracted} (needs_review: {run.data_points_needing_review})"
            + (f" | Deals created: {deal_result.deals_created} (needs_review)" if deal_result else "")
            + (f" | Existing deals enriched: {deal_result.deals_enriched} ({deal_result.fields_enriched} fields)"
               if deal_result else "")
        )

        await db.commit()
        if get_settings().auto_validation_enabled:
            from pathlib import Path

            from scraping.validation.automatic import validate_deals, validate_financial_data

            settings = get_settings()
            try:
                from scraping.storage.manager import StorageManager
                from scraping.universe.documents import DocumentRegistrar
                from scraping.universe.unit_repair import corroborate_with_fascicle, reread_units

                registrar = DocumentRegistrar(StorageManager(settings.documents_storage_path))
                unit_repair = await reread_units(db, registrar, dry_run=False)
                fascicle_repair = await corroborate_with_fascicle(db, dry_run=False)
                logger.info("financial_source_enrichment_finished", unit_repair=unit_repair.summary(),
                            fascicle_repair=fascicle_repair.summary())
                fd = await validate_financial_data(
                    db, storage_root=Path(settings.documents_storage_path),
                    scope_classes=tuple(c.strip() for c in settings.auto_validation_scope_classes.split(",")
                                        if c.strip()),
                    single_source_status=settings.auto_validation_single_source_status,
                )
                dl = await validate_deals(db, single_source_status=settings.auto_validation_single_source_status)
                logger.info("auto_validation_finished", financial_data=fd.summary(), deals=dl.summary())
            except Exception as err:  # recorded on the run: never a silent failure after "completed"
                logger.error("auto_validation_failed", run_id=run.id, error=str(err))
                await db.rollback()
                await db.refresh(run)
                run.errors = [*(run.errors or []), {"source": "all", "phase": "auto_validation", "error": str(err),
                                                   "timestamp": utcnow().isoformat()}]
                if run.status == "completed":
                    run.status = "partial_failure"
                run.summary_text = f"{run.summary_text} | Auto-validation FAILED: {err}"[:2000]
                await db.commit()
        logger.info(
            "ingestion_run_finished",
            run_id=run.id,
            status=run.status,
            summary=run.summary_text,
        )
        return run
