"""
UMOA Financial Intelligence — Entity Hub Model (Phase 14).

Universal registry for all entities (financial institutions, regulators,
market infrastructures, sovereign entities, corporates, SPVs, macro regions).
"""

from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.entities import (
    ENTITY_CLASSES,
    ENTITY_STATUSES,
    ENTITY_TYPES,
    sql_in,
)
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.country import Country
    from app.models.entity_relationship import EntityRelationship
    from app.models.financial_data import FinancialData
    from app.models.institution import Institution


class Entity(Base):
    """
    Central entity registry across all financial sectors.
    """

    __tablename__ = "entities"
    __table_args__ = (
        CheckConstraint(
            f"entity_class IN ({sql_in(ENTITY_CLASSES)})",
            name="ck_entities_entity_class",
        ),
        CheckConstraint(
            f"entity_type IN ({sql_in(ENTITY_TYPES)})",
            name="ck_entities_entity_type",
        ),
        CheckConstraint(
            f"status IN ({sql_in(ENTITY_STATUSES)})",
            name="ck_entities_status",
        ),
        Index("ix_entities_canonical_name", "canonical_name"),
        Index("ix_entities_entity_class", "entity_class"),
        Index("ix_entities_entity_type", "entity_type"),
        Index("ix_entities_country_id", "country_id"),
        Index("ix_entities_status", "status"),
    )

    # Class & Type
    entity_class: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)

    # Names
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Country (nullable for supranational / regional entities)
    country_id: Mapped[str | None] = mapped_column(
        ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True
    )

    # Official website (Phase 20 directory); the only URL from which the entity was registered.
    website: Mapped[str | None] = mapped_column(String(2048), nullable=True)

    # Description & Status
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", server_default="active")

    # Relationships
    country: Mapped["Country | None"] = relationship("Country", lazy="joined")
    institution: Mapped["Institution | None"] = relationship(
        "Institution", back_populates="entity", uselist=False, lazy="noload"
    )
    financial_data: Mapped[list["FinancialData"]] = relationship(
        "FinancialData", back_populates="entity", lazy="noload"
    )
    outgoing_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.source_entity_id",
        back_populates="source_entity",
        lazy="noload",
    )
    incoming_relationships: Mapped[list["EntityRelationship"]] = relationship(
        "EntityRelationship",
        foreign_keys="EntityRelationship.target_entity_id",
        back_populates="target_entity",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Entity {self.canonical_name!r} class={self.entity_class!r} type={self.entity_type!r}>"
