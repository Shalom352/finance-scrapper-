"""
UMOA Banking Intelligence — Scraping Pipeline Orchestrator

Ties together:
  Discovery (Connectors) → Database Registration → Download (DownloadManager) → Storage (StorageManager)

Guarantees:
  - Idempotent document registration (by URL and SHA-256).
  - Respects database CHECK constraints.
  - Safe error handling and status tracking.
"""
import time
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.document import Document
from app.models.source import Source
from scraping.common.models import DiscoveredDocument, DownloadResult, StorageResult
from scraping.connectors.base import BaseSourceConnector
from scraping.connectors.bceao import BCEAOConnector
from scraping.connectors.cb_umoa import CBUMOAConnector
from scraping.download.manager import DownloadManager
from scraping.storage.manager import StorageManager

logger = get_logger(__name__)


def utcnow() -> datetime:
    """Return timezone-aware UTC datetime."""
    return datetime.now(UTC)


class ScrapingPipeline:
    """Orchestrates document discovery, download, and content-addressed storage."""

    def __init__(
        self,
        storage_manager: StorageManager | None = None,
        download_manager: DownloadManager | None = None,
        institution_resolver: Any | None = None,
    ) -> None:
        settings = get_settings()
        self.storage_manager = storage_manager or StorageManager(settings.documents_storage_path)
        self.download_manager = download_manager or DownloadManager(
            concurrency=settings.scraper_concurrency,
            timeout_seconds=float(settings.scraper_timeout),
        )
        self.institution_resolver = institution_resolver
        self.connectors: dict[str, BaseSourceConnector] = {
            "bceao": BCEAOConnector(),
            "cb-umoa": CBUMOAConnector(),
        }

    def get_connector(self, source_name: str) -> BaseSourceConnector:
        """Get registered connector by name/slug."""
        key = source_name.lower().replace("_", "-")
        if key not in self.connectors:
            valid = ", ".join(self.connectors.keys())
            raise ValueError(f"Unknown connector {source_name!r}. Available: {valid}")
        return self.connectors[key]

    async def discover_source(
        self,
        source_name: str,
        db: AsyncSession | None = None,
        limit: int | None = None,
    ) -> list[DiscoveredDocument]:
        """
        Execute discovery for a given official source connector.

        If a database session is provided, saves new documents to the database.
        """
        connector = self.get_connector(source_name)
        start_time = time.perf_counter()

        logger.info("discovery_started", source=connector.source_short_name, limit=limit)

        async with httpx.AsyncClient(timeout=float(get_settings().scraper_timeout)) as client:
            discovered = await connector.discover(client, limit=limit)

        duration = time.perf_counter() - start_time
        logger.info(
            "discovery_finished",
            source=connector.source_short_name,
            found_count=len(discovered),
            duration_seconds=round(duration, 3),
        )

        if db is not None and discovered:
            await self._register_discovered_documents(db, connector.source_short_name, discovered)

        return discovered

    async def _register_discovered_documents(
        self,
        db: AsyncSession,
        source_short_name: str,
        documents: Sequence[DiscoveredDocument],
    ) -> list[Document]:
        """Persist discovered documents to PostgreSQL with download_status='pending'."""
        # Find the official source row
        res = await db.execute(
            select(Source).where(
                Source.short_name == source_short_name,
                Source.deleted_at.is_(None),
            )
        )
        source_row = res.scalar_one_or_none()
        if not source_row:
            # Fallback search by name
            res = await db.execute(
                select(Source).where(
                    Source.name.ilike(f"%{source_short_name}%"),
                    Source.deleted_at.is_(None),
                )
            )
            source_row = res.scalar_one_or_none()

        if not source_row:
            logger.warning("source_record_not_found_in_db", source_short_name=source_short_name)
            return []

        registered: list[Document] = []

        for doc_item in documents:
            # Idempotency check: see if document with this URL already exists
            existing_res = await db.execute(
                select(Document).where(
                    Document.url == doc_item.url,
                    Document.deleted_at.is_(None),
                )
            )
            existing_doc = existing_res.scalar_one_or_none()

            if existing_doc:
                logger.debug("document_already_registered", url=doc_item.url, doc_id=existing_doc.id)
                registered.append(existing_doc)
                continue

            new_doc = Document(
                title=doc_item.title[:500],
                document_type=doc_item.document_type,
                source_id=source_row.id,
                institution_id=doc_item.institution_id,
                url=doc_item.url[:2048],
                download_status="pending",
                extraction_status="pending",
                period_year=doc_item.period_year,
                period_type=doc_item.period_type,
                language=doc_item.language,
                collected_at=utcnow(),
            )
            db.add(new_doc)
            registered.append(new_doc)

        await db.commit()
        logger.info(
            "documents_registered_in_db",
            source=source_short_name,
            total_registered=len(registered),
        )
        return registered

    async def download_pending_documents(
        self,
        db: AsyncSession,
        source_short_name: str | None = None,
        limit: int | None = None,
    ) -> list[tuple[Document, DownloadResult, StorageResult | None]]:
        """
        Download documents that have download_status = 'pending'.

        Downloads bytes, computes SHA-256, stores content-addressed files,
        and updates DB statuses.
        """
        query = (
            select(Document)
            .where(
                Document.download_status == "pending",
                Document.deleted_at.is_(None),
            )
            .order_by(Document.created_at.asc())
        )
        if source_short_name:
            query = query.join(Document.source).where(Source.short_name == source_short_name)

        if limit:
            query = query.limit(limit)

        result = await db.execute(query)
        pending_docs = result.scalars().all()

        if not pending_docs:
            logger.info("no_pending_documents_to_download")
            return []

        logger.info("starting_downloads", count=len(pending_docs))
        results: list[tuple[Document, DownloadResult, StorageResult | None]] = []

        async with httpx.AsyncClient(timeout=float(get_settings().scraper_timeout)) as client:
            for doc in pending_docs:
                if not doc.url:
                    doc.download_status = "failed"
                    doc.error_message = "Document has no URL"
                    results.append((doc, DownloadResult(url="", success=False, error_message="No URL"), None))
                    continue

                # 1. Download
                dl_result = await self.download_manager.download_file(client, doc.url)

                if not dl_result.success or not dl_result.content:
                    doc.download_status = "failed"
                    doc.error_message = dl_result.error_message or "Download failed"
                    results.append((doc, dl_result, None))
                    continue

                # 2. Store & Hash
                storage_result = self.storage_manager.store_content(
                    content=dl_result.content,
                    original_filename=doc.url.split("/")[-1],
                )

                # 3. Deduplication check in DB
                dup_res = await db.execute(
                    select(Document).where(
                        Document.file_hash == storage_result.file_hash,
                        Document.id != doc.id,
                        Document.deleted_at.is_(None),
                    )
                )
                existing_with_same_hash = dup_res.scalar_one_or_none()
                if existing_with_same_hash:
                    logger.info(
                        "duplicate_content_hash_detected",
                        doc_id=doc.id,
                        existing_id=existing_with_same_hash.id,
                        hash=storage_result.file_hash,
                    )

                # 4. Update Document row
                doc.download_status = "downloaded"
                doc.file_hash = storage_result.file_hash
                doc.file_size = storage_result.file_size
                doc.storage_path = storage_result.relative_path
                doc.collected_at = utcnow()
                doc.error_message = None

                results.append((doc, dl_result, storage_result))

        await db.commit()
        logger.info("download_batch_completed", count=len(results))
        return results

    async def parse_downloaded_documents(
        self,
        db: AsyncSession,
        document_id: str | None = None,
        limit: int | None = None,
    ) -> list[tuple[Document, Any]]:
        """
        Parse downloaded PDF documents, analyze structure, and update database.
        """
        from scraping.parsing.pdf_parser import PDFParser

        query = select(Document).where(
            Document.download_status == "downloaded",
            Document.deleted_at.is_(None),
        )
        if document_id:
            query = query.where(Document.id == document_id)
        else:
            query = query.where(Document.extraction_status == "pending")

        if limit:
            query = query.limit(limit)

        res = await db.execute(query)
        docs = res.scalars().all()

        if not docs:
            logger.info("no_documents_to_parse")
            return []

        parser = PDFParser()
        results: list[tuple[Document, Any]] = []

        for doc in docs:
            if not doc.storage_path or not doc.file_hash:
                doc.extraction_status = "failed"
                doc.error_message = "Document missing storage_path or file_hash"
                results.append((doc, None))
                continue

            try:
                abs_path = self.storage_manager.get_absolute_path(doc.file_hash)
                parsed = await parser.parse(
                    file_path=str(abs_path),
                    document_id=doc.id,
                    document_title=doc.title,
                )
                doc.page_count = parsed.page_count
                doc.extraction_status = "extracted"
                doc.extracted_at = utcnow()
                doc.error_message = None
                results.append((doc, parsed))
            except Exception as err:
                logger.error("document_parsing_failed", doc_id=doc.id, error=str(err))
                doc.extraction_status = "failed"
                doc.error_message = str(err)
                results.append((doc, None))

        await db.commit()
        logger.info("parsing_batch_completed", count=len(results))
        return results

    async def extract_financial_data(
        self,
        db: AsyncSession,
        document_id: str | None = None,
        limit: int | None = None,
    ) -> list[tuple[Document, list[Any]]]:
        """
        Extract tabular financial metrics from parsed documents and populate financial_data.
        Adheres strictly to the rule: DATA MISSING > DATA WRONG.
        Never sets status='verified'.
        """
        from app.models.financial_data import FinancialData
        from scraping.parsing.financial_extractor import FinancialExtractor
        from scraping.parsing.pdf_parser import PDFParser

        query = select(Document).where(
            Document.download_status == "downloaded",
            Document.deleted_at.is_(None),
        )
        if document_id:
            query = query.where(Document.id == document_id)
        else:
            query = query.where(Document.extraction_status == "extracted")

        if limit:
            query = query.limit(limit)

        res = await db.execute(query)
        docs = res.scalars().all()

        if not docs:
            logger.info("no_documents_to_extract_financial_data")
            return []

        parser = PDFParser()
        extractor = FinancialExtractor()
        if self.institution_resolver is not None:
            resolver = self.institution_resolver
        else:
            from scraping.reconciliation.resolver import InstitutionResolver
            resolver = InstitutionResolver()
            self.institution_resolver = resolver

        results: list[tuple[Document, list[Any]]] = []

        for doc in docs:
            if not doc.storage_path or not doc.file_hash:
                continue

            abs_path = self.storage_manager.get_absolute_path(doc.file_hash)
            if not abs_path.is_file():
                continue

            try:
                # 1. Parse document structure
                parsed_doc = await parser.parse(
                    file_path=str(abs_path),
                    document_id=doc.id,
                    document_title=doc.title,
                )

                # 2. Extract financial metrics from tables
                extracted_points = await extractor.extract_from_parsed_document(
                    parsed_doc=parsed_doc,
                    pdf_path=str(abs_path),
                    institution_id=doc.institution_id,
                    source_id=doc.source_id,
                    base_document_year=doc.period_year,
                )

                # 3. Idempotent insertion into financial_data for points with an institution_id
                for pt in extracted_points:
                    target_institution_id = pt.institution_id or doc.institution_id
                    if not target_institution_id:
                        # Lazy load resolver index from db if not yet loaded
                        if not resolver.matcher.institutions:
                            try:
                                await resolver.load_from_db(db)
                            except Exception as err:
                                logger.warning("failed_to_load_reconciliation_index", error=str(err))

                        # Attempt resolution from table context or document title
                        cand_name = pt.table_context or doc.title or ""
                        res = resolver.resolve(cand_name)
                        if res.status == "matched" and res.institution_id:
                            target_institution_id = res.institution_id
                            pt.institution_id = res.institution_id
                            if res.confidence_level != "high_confidence":
                                pt.status = "needs_review"
                            pt.notes = f"{pt.notes} | Resolved to {res.institution_name} ({res.matched_by})"
                        else:
                            # Cannot insert into financial_data without institution_id (NOT NULL constraint)
                            continue

                    # Check if matching point already exists in financial_data for this document
                    existing_q = select(FinancialData).where(
                        FinancialData.institution_id == target_institution_id,
                        FinancialData.document_id == doc.id,
                        FinancialData.metric_code == pt.metric_code,
                        FinancialData.period_year == pt.period_year,
                        FinancialData.period_type == pt.period_type,
                        FinancialData.deleted_at.is_(None),
                    )
                    existing = (await db.execute(existing_q)).scalar_one_or_none()

                    if existing:
                        # Invariant: Never overwrite verified or reviewed records
                        if existing.status in ("verified", "reviewed"):
                            logger.info(
                                "protected_record_untouched",
                                data_id=existing.id,
                                status=existing.status,
                            )
                            continue
                        # Update only if new extraction has higher confidence
                        if (pt.confidence_score or 0.0) >= (existing.confidence_score or 0.0):
                            existing.value_original = pt.value_original
                            existing.unit_original = pt.unit_original
                            existing.currency_original = pt.currency_original
                            existing.value_normalized = pt.value_normalized
                            existing.unit_normalized = pt.unit_normalized
                            existing.currency_normalized = pt.currency_normalized
                            existing.page_number = pt.page_number
                            existing.extraction_method = pt.extraction_method
                            existing.confidence_score = pt.confidence_score
                            existing.status = pt.status
                            existing.notes = pt.notes
                            existing.extracted_at = utcnow()
                    else:
                        new_data = FinancialData(
                            institution_id=target_institution_id,
                            source_id=doc.source_id,
                            document_id=doc.id,
                            metric_code=pt.metric_code,
                            scope="individual",
                            period_type=pt.period_type,
                            period_year=pt.period_year,
                            period_label=pt.period_label,
                            value_original=pt.value_original,
                            unit_original=pt.unit_original,
                            currency_original=pt.currency_original,
                            value_normalized=pt.value_normalized,
                            unit_normalized=pt.unit_normalized,
                            currency_normalized=pt.currency_normalized,
                            page_number=pt.page_number,
                            extraction_method=pt.extraction_method,
                            confidence_score=pt.confidence_score,
                            status=pt.status,
                            notes=pt.notes,
                            extracted_at=utcnow(),
                        )
                        db.add(new_data)

                results.append((doc, extracted_points))
            except Exception as err:
                logger.error("financial_data_extraction_failed", doc_id=doc.id, error=str(err))
                results.append((doc, []))

        await db.commit()
        logger.info("financial_data_extraction_completed", doc_count=len(results))
        return results

