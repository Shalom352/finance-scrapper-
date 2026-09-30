"""
UMOA Banking Intelligence — Deal Intelligence models (Phase 13).

A deal (financing transaction) is recorded ONLY from a structured import that
references existing documents / sources / pages. Rules:
  - every business field is nullable: an unpublished amount, rate, maturity,
    grace period, fee, guarantee or date stays NULL (never 0);
  - borrower / sponsor / arranger / lenders ... are participants with an explicit
    role attested by a source, never deduced;
  - provenance: deal_sources (deal level) + deal_field_sources (field level);
  - a new deal always starts as ``needs_review``; only a human decision in the
    Review Center moves it forward (audit trail: financial_data_review_events);
  - possible duplicates are recorded as candidates and never merged automatically.
    A human "same deal" decision sets ``merged_into_deal_id``; nothing is deleted.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.deals import (
    DEAL_STATUSES,
    DEAL_TYPES,
    DUPLICATE_STATES,
    INTEREST_RATE_TYPES,
    PARTICIPANT_ROLES,
    PROVENANCE_FIELDS,
    sql_in,
)
from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.country import Country
    from app.models.document import Document
    from app.models.institution import Institution
    from app.models.source import Source


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = (
        CheckConstraint(f"deal_type IS NULL OR deal_type IN ({sql_in(DEAL_TYPES)})", name="ck_deals_deal_type"),
        CheckConstraint(f"status IN ({sql_in(DEAL_STATUSES)})", name="ck_deals_status"),
        CheckConstraint(
            f"interest_rate_type IS NULL OR interest_rate_type IN ({sql_in(INTEREST_RATE_TYPES)})",
            name="ck_deals_interest_rate_type",
        ),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_deals_amount_positive"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_deals_currency_iso"),
        CheckConstraint("maturity_months IS NULL OR maturity_months > 0", name="ck_deals_maturity_positive"),
        CheckConstraint(
            "grace_period_months IS NULL OR grace_period_months >= 0", name="ck_deals_grace_non_negative"
        ),
        CheckConstraint(
            "status != 'verified' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_deals_verified_requires_validator",
        ),
        CheckConstraint(
            "merged_into_deal_id IS NULL OR merged_into_deal_id != id", name="ck_deals_not_merged_into_itself"
        ),
        Index("ix_deals_status", "status"),
        Index("ix_deals_country_signing", "country_id", "signing_date"),
        Index("ix_deals_deal_type", "deal_type"),
        Index("ix_deals_currency", "currency"),
        Index("ix_deals_merged_into", "merged_into_deal_id"),
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    deal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    country_id: Mapped[str | None] = mapped_column(ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    project_name: Mapped[str | None] = mapped_column(Text, nullable=True)

    amount_original: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(20), nullable=True)

    interest_rate: Mapped[Decimal | None] = mapped_column(Numeric(9, 4), nullable=True)
    interest_rate_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    benchmark: Mapped[str | None] = mapped_column(String(50), nullable=True)
    spread_bps: Mapped[Decimal | None] = mapped_column(Numeric(9, 2), nullable=True)
    maturity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    grace_period_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fees: Mapped[str | None] = mapped_column(Text, nullable=True)
    guarantees: Mapped[str | None] = mapped_column(Text, nullable=True)

    announcement_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    signing_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    financial_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closing_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False, default="needs_review")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    merged_into_deal_id: Mapped[str | None] = mapped_column(
        ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True
    )

    country: Mapped["Country | None"] = relationship("Country", lazy="noload")
    participants: Mapped[list["DealParticipant"]] = relationship(
        "DealParticipant", back_populates="deal", lazy="noload", order_by="DealParticipant.created_at"
    )
    sources: Mapped[list["DealSource"]] = relationship(
        "DealSource", back_populates="deal", lazy="noload", order_by="DealSource.created_at"
    )
    field_sources: Mapped[list["DealFieldSource"]] = relationship(
        "DealFieldSource", back_populates="deal", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Deal {self.title!r} status={self.status!r}>"


class DealSource(Base):
    """Deal-level provenance: an existing document / source / page attesting the deal."""

    __tablename__ = "deal_sources"
    __table_args__ = (
        CheckConstraint("page_number > 0", name="ck_deal_sources_page_positive"),
        UniqueConstraint("deal_id", "document_id", "page_number", name="uq_deal_sources_deal_document_page"),
        Index("ix_deal_sources_deal", "deal_id"),
        Index("ix_deal_sources_document", "document_id"),
    )

    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    deal: Mapped[Deal] = relationship("Deal", back_populates="sources", lazy="noload")
    document: Mapped["Document"] = relationship("Document", lazy="noload")
    source: Mapped["Source"] = relationship("Source", lazy="noload")


class DealFieldSource(Base):
    """Field-level provenance: which deal source attests which field (several allowed)."""

    __tablename__ = "deal_field_sources"
    __table_args__ = (
        CheckConstraint(f"field_name IN ({sql_in(PROVENANCE_FIELDS)})", name="ck_deal_field_sources_field"),
        UniqueConstraint("deal_id", "field_name", "deal_source_id", name="uq_deal_field_sources"),
        Index("ix_deal_field_sources_deal", "deal_id"),
    )

    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False)
    field_name: Mapped[str] = mapped_column(String(40), nullable=False)
    deal_source_id: Mapped[str] = mapped_column(ForeignKey("deal_sources.id", ondelete="RESTRICT"), nullable=False)

    deal: Mapped[Deal] = relationship("Deal", back_populates="field_sources", lazy="noload")


class DealParticipant(Base):
    """A party to the deal with an explicit role attested by a deal source."""

    __tablename__ = "deal_participants"
    __table_args__ = (
        CheckConstraint(f"role IN ({sql_in(PARTICIPANT_ROLES)})", name="ck_deal_participants_role"),
        CheckConstraint(
            "commitment_amount IS NULL OR commitment_amount > 0", name="ck_deal_participants_commitment_positive"
        ),
        CheckConstraint(
            "commitment_currency IS NULL OR commitment_currency ~ '^[A-Z]{3}$'",
            name="ck_deal_participants_currency_iso",
        ),
        Index("ix_deal_participants_deal", "deal_id"),
        Index("ix_deal_participants_institution_role", "institution_id", "role"),
    )

    deal_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False)
    participant_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[str | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    commitment_amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    commitment_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    deal_source_id: Mapped[str] = mapped_column(ForeignKey("deal_sources.id", ondelete="RESTRICT"), nullable=False)

    deal: Mapped[Deal] = relationship("Deal", back_populates="participants", lazy="noload")
    institution: Mapped["Institution | None"] = relationship("Institution", lazy="noload")


class DealDuplicateCandidate(Base):
    """Two deals that look alike on explicit criteria. Never a merge by itself."""

    __tablename__ = "deal_duplicate_candidates"
    __table_args__ = (
        CheckConstraint("deal_a_id < deal_b_id", name="ck_deal_duplicates_ordered_pair"),
        CheckConstraint(f"state IN ({sql_in(DUPLICATE_STATES)})", name="ck_deal_duplicates_state"),
        CheckConstraint(
            "state = 'duplicate_candidate' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_deal_duplicates_decision_traced",
        ),
        UniqueConstraint("deal_a_id", "deal_b_id", name="uq_deal_duplicates_pair"),
        Index("ix_deal_duplicates_state", "state"),
    )

    deal_a_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False)
    deal_b_id: Mapped[str] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False)
    # Explicit list of the criteria that matched (e.g. ["borrower", "currency_amount"]). No score.
    matched_criteria: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="duplicate_candidate")
    primary_deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
