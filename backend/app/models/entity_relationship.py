"""
UMOA Financial Intelligence — Entity Relationship Model (Phase 14).

Tracks cross-entity relationships (ownership, subsidiary, financing, supervision, etc.)
with temporal bounds, provenance, and confidence scoring.
"""

from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.constants.entities import RELATIONSHIP_TYPES, sql_in
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.entity import Entity
    from app.models.source import Source


class EntityRelationship(Base):
    """
    Directional, attributed relationship between two entities.
    """

    __tablename__ = "entity_relationships"
    __table_args__ = (
        CheckConstraint(
            "source_entity_id != target_entity_id",
            name="ck_entity_relationships_no_self_ref",
        ),
        CheckConstraint(
            f"relationship_type IN ({sql_in(RELATIONSHIP_TYPES)})",
            name="ck_entity_relationships_type",
        ),
        CheckConstraint(
            "ownership_percentage IS NULL OR (ownership_percentage >= 0 AND ownership_percentage <= 100)",
            name="ck_entity_relationships_ownership_pct",
        ),
        CheckConstraint(
            "voting_rights_percentage IS NULL OR (voting_rights_percentage >= 0 AND voting_rights_percentage <= 100)",
            name="ck_entity_relationships_voting_pct",
        ),
        CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_relationships_dates",
        ),
        CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_entity_relationships_page_positive",
        ),
        CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_entity_relationships_confidence",
        ),
        Index("ix_entity_relationships_source", "source_entity_id"),
        Index("ix_entity_relationships_target", "target_entity_id"),
        Index("ix_entity_relationships_type", "relationship_type"),
        Index("ix_entity_relationships_is_current", "is_current"),
    )

    # Entities
    source_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )
    target_entity_id: Mapped[str] = mapped_column(
        ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False
    )

    # Relationship nature
    relationship_type: Mapped[str] = mapped_column(String(50), nullable=False)
    role_context: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Ownership & Control metrics
    ownership_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    voting_rights_percentage: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # Validity
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, server_default=text("true"))

    # Provenance
    source_id: Mapped[str | None] = mapped_column(
        ForeignKey("sources.id", ondelete="SET NULL"), nullable=True
    )
    document_id: Mapped[str | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), nullable=True
    )
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence_score: Mapped[Decimal | None] = mapped_column(
        Numeric(4, 3), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    source_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[source_entity_id], back_populates="outgoing_relationships", lazy="joined"
    )
    target_entity: Mapped["Entity"] = relationship(
        "Entity", foreign_keys=[target_entity_id], back_populates="incoming_relationships", lazy="joined"
    )
    source: Mapped["Source | None"] = relationship("Source", lazy="noload")
    document: Mapped["Document | None"] = relationship("Document", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<EntityRelationship {self.relationship_type!r} "
            f"from={self.source_entity_id!r} to={self.target_entity_id!r}>"
        )
