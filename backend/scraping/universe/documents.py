"""
Document registration for discovery (Phase 15).

Reuses the content-addressed StorageManager (SHA-256). Dedup rules of the Document model:
the file hash is unique; a republished file with a different hash is a NEW document; the URL
alone never deduplicates across different contents.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pymupdf
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.document import Document
from app.models.source import Source
from scraping.storage.manager import StorageManager


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class RegisteredDocument:
    document: Document
    is_new: bool


class DocumentRegistrar:
    def __init__(self, storage: StorageManager | None = None) -> None:
        self.storage = storage or StorageManager(get_settings().documents_storage_path)

    async def register_pdf(
        self,
        db: AsyncSession,
        *,
        source: Source,
        url: str,
        content: bytes,
        title: str,
        document_type: str,
        period_year: int | None = None,
        period_type: str | None = "annual",
        entity_id: str | None = None,
        institution_id: str | None = None,
        language: str = "fr",
        document_scope: str = "unknown",
        original_filename: str | None = None,
    ) -> RegisteredDocument:
        """Store the bytes and return the matching Document (existing one when the hash is known)."""
        file_hash = StorageManager.compute_sha256(content)
        existing = (
            await db.execute(select(Document).where(Document.file_hash == file_hash, Document.deleted_at.is_(None)))
        ).scalar_one_or_none()
        if existing is not None:
            if existing.document_scope == "unknown" and document_scope != "unknown":
                existing.document_scope = document_scope
            return RegisteredDocument(existing, False)

        stored = self.storage.store_content(
            content=content, original_filename=original_filename or url.rsplit("/", 1)[-1]
        )
        page_count: int | None = None
        try:
            with pymupdf.open(stream=content, filetype="pdf") as pdf:
                page_count = pdf.page_count or None
        except Exception:
            page_count = None

        doc = Document(
            title=title[:500],
            document_type=document_type,
            source_id=source.id,
            institution_id=institution_id,
            entity_id=entity_id,
            url=url[:2048],
            file_hash=stored.file_hash,
            file_size=stored.file_size,
            storage_path=stored.relative_path,
            download_status="downloaded",
            # The generic extraction pipeline must not re-read these files blindly: discovery
            # strategies own their dedicated parsers (see fascicle strategy).
            extraction_status="skipped",
            page_count=page_count,
            period_year=period_year,
            period_type=period_type,
            language=language,
            document_scope=document_scope,
            collected_at=utcnow(),
        )
        db.add(doc)
        await db.flush()
        return RegisteredDocument(doc, True)

    def read_bytes(self, document: Document) -> bytes | None:
        if not document.file_hash:
            return None
        path = self.storage.get_absolute_path(document.file_hash)
        return path.read_bytes() if path.is_file() else None
