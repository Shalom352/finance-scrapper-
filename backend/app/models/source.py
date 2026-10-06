"""
UMOA Banking Intelligence — Source Model

Registry of data sources.
Every piece of data must be traceable to a source entry.

Sources are seeded from well-known official institutions.
No invented sources.
"""

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.discovery import SOURCE_LIFECYCLE_STATUSES, sql_in
from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.banking_group import BankingGroup
    from app.models.document import Document
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution


class Source(Base):
    """
    Data source registry.

    All financial data must be linked to a Source.
    Sources represent official institutions or publications.

    Source types (open string — not an enum — for extensibility):
      regulatory    : CB-UMOA, CREPMF
      central_bank  : BCEAO
      bank          : individual bank website/report
      banking_group : banking group consolidation
      government    : ministry, national institution
      financial_market : stock exchange, bond market
      secondary     : press, secondary analysis (lower priority)
    """

    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint(
            f"lifecycle_status IN ({sql_in(SOURCE_LIFECYCLE_STATUSES)})",
            name="ck_sources_lifecycle_status",
        ),
    )

    # Official name of the source/institution
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Short name / acronym
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Publisher / issuing institution description
    publisher: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Main URL of the source (verified, not invented)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Source type (open string for extensibility)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Priority: 1 (highest, official) → 3 (secondary)
    priority: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    # ISO country code if source is country-specific (nullable = supranational)
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    # Language of publications (ISO 639-1)
    language: Mapped[str | None] = mapped_column(String(5), nullable=True)

    # Description of the source and its relevance
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Whether this source is currently active / being monitored
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Explicit lifecycle (Phase 15): CANDIDATE → VERIFIED → ACTIVE, or BLOCKED / RETIRED.
    # A source becomes ACTIVE only once it has produced a downloaded document.
    lifecycle_status: Mapped[str] = mapped_column(String(20), default="CANDIDATE", nullable=False, server_default="CANDIDATE")
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Expected publication cadence used to schedule re-checks (NULL = unknown)
    check_frequency_days: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    institutions: Mapped[list["Institution"]] = relationship(  # type: ignore[name-defined]
        "Institution", back_populates="source", lazy="noload"
    )
    banking_groups: Mapped[list["BankingGroup"]] = relationship(  # type: ignore[name-defined]
        "BankingGroup", back_populates="source", lazy="noload"
    )
    documents: Mapped[list["Document"]] = relationship(  # type: ignore[name-defined]
        "Document", back_populates="source", lazy="noload"
    )
    financial_data: Mapped[list["FinancialData"]] = relationship(  # type: ignore[name-defined]
        "FinancialData", back_populates="source", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Source {self.short_name or self.name!r}>"
