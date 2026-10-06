"""
UMOA Banking Intelligence — Automated Ingestion Service

Orchestrates automated and manual ingestion executions:
  1. Computes target years (current year down to current year - historical_years).
  2. Enforces concurrency protection (single running ingestion at any time).
  3. Discovers documents from registered official sources (BCEAO, CB-UMOA).
  4. Downloads new/modified documents idempotently (SHA-256 hash tracking).
  5. Parses PDF documents and extracts financial metrics.
  6. Applies Phase 13 scope guard (needs_review + "scope not detected").
  7. Protects reviewed, verified, and rejected observations against overwriting.
  8. Tracks granular metrics and source-level errors (supporting partial failures).
"""

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, func, select
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
    ) -> IngestionRun:
        """
        Execute an end-to-end ingestion run across official sources and target years.
        """
        years = target_years or get_target_years()
        years_str = ", ".join(str(y) for y in years)

        # 1. Check for concurrency lock
        if _INGESTION_LOCK.locked() and not force:
            logger.warning("ingestion_skipped_concurrency_lock")
            run = IngestionRun(
                trigger_type=trigger_type,
                status="skipped_concurrent",
                started_at=utcnow(),
                finished_at=utcnow(),
                target_years=years_str,
                summary_text="Run skipped: another ingestion run is currently in progress.",
            )
            db.add(run)
            await db.commit()
            return run

        async with _INGESTION_LOCK:
            # Check database for any active running state
            active_res = await db.execute(
                select(IngestionRun).where(IngestionRun.status == "running")
            )
            active_existing = active_res.scalar_one_or_none()
            if active_existing and not force and (run_id is None or active_existing.id != run_id):
                logger.warning("ingestion_skipped_database_running_state", active_id=active_existing.id)
                run = IngestionRun(
                    trigger_type=trigger_type,
                    status="skipped_concurrent",
                    started_at=utcnow(),
                    finished_at=utcnow(),
                    target_years=years_str,
                    summary_text=f"Run skipped: active run {active_existing.id} in database.",
                )
                db.add(run)
                await db.commit()
                return run

            # 2. Initialize or fetch IngestionRun record
            if run_id:
                run_res = await db.execute(select(IngestionRun).where(IngestionRun.id == run_id))
                run = run_res.scalar_one_or_none()
            else:
                run = None

            if run is None:
                run = IngestionRun(
                    trigger_type=trigger_type,
                    status="running",
                    started_at=utcnow(),
                    target_years=years_str,
                )
                db.add(run)
                await db.commit()

            logger.info("ingestion_run_started", run_id=run.id, trigger_type=trigger_type, years=years)

            # 3. Determine official sources to query
            sources_to_check = sources or ["bceao", "cb-umoa", "brvm", "umoa-titres"]
            run.sources_checked = len(sources_to_check)

            errors: list[dict[str, Any]] = []
            total_discovered = 0
            total_new_docs = 0
            successful_sources = 0

            # Count existing documents before discovery
            existing_doc_count = (await db.execute(select(func.count(Document.id)).where(Document.deleted_at.is_(None)))).scalar_one()

            # 4. Phase: Discovery across sources
            for src in sources_to_check:
                try:
                    logger.info("ingestion_discovering_source", source=src, run_id=run.id)
                    discovered = await self.pipeline.discover_source(
                        source_name=src,
                        db=db,
                        limit=limit_per_source,
                    )
                    total_discovered += len(discovered)
                    successful_sources += 1
                except Exception as err:
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

            # 5. Phase: Download pending documents
            total_downloaded = 0
            total_download_failed = 0
            try:
                logger.info("ingestion_downloading_pending_documents", run_id=run.id)
                download_results = await self.pipeline.download_pending_documents(db=db)
                for _, dl_res, storage_res in download_results:
                    if dl_res.success and storage_res:
                        total_downloaded += 1
                    else:
                        total_download_failed += 1
            except Exception as err:
                logger.error("ingestion_download_batch_failed", error=str(err))
                errors.append({
                    "source": "all",
                    "phase": "download",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

            run.documents_downloaded = total_downloaded
            run.documents_failed = total_download_failed
            run.documents_skipped = max(0, total_discovered - total_new_docs)

            # 6. Phase: Parsing & Classification
            try:
                logger.info("ingestion_parsing_downloaded_documents", run_id=run.id)
                await self.pipeline.parse_downloaded_documents(db=db)
            except Exception as err:
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
                logger.info("ingestion_extracting_financial_data", run_id=run.id)
                extraction_results = await self.pipeline.extract_financial_data(db=db)
                for _, points in extraction_results:
                    total_extracted += len(points)
                    for pt in points:
                        if getattr(pt, "status", None) == "needs_review":
                            total_needing_review += 1
            except Exception as err:
                logger.error("ingestion_extraction_batch_failed", error=str(err))
                errors.append({
                    "source": "all",
                    "phase": "extraction",
                    "error": str(err),
                    "timestamp": utcnow().isoformat(),
                })

            run.data_points_extracted = total_extracted
            run.data_points_needing_review = total_needing_review

            # 8. Determine final run status
            run.finished_at = utcnow()
            run.errors = errors if errors else None

            if not errors:
                run.status = "completed"
            elif successful_sources > 0:
                run.status = "partial_failure"
            else:
                run.status = "failed"

            duration_s = (run.finished_at - run.started_at).total_seconds()
            run.summary_text = (
                f"Ingestion {run.status.upper()} in {duration_s:.1f}s | "
                f"Sources: {successful_sources}/{len(sources_to_check)} OK | "
                f"Docs found: {run.documents_found}, new: {run.documents_new}, "
                f"downloaded: {run.documents_downloaded} | "
                f"Points extracted: {run.data_points_extracted} (needs_review: {run.data_points_needing_review})"
            )

            await db.commit()
            logger.info(
                "ingestion_run_finished",
                run_id=run.id,
                status=run.status,
                summary=run.summary_text,
            )
            return run
