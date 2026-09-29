"""
UMOA Banking Intelligence — Document Model

A Document is the materialised, traceable artifact from which every
financial value originates. It can be a PDF file or a web page
(``document_type = web_page``).

Reference: docs/specification-v1.md sections 10, 11, 14, 17.

Deduplication rules:
  - ``file_hash`` (SHA-256) is UNIQUE when present.
  - A missing ``file_hash`` does NOT prevent registration
    (document not yet downloaded).
  - Never deduplicate by institution + year.
  - URL alone is not sufficient to deduplicate.

Versioning: a corrected/republished document is a NEW Document.
Never overwrite an existing document's provenance.
"""

from datetime import date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Document(Base):
    """
    Downloadable / consultable document (official source artefact).

    All financial data must be linked to a Document.
    """

    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "document_type IN ('annual_report', 'financial_statement', "
            "'regulatory_report', 'press_release', 'web_page', 'other')",
            name="ck_documents_document_type",
        ),
        CheckConstraint(
            "download_status IN ('pending', 'downloaded', 'failed')",
            name="ck_documents_download_status",
        ),
        CheckConstraint(
            "extraction_status IN ('pending', 'extracted', 'failed', 'skipped')",
            name="ck_documents_extraction_status",
        ),
        CheckConstraint(
            "period_type IS NULL OR period_type IN ('annual', 'semi_annual', 'quarterly')",
            name="ck_documents_period_type",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_documents_page_count_positive",
        ),
        CheckConstraint(
            "file_size IS NULL OR file_size >= 0",
            name="ck_documents_file_size_non_negative",
        ),
    )

    # Document title (as published, or descriptive for web pages)
    title: Mapped[str] = mapped_column(String(500), nullable=False)

    # Document type (see CHECK above)
    document_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Institution the document concerns (nullable: general/sector-wide sources)
    institution_id: Mapped[str | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Source of the document (required — provenance)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Origin URL (not sufficient for deduplication on its own)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # SHA-256 content hash — UNIQUE when present (content-addressed storage)
    file_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)

    # File size in bytes
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relative storage path (content-addressed): {hash[:2]}/{hash}.{ext}
    storage_path: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Download lifecycle
    download_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )

    # Number of pages (PDF)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Extraction lifecycle
    extraction_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", index=True
    )

    # When extraction was performed
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Publication date (as stated by the source)
    published_at: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Covered period (document-level)
    period_year: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    period_type: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Document language (ISO 639-1)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # When the document was discovered/collected
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Last download/extraction error (if any)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    source: Mapped["Source"] = relationship(  # type: ignore[name-defined]
        "Source", back_populates="documents", lazy="joined"
    )
    institution: Mapped["Institution | None"] = relationship(  # type: ignore[name-defined]
        "Institution", back_populates="documents", lazy="joined"
    )
    financial_data: Mapped[list["FinancialData"]] = relationship(  # type: ignore[name-defined]
        "FinancialData", back_populates="document", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Document {self.title!r} ({self.document_type})>"