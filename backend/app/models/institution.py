"""
UMOA Banking Intelligence — Institution Model

Registry of banks and financial institutions in UMOA.

IMPORTANT:
- Never add institutions without verifiable official sourcing.
- If a field cannot be verified, leave it null.
- Do not assume group membership without documented evidence.

Institution types (open string):
  bank                : commercial bank (banque commerciale)
  microfinance        : microfinance institution
  insurance           : insurance company with financial activity
  financial_holding   : financial holding company
  development_bank    : development finance institution
  other               : other regulated financial institution
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.banking_group import BankingGroup
    from app.models.country import Country
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.financial_data import FinancialData
    from app.models.source import Source


class Institution(Base):
    """
    Bank or financial institution operating in UMOA.

    Each institution is linked to:
    - A country (required)
    - A source (required — for data provenance)
    - A banking group (optional — only when verifiably documented)
    """

    __tablename__ = "institutions"
    __table_args__ = (UniqueConstraint("entity_id", name="uq_institutions_entity_id"),)

    # Official registered name
    name_official: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Commercial/brand name (if different from official)
    name_commercial: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Institution type (open string for extensibility)
    institution_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="bank", index=True
    )

    # Country of operation (required)
    country_id: Mapped[str] = mapped_column(
        ForeignKey("countries.id", ondelete="RESTRICT"), nullable=False, index=True
    )

    # Banking group (nullable — only set when officially documented)
    banking_group_id: Mapped[str | None] = mapped_column(
        ForeignKey("banking_groups.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Regulatory identifier (e.g., BCEAO registration number)
    # Left null when not publicly available
    regulatory_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Official website URL (verified)
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Institution status
    # active | closed | in_liquidation | merged | unknown
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="active", index=True
    )

    # Brief description
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Notes about data quality or collection
    data_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source from which this institution was identified (required)
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Unified Entity Hub link (Phase 14)
    entity_id: Mapped[str | None] = mapped_column(
        ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True, index=True
    )

    # Relationships
    entity: Mapped["Entity | None"] = relationship(  # type: ignore[name-defined]
        "Entity", back_populates="institution", lazy="joined"
    )
    country: Mapped["Country"] = relationship(  # type: ignore[name-defined]
        "Country", back_populates="institutions", lazy="joined"
    )
    banking_group: Mapped["BankingGroup | None"] = relationship(  # type: ignore[name-defined]
        "BankingGroup", back_populates="institutions", lazy="joined"
    )
    source: Mapped["Source | None"] = relationship(  # type: ignore[name-defined]
        "Source", back_populates="institutions", lazy="joined"
    )
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="institution", lazy="noload"
    )
    financial_data: Mapped[list["FinancialData"]] = relationship(  # type: ignore[name-defined]
        "FinancialData", back_populates="institution", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Institution {self.name_official!r}>"
