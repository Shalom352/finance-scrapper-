"""
UMOA Banking Intelligence — Review audit trail (Phase 12).

One append-only row per human decision on a financial observation
(review / verify / reject): who, when, why, status before / after and the
normalized value before / after. Rows are never updated nor deleted.
"""
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FinancialDataReviewEvent(Base):
    __tablename__ = "financial_data_review_events"
    __table_args__ = (
        CheckConstraint("action IN ('review', 'verify', 'reject')", name="ck_review_events_action"),
        Index("ix_review_events_data_created", "financial_data_id", "created_at"),
    )

    financial_data_id: Mapped[str] = mapped_column(
        ForeignKey("financial_data.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Declared by the operator: the platform has no authentication (documented limit).
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_before: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    value_after: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)

    def __repr__(self) -> str:
        return f"<FinancialDataReviewEvent {self.action} {self.previous_status}->{self.new_status}>"
