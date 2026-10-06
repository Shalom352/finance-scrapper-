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
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.entities import (
    CONSOLIDATION_SCOPES,
    OBSERVATION_LEVELS,
    sql_in,
)
from app.constants.quality import SCOPE_EVIDENCE_CLASSES, SCOPE_REASON_CODES
from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.institution import Institution
    from app.models.metric_definition import MetricDefinition
    from app.models.source import Source


class FinancialData(Base):
    """
    A single traceable financial value for an institution and a period.

    Every row carries its full provenance:
    institution -> source -> document -> page -> period -> metric.
    """

    __tablename__ = "financial_data"
    __table_args__ = (
        CheckConstraint(
            "validation_method IS NULL OR validation_method IN ('human', 'automatic')",
            name="ck_financial_data_validation_method",
        ),
        Index("ix_financial_data_validation_method", "validation_method"),
        # --- Enumerations (open strings guarded by CHECK) ---
        CheckConstraint(
            "scope IN ('individual', 'consolidated')",
            name="ck_financial_data_scope",
        ),
        CheckConstraint(
            f"observation_level IN ({sql_in(OBSERVATION_LEVELS)})",
            name="ck_financial_data_observation_level",
        ),
        CheckConstraint(
            f"consolidation_scope IN ({sql_in(CONSOLIDATION_SCOPES)})",
            name="ck_financial_data_consolidation_scope",
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
        CheckConstraint(
            "institution_id IS NOT NULL OR entity_id IS NOT NULL",
            name="ck_financial_data_target",
        ),
        # --- Scope evidence (Phase 16, migration 0012) ---
        CheckConstraint(
            f"scope_evidence_class IS NULL OR scope_evidence_class IN ({sql_in(SCOPE_EVIDENCE_CLASSES)})",
            name="ck_financial_data_scope_evidence_class",
        ),
        CheckConstraint(
            f"scope_reason_code IS NULL OR scope_reason_code IN ({sql_in(SCOPE_REASON_CODES)})",
            name="ck_financial_data_scope_reason_code",
        ),
        # Automatic qualification may only reach 'extracted' with explicit (A/B) evidence:
        # C/D evidence can never sit on an automatically 'extracted' row.
        CheckConstraint(
            "scope_evidence_class IS NULL OR scope_evidence_class IN ('A', 'B') OR status != 'extracted'",
            name="ck_financial_data_extracted_requires_explicit_scope",
        ),
        # --- Data explorer access paths (Phase 11, migration 0005) ---
        Index("ix_financial_data_period_scope_year", "period_type", "scope", "period_year"),
        Index("ix_financial_data_logical_key", "institution_id", "metric_code", "period_year", "period_type", "scope"),
        Index("ix_financial_data_currency_value", "currency_normalized", "value_normalized"),
        # --- Unified Entity Hub indexes (Phase 14) ---
        Index("ix_financial_data_entity_id", "entity_id"),
        Index("ix_financial_data_observation_level", "observation_level"),
        Index("ix_financial_data_consolidation_scope", "consolidation_scope"),
    )

    # --- Provenance & Targeting ---
    institution_id: Mapped[str | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True, index=True
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

    # Unified Entity Hub link and decoupled observation dimensions (Phase 14)
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True, index=True
    )
    observation_level: Mapped[str] = mapped_column(
        String(30), nullable=False, default="entity", index=True, server_default="entity"
    )
    consolidation_scope: Mapped[str] = mapped_column(
        String(30), nullable=False, default="individual", index=True, server_default="individual"
    )

    # Scope — backward-compatible V1 field (mirrors consolidation_scope for individual/consolidated)
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
    # Widened to 255 in migration 0007 (same bound as the audit actor).
    # No User table in V1 (replaced by an FK once auth exists).
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # --- Scope evidence & quality (Phase 16, migration 0012) ---
    # A/B = explicit documentary evidence; C = inferred; D = none / contradiction / unreadable.
    scope_evidence_class: Mapped[str | None] = mapped_column(String(1), nullable=True, index=True)
    scope_reason_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # Quoted evidence (snippet + page) — never a guess
    scope_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Informational flags: they never change a value; blocking flags prevent automatic promotion
    quality_flags: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    # Where the value was read, e.g. "p.23 · TOTAL DE L'ACTIF · col. 2023"
    source_location: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Automatic validation (Phase 21, migration 0018) — always reversible by a human.
    validation_method: Mapped[str | None] = mapped_column(String(10), nullable=True)
    auto_validation: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    auto_validation_blocked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    # Relationships
    entity: Mapped["Entity | None"] = relationship(  # type: ignore[name-defined]
        "Entity", back_populates="financial_data", lazy="joined"
    )
    institution: Mapped["Institution | None"] = relationship(  # type: ignore[name-defined]
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

