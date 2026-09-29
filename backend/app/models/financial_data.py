"""
UMOA Banking Intelligence — Financial Data Model

Core of the V1 financial dataset. Answers:
    "What is the value of this indicator for this institution at this
     period, and what is its documentary proof?"

Reference: docs/specification-v1.md sections 4, 5, 12, 13, 14, 15.

Foundational rules:
  - Unit and currency are two DISTINCT concepts (six value fields).
  - ``value_original`` is never overwritten by the normalized value.
  - No FX conversion in V1: ``currency_normalized == currency_original``.
  - ``document_id`` is NOT NULL (a web page is materialised as a Document).
  - ``institution_id`` is NOT NULL: only institution-attachable scopes
    (``individual`` / ``consolidated``) are allowed in V1.
  - No automatic extraction process may set ``verified``.
"""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class FinancialData(Base):
    """
    A single traceable financial value for an institution and a period.

    Every row carries its full provenance:
    institution -> source -> document -> page -> period -> metric.
    """

    __tablename__ = "financial_data"
    __table_args__ = (
        # --- Enumerations (open strings guarded by CHECK) ---
        CheckConstraint(
            "scope IN ('individual', 'consolidated')",
            name="ck_financial_data_scope",
        ),
        CheckConstraint(
            "period_type IN ('annual', 'semi_annual', 'quarterly')",
            name="ck_financial_data_period_type",
        ),
        CheckConstraint(
            "extraction_method IN ('pdf_table', 'pdf_text', 'ocr', 'web_html', 'manual')",
            name="ck_financial_data_extraction_method",
        ),
        CheckConstraint(
            "status IN ('extracted', 'needs_review', 'reviewed', 'verified', 'rejected')",
            name="ck_financial_data_status",
        ),
        # --- Numeric integrity ---
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_financial_data_confidence_range",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_financial_data_page_number_positive",
        ),
        CheckConstraint(
            "period_year >= 1900 AND period_year <= 2100",
            name="ck_financial_data_period_year_range",
        ),
        # --- Validation workflow invariants ---
        CheckConstraint(
            "status NOT IN ('reviewed', 'verified') OR value_normalized IS NOT NULL",
            name="ck_financial_data_reviewed_requires_normalized",
        ),
        CheckConstraint(
            "status != 'verified' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_financial_data_verified_requires_validator",
        ),
        # --- Data explorer access paths (Phase 11, migration 0005) ---
        Index("ix_financial_data_period_scope_year", "period_type", "scope", "period_year"),
        Index("ix_financial_data_logical_key", "institution_id", "metric_code", "period_year", "period_type", "scope"),
        Index("ix_financial_data_currency_value", "currency_normalized", "value_normalized"),
    )

    # --- Provenance (all mandatory) ---
    institution_id: Mapped[str] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    source_id: Mapped[str] = mapped_column(
        ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    document_id: Mapped[str] = mapped_column(
        ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Metric reference (catalogue)
    metric_code: Mapped[str] = mapped_column(
        ForeignKey("metric_definitions.code", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Scope — only institution-attachable scopes in V1
    scope: Mapped[str] = mapped_column(String(20), nullable=False, default="individual", index=True)

    # --- Period ---
    period_type: Mapped[str] = mapped_column(String(20), nullable=False, default="annual")
    period_year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    # e.g. "2024", "S1 2024", "T3 2024" — consistent with period_type (§14)
    period_label: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # --- Original value (never overwritten) ---
    value_original: Mapped[str] = mapped_column(Text, nullable=False)
    unit_original: Mapped[str | None] = mapped_column(String(50), nullable=True)
    currency_original: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # --- Normalized value (no FX conversion in V1) ---
    value_normalized: Mapped[float | None] = mapped_column(Numeric(24, 6), nullable=True)
    unit_normalized: Mapped[str | None] = mapped_column(String(20), nullable=True)
    currency_normalized: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # --- Extraction provenance ---
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    confidence_score: Mapped[float | None] = mapped_column(Numeric(4, 3), nullable=True)

    # --- Validation workflow ---
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="extracted", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    extracted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Technical validator identifier (agent code / e-mail), NOT a display name.
    # No User table in V1 (replaced by an FK once auth exists).
    verified_by: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Relationships
    institution: Mapped["Institution"] = relationship(  # type: ignore[name-defined]
        "Institution", back_populates="financial_data", lazy="joined"
    )
    source: Mapped["Source"] = relationship(  # type: ignore[name-defined]
        "Source", back_populates="financial_data", lazy="joined"
    )
    document: Mapped["Document"] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="financial_data", lazy="joined"
    )
    metric: Mapped["MetricDefinition"] = relationship(  # type: ignore[name-defined]
        "MetricDefinition", back_populates="financial_data", lazy="joined"
    )

    def __repr__(self) -> str:
        return (
            f"<FinancialData {self.metric_code!r} "
            f"institution={self.institution_id!r} year={self.period_year} "
            f"status={self.status!r}>"
        )