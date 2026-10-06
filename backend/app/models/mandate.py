"""
UMOA Financial Intelligence — Internal mandates (Phase 20).

TOMASTEED's own financing mandates and the institutions approached on each of them.
Internal data, entered by the team (``recorded_by``); it is never presented as published data.
A counterparty is linked to the directory only by an exact identifier (institution or entity);
otherwise it keeps its name alone.
"""

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.deals import COUNTERPARTY_STAGES, MANDATE_STATUSES, SECTORS, sql_in
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

    country: Mapped["Country | None"] = relationship("Country", lazy="noload")
    counterparties: Mapped[list["MandateCounterparty"]] = relationship(
        "MandateCounterparty", back_populates="mandate", lazy="noload", order_by="MandateCounterparty.created_at"
    )


class MandateCounterparty(Base):
    __tablename__ = "mandate_counterparties"
    __table_args__ = (
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

    mandate: Mapped[Mandate] = relationship("Mandate", back_populates="counterparties", lazy="noload")
    institution: Mapped["Institution | None"] = relationship("Institution", lazy="noload")
    entity: Mapped["Entity | None"] = relationship("Entity", lazy="noload")
