"""
UMOA Banking Intelligence — Country Model

Represents UMOA member states.
The 8 countries are seeded once and are static reference data.

Source: BCEAO official list of UMOA member states
https://www.bceao.int/fr/content/presentation-de-lumoa
"""

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Country(Base):
    """
    UMOA member state.

    Static reference — seeded from official BCEAO/UMOA data.
    Do not modify or add countries without official sourcing.
    """

    __tablename__ = "countries"
    __table_args__ = (
        UniqueConstraint("code", name="uq_countries_code"),
    )

    # ISO 3166-1 alpha-2 country code
    code: Mapped[str] = mapped_column(String(2), nullable=False, index=True)

    # Official country name in French (BCEAO working language)
    name_fr: Mapped[str] = mapped_column(String(100), nullable=False)

    # Official country name in English
    name_en: Mapped[str] = mapped_column(String(100), nullable=False)

    # Unicode flag emoji (presentation only)
    flag_emoji: Mapped[str] = mapped_column(String(10), nullable=True)

    # Capital city name in French
    capital_fr: Mapped[str] = mapped_column(String(100), nullable=True)

    # Capital city name in English
    capital_en: Mapped[str] = mapped_column(String(100), nullable=True)

    # Whether this country is currently active in UMOA
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Relationships (defined in referenced models)
    institutions: Mapped[list["Institution"]] = relationship(  # type: ignore[name-defined]
        "Institution", back_populates="country", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<Country {self.code} {self.name_fr!r}>"
