"""
UMOA Financial Intelligence — Internal mandates (Phase 20).

TOMASTEED's own financing mandates and the institutions approached on each of them.
Internal data, entered by the team (``recorded_by``); it is never presented as published data.
A counterparty is linked to the directory only by an exact identifier (institution or entity);
otherwise it keeps its name alone.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
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
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.deals import (
    COUNTERPARTY_STAGES,
    LENDER_TYPES,
    MANDATE_STATUSES,
    RECORD_ORIGINS,
    SECTORS,
    SYNDICATION_IMPORT_STATUSES,
    sql_in,
)
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.country import Country
    from app.models.entity import Entity
    from app.models.institution import Institution


class Mandate(Base):
    __tablename__ = "mandates"
    __table_args__ = (
        UniqueConstraint("code", name="uq_mandates_code"),
        CheckConstraint(f"status IN ({sql_in(MANDATE_STATUSES)})", name="ck_mandates_status"),
        CheckConstraint(f"sector IS NULL OR sector IN ({sql_in(SECTORS)})", name="ck_mandates_sector"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_mandates_amount_positive"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_mandates_currency_iso"),
        CheckConstraint("amount IS NULL OR currency IS NOT NULL", name="ck_mandates_amount_has_currency"),
        CheckConstraint("maturity_months IS NULL OR maturity_months > 0", name="ck_mandates_maturity_positive"),
        CheckConstraint(f"origin IN ({sql_in(RECORD_ORIGINS)})", name="ck_mandates_origin"),
    )

    code: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country_id: Mapped[str | None] = mapped_column(ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(40), nullable=True)
    deal_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    maturity_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active", server_default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    # Syndication tracker (migration 0022): raw values as written in the Excel, never reinterpreted.
    stage_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    country_code_raw: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_updated_from_file: Mapped[date | None] = mapped_column(Date, nullable=True)
    origin: Mapped[str] = mapped_column(String(15), nullable=False, default="manual", server_default="manual")
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("syndication_imports.id", ondelete="RESTRICT"), nullable=True
    )
    # Values of the LAST Excel import (3-way merge: a field edited in the platform since then is a
    # conflict when the Excel brings another value) and the time of the last edit in the platform.
    excel_snapshot: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    manually_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    country: Mapped["Country | None"] = relationship("Country", lazy="noload")
    counterparties: Mapped[list["MandateCounterparty"]] = relationship(
        "MandateCounterparty", back_populates="mandate", lazy="noload", order_by="MandateCounterparty.created_at"
    )


class MandateCounterparty(Base):
    __tablename__ = "mandate_counterparties"
    __table_args__ = (
        CheckConstraint(f"lender_type IS NULL OR lender_type IN ({sql_in(LENDER_TYPES)})",
                        name="ck_mandate_counterparties_lender_type"),
        CheckConstraint(f"origin IN ({sql_in(RECORD_ORIGINS)})", name="ck_mandate_counterparties_origin"),
        CheckConstraint(f"stage IN ({sql_in(COUNTERPARTY_STAGES)})", name="ck_mandate_counterparties_stage"),
        CheckConstraint("amount IS NULL OR amount > 0", name="ck_mandate_counterparties_amount_positive"),
        CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_mandate_counterparties_currency_iso"),
        CheckConstraint(
            "amount IS NULL OR currency IS NOT NULL", name="ck_mandate_counterparties_amount_has_currency"
        ),
        Index("ix_mandate_counterparties_mandate", "mandate_id"),
        Index("ix_mandate_counterparties_institution", "institution_id"),
        Index("ix_mandate_counterparties_entity", "entity_id"),
    )

    mandate_id: Mapped[str] = mapped_column(ForeignKey("mandates.id", ondelete="RESTRICT"), nullable=False)
    counterparty_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[str | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True
    )
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True)
    stage: Mapped[str] = mapped_column(String(20), nullable=False)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    contact_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
    # Syndication terms (migration 0022), as written: amounts / rates / fees stay text, and amount /
    # currency are filled only when ONE explicit amount with its currency is given.
    lender_type: Mapped[str | None] = mapped_column(String(15), nullable=True)
    appetite: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    amount_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    rate_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    arrangement_fee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    commitment_fee_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    maturity_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    dossier_status_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    nda_sent_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    nda_received_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_steps: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(15), nullable=False, default="manual", server_default="manual")
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("syndication_imports.id", ondelete="RESTRICT"), nullable=True
    )

    mandate: Mapped[Mandate] = relationship("Mandate", back_populates="counterparties", lazy="noload")
    institution: Mapped["Institution | None"] = relationship("Institution", lazy="noload")
    entity: Mapped["Entity | None"] = relationship("Entity", lazy="noload")


class SyndicationImport(Base):
    """One upload of the syndication Excel: a preview (plan only), then applied (migration 0022)."""

    __tablename__ = "syndication_imports"
    __table_args__ = (
        CheckConstraint(f"status IN ({sql_in(SYNDICATION_IMPORT_STATUSES)})", name="ck_syndication_imports_status"),
        Index("ix_syndication_imports_sha", "file_sha256"),
        # The same file is applied once.
        Index("uq_syndication_imports_applied_sha", "file_sha256", unique=True,
              postgresql_where=text("status = 'applied'")),
    )

    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    file_updated_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(15), nullable=False, default="preview")
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[dict] = mapped_column(JSONB, nullable=False)
    counts: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class InstitutionContact(Base):
    """A person at an institution (internal CRM, migration 0022). Personal data: internal routes only."""

    __tablename__ = "institution_contacts"
    __table_args__ = (
        CheckConstraint(f"origin IN ({sql_in(RECORD_ORIGINS)})", name="ck_institution_contacts_origin"),
        UniqueConstraint("contact_key", name="uq_institution_contacts_key"),
        Index("ix_institution_contacts_institution", "institution_id"),
        Index("ix_institution_contacts_entity", "entity_id"),
        Index("ix_institution_contacts_mandate", "mandate_id"),
    )

    # Normalized "institution|email" (or "institution|name" without an e-mail): the identity of a contact.
    contact_key: Mapped[str] = mapped_column(String(400), nullable=False)
    institution_name: Mapped[str] = mapped_column(String(255), nullable=False)
    institution_id: Mapped[str | None] = mapped_column(
        ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True
    )
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    job_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_interaction_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    mandate_id: Mapped[str | None] = mapped_column(ForeignKey("mandates.id", ondelete="RESTRICT"), nullable=True)
    dataroom_access: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str] = mapped_column(String(15), nullable=False, default="manual", server_default="manual")
    import_batch_id: Mapped[str | None] = mapped_column(
        ForeignKey("syndication_imports.id", ondelete="RESTRICT"), nullable=True
    )
    excel_snapshot: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    manually_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recorded_by: Mapped[str] = mapped_column(String(255), nullable=False)
