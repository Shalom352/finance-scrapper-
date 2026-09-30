"""
UMOA Banking Intelligence — Banking Group Model

Registry of banking groups (holding companies) operating in UMOA.

IMPORTANT: Do not add banking groups without verifiable sourcing.
If information is uncertain, leave the field null rather than inventing it.
"""

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:  # relationship targets, resolved by SQLAlchemy at runtime
    from app.models.institution import Institution
    from app.models.source import Source


class BankingGroup(Base):
    """
    Banking group (holding / parent company).

    Groups aggregate multiple bank subsidiaries across UMOA countries.
    Examples: Ecobank (ETI), Banque Atlantique, Coris Bank International,
    Société Générale (West Africa presence), BNP Paribas, etc.

    All data must be verifiable from official sources.
    Fields that cannot be verified should remain null.
    """

    __tablename__ = "banking_groups"

    # Official legal/registered name of the group
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    # Short/commercial name
    short_name: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Country of incorporation / headquarters (ISO 3166-1 alpha-2)
    # May be outside UMOA (e.g., France for BNP, Nigeria for GTBank)
    headquarter_country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # City of headquarters
    headquarter_city: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Official website URL (verified)
    website_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Brief description of the group
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Source from which this group's information was collected
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    source: Mapped["Source | None"] = relationship(  # type: ignore[name-defined]
        "Source", back_populates="banking_groups", lazy="joined"
    )
    institutions: Mapped[list["Institution"]] = relationship(  # type: ignore[name-defined]
        "Institution", back_populates="banking_group", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<BankingGroup {self.short_name or self.name!r}>"
