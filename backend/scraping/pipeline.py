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
from scraping.connectors.brvm import BRVMConnector
from scraping.connectors.cb_umoa import CBUMOAConnector
from scraping.connectors.umoa_titres import UMOATitresConnector
from scraping.download.manager import DownloadManager
from scraping.storage.manager import StorageManager

logger = get_logger(__name__)

# Scope guard (Phase 13). The extractor does NOT detect whether a statement is individual
# or consolidated. The technical value stored is "individual" (the column is NOT NULL and
# no "unknown" scope exists), so every extracted point is held for a human decision:
# status needs_review + the explicit note below. Eligibility already excludes needs_review
# from rankings, comparisons, ratios, growth and aggregations. Existing rows are never
# modified retroactively by this rule.
EXTRACTION_SCOPE = "individual"
SCOPE_NOT_DETECTED_NOTE = "scope not detected"
# A re-extraction never overwrites a human decision.
PROTECTED_STATUSES = ("reviewed", "verified", "rejected")


def _append_note(notes: str | None, note: str) -> str:
    text = notes or ""
    if note in text:
        return text
    return f"{text} | {note}" if text else note


def scope_guard(
    status: str | None,
    notes: str | None,
    assessment: Any | None = None,
    quality_flags: list[dict] | None = None,
) -> tuple[str, str]:
    """Scope guard (Phase 13, extended Phase 16). Never produces reviewed / verified.

    - no assessment (legacy callers)          → needs_review + "scope not detected" (unchanged);
    - class A/B, extractor proposed 'extracted',
      no blocking quality flag                → 'extracted' + the documentary evidence;
    - anything else (C, D, contradiction, a blocking flag, or the extractor already
      asked for review)                       → needs_review + the structured reason.
    """
    from scraping.quality.checks import has_blocking_flag

    if assessment is None:
        return "needs_review", _append_note(notes, SCOPE_NOT_DETECTED_NOTE)
    if assessment.promotable and status == "extracted" and not has_blocking_flag(quality_flags):
        return "extracted", _append_note(
            notes, f"scope {assessment.scope} ({assessment.evidence_class}: {assessment.reason_code})"
        )
    note = SCOPE_NOT_DETECTED_NOTE if assessment.reason_code == "scope_not_stated" else (
        f"scope {assessment.reason_code}"
    )
    if assessment.promotable:
        note = f"scope {assessment.scope} ({assessment.evidence_class}) held: " + (
            "blocking quality flag" if has_blocking_flag(quality_flags) else "extraction requires review"
        )
    return "needs_review", _append_note(notes, note)



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
            "brvm": BRVMConnector(),
            "umoa-titres": UMOATitresConnector(),
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
                # Phase 16: market-infrastructure publications; anything else stays 'unknown'
                # (never presumed institution-specific).
                document_scope="market" if source_short_name in ("BRVM", "UMOA-Titres") else "unknown",
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
        from app.models.country import Country
        from app.models.entity import Entity
        from app.models.financial_data import FinancialData
        from scraping.parsing.financial_extractor import FinancialExtractor
        from scraping.parsing.market_extractor import MarketExtractor
        from scraping.parsing.pdf_parser import PDFParser

        query = (
            select(Document)
            .join(Document.source)
            .where(
                Document.download_status == "downloaded",
                Document.deleted_at.is_(None),
            )
        )
        if document_id:
            query = query.where(Document.id == document_id)
        else:
            query = query.where(Document.extraction_status == "extracted")
            # Phase 17: documents owned by the discovery engine have dedicated extractors; the generic
            # extractor (name-guessing resolver) must never re-read them.
            query = query.where(Document.document_scope.not_in(
                ("regulatory_aggregate", "institution_specific", "reference_listing")))

        if limit:
            query = query.limit(limit)

        res = await db.execute(query)
        docs = res.scalars().all()

        if not docs:
            logger.info("no_documents_to_extract_financial_data")
            return []

        parser = PDFParser()
        extractor = FinancialExtractor()
        market_extractor = MarketExtractor()
        if self.institution_resolver is not None:
            resolver = self.institution_resolver
        else:
            from scraping.reconciliation.resolver import InstitutionResolver
            resolver = InstitutionResolver()
            self.institution_resolver = resolver

        results: list[tuple[Document, list[Any]]] = []

        brvm_entity_id: str | None = None
        brvm_looked_up = False
        sovereign_entity_map: dict[str, str] | None = None

        for doc in docs:
            if not doc.storage_path or not doc.file_hash:
                continue

            abs_path = self.storage_manager.get_absolute_path(doc.file_hash)
            if not abs_path.is_file():
                continue

            source_short_name = doc.source.short_name if doc.source else ""

            try:
                # 1. Parse document structure
                parsed_doc = await parser.parse(
                    file_path=str(abs_path),
                    document_id=doc.id,
                    document_title=doc.title,
                )

                extracted_points: list[Any] = []
                scope_ctx = None  # Phase 16: documentary scope evidence, built once per document

                # 2. Extract based on source type: Market, Sovereign, or Banking
                if source_short_name == "BRVM":
                    if not brvm_looked_up:
                        brvm_entity = (
                            await db.execute(
                                select(Entity).where(
                                    Entity.canonical_name == "Bourse Régionale des Valeurs Mobilières",
                                    Entity.deleted_at.is_(None),
                                )
                            )
                        ).scalar_one_or_none()
                        brvm_entity_id = brvm_entity.id if brvm_entity else None
                        brvm_looked_up = True

                    extracted_points = market_extractor.extract_brvm_boc(
                        pdf_path=str(abs_path),
                        document_id=doc.id,
                        source_id=doc.source_id,
                        entity_id=brvm_entity_id,
                        period_year=doc.period_year or utcnow().year,
                    )
                elif source_short_name == "UMOA-Titres":
                    if sovereign_entity_map is None:
                        sovereign_ents = (
                            await db.execute(
                                select(Entity).where(
                                    Entity.entity_class.in_(["sovereign", "sovereign_entity"]),
                                    Entity.deleted_at.is_(None),
                                )
                            )
                        ).scalars().all()
                        sovereign_entity_map = {}
                        for ent in sovereign_ents:
                            if ent.country_id:
                                cntry = (
                                    await db.execute(
                                        select(Country).where(Country.id == ent.country_id)
                                    )
                                ).scalar_one_or_none()
                                if cntry:
                                    sovereign_entity_map[cntry.code] = ent.id

                    extracted_points = market_extractor.extract_umoa_titres_auction(
                        pdf_path=str(abs_path),
                        document_id=doc.id,
                        source_id=doc.source_id,
                        entity_map=sovereign_entity_map,
                        period_year=doc.period_year or utcnow().year,
                    )
                else:
                    # Traditional banking documents (BCEAO, CB-UMOA, Banks)
                    extracted_points = await extractor.extract_from_parsed_document(
                        parsed_doc=parsed_doc,
                        pdf_path=str(abs_path),
                        institution_id=doc.institution_id,
                        source_id=doc.source_id,
                        base_document_year=doc.period_year,
                    )

                # 3. Idempotent insertion into financial_data
                for pt in extracted_points:
                    target_entity_id = pt.metadata.get("entity_id") if hasattr(pt, "metadata") else None
                    obs_level = pt.metadata.get("observation_level", "entity") if hasattr(pt, "metadata") else "entity"
                    cons_scope = pt.metadata.get("consolidation_scope", "individual") if hasattr(pt, "metadata") else "individual"
                    target_institution_id = pt.institution_id or doc.institution_id

                    # If this is not a market observation, it requires an institution_id
                    if not target_entity_id and not target_institution_id:
                        if not resolver.matcher.institutions:
                            try:
                                await resolver.load_from_db(db)
                            except Exception as err:
                                logger.warning("failed_to_load_reconciliation_index", error=str(err))

                        cand_name = pt.table_context or doc.title or ""
                        res_match = resolver.resolve(cand_name)
                        if res_match.status == "matched" and res_match.institution_id:
                            target_institution_id = res_match.institution_id
                            pt.institution_id = res_match.institution_id
                            if res_match.confidence_level != "high_confidence":
                                pt.status = "needs_review"
                            pt.notes = f"{pt.notes} | Resolved to {res_match.institution_name} ({res_match.matched_by})"
                        else:
                            continue

                    # Phase 16: documentary scope evidence (banking statements only; market and
                    # sovereign observations keep consolidation_scope = not_applicable).
                    assessment = None
                    if cons_scope != "not_applicable":
                        if scope_ctx is None:
                            from scraping.quality.scope import DocumentScopeContext

                            scope_ctx = DocumentScopeContext.from_pdf_path(str(abs_path))
                        assessment = scope_ctx.assess(pt.page_number)
                        if assessment.promotable:
                            cons_scope = assessment.scope  # explicitly stated by the document

                    # Determine scope (satisfying ck_financial_data_scope: 'individual' | 'consolidated')
                    db_scope = "consolidated" if cons_scope == "consolidated" else "individual"

                    # Idempotency check: see if matching point exists
                    if target_entity_id:
                        existing_q = select(FinancialData).where(
                            FinancialData.entity_id == target_entity_id,
                            FinancialData.document_id == doc.id,
                            FinancialData.metric_code == pt.metric_code,
                            FinancialData.period_year == pt.period_year,
                            FinancialData.period_type == pt.period_type,
                            FinancialData.observation_level == obs_level,
                            FinancialData.deleted_at.is_(None),
                        )
                    else:
                        existing_q = select(FinancialData).where(
                            FinancialData.institution_id == target_institution_id,
                            FinancialData.document_id == doc.id,
                            FinancialData.metric_code == pt.metric_code,
                            FinancialData.period_year == pt.period_year,
                            FinancialData.period_type == pt.period_type,
                            FinancialData.scope == db_scope,
                            FinancialData.deleted_at.is_(None),
                        )

                    existing = (await db.execute(existing_q.order_by(FinancialData.created_at))).scalars().first()
                    guarded_status, guarded_notes = scope_guard(pt.status, pt.notes, assessment)
                    evidence_fields = {} if assessment is None else {
                        "scope_evidence_class": assessment.evidence_class,
                        "scope_reason_code": assessment.reason_code,
                        "scope_evidence": assessment.evidence,
                    }

                    if existing:
                        if existing.status in PROTECTED_STATUSES:
                            logger.info(
                                "protected_record_untouched",
                                data_id=existing.id,
                                status=existing.status,
                            )
                            continue
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
                            existing.status = guarded_status
                            existing.notes = guarded_notes
                            for field, field_value in evidence_fields.items():
                                setattr(existing, field, field_value)
                            existing.extracted_at = utcnow()
                    else:
                        new_data = FinancialData(
                            institution_id=target_institution_id if not target_entity_id else None,
                            entity_id=target_entity_id,
                            observation_level=obs_level,
                            consolidation_scope=cons_scope,
                            source_id=doc.source_id,
                            document_id=doc.id,
                            metric_code=pt.metric_code,
                            scope=db_scope,
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
                            status=guarded_status,
                            notes=guarded_notes,
                            extracted_at=utcnow(),
                            **evidence_fields,
                        )
                        db.add(new_data)

                results.append((doc, extracted_points))
            except Exception as err:
                logger.error("financial_data_extraction_failed", doc_id=doc.id, error=str(err))
                results.append((doc, []))

        await db.commit()
        logger.info("financial_data_extraction_completed", doc_count=len(results))
        return results

