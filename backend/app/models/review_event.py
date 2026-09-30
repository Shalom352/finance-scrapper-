"""
UMOA Banking Intelligence — Review audit trail (Phase 12, generalized in Phase 13).

One append-only row per human decision: who, when, why, status before / after and the
value before / after. Rows are never updated nor deleted by the application.

Single journal for the platform (no second audit system): an event targets EITHER a
financial observation (``financial_data_id``) OR a deal (``deal_id``). Deal events may
also reference the duplicate candidate they decided (``deal_duplicate_candidate_id``).
For deals, value_before / value_after hold the deal amount.
"""
from decimal import Decimal

from sqlalchemy import CheckConstraint, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

REVIEW_EVENT_ACTIONS = (
    "review",
    "verify",
    "reject",
    "import",
    "mark_same_deal",
    "mark_distinct",
    "mark_same_deal_multi_source",
)


class FinancialDataReviewEvent(Base):
    __tablename__ = "financial_data_review_events"
    __table_args__ = (
        CheckConstraint(
            "action IN (" + ", ".join(f"'{a}'" for a in REVIEW_EVENT_ACTIONS) + ")",
            name="ck_review_events_action",
        ),
        CheckConstraint(
            "(financial_data_id IS NOT NULL AND deal_id IS NULL) OR (financial_data_id IS NULL AND deal_id IS NOT NULL)",
            name="ck_review_events_single_target",
        ),
        CheckConstraint(
            "deal_duplicate_candidate_id IS NULL OR deal_id IS NOT NULL",
            name="ck_review_events_candidate_on_deal",
        ),
        Index("ix_review_events_data_created", "financial_data_id", "created_at"),
        Index("ix_review_events_deal_created", "deal_id", "created_at"),
    )

    financial_data_id: Mapped[str | None] = mapped_column(
        ForeignKey("financial_data.id", ondelete="RESTRICT"), nullable=True
    )
    deal_id: Mapped[str | None] = mapped_column(ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True)
    deal_duplicate_candidate_id: Mapped[str | None] = mapped_column(
        ForeignKey("deal_duplicate_candidates.id", ondelete="RESTRICT"), nullable=True
    )
    action: Mapped[str] = mapped_column(String(30), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(20), nullable=False)
    new_status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Declared by the operator: the platform has no authentication (documented limit).
    actor: Mapped[str | None] = mapped_column(String(255), nullable=True)
    value_before: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)
    value_after: Mapped[Decimal | None] = mapped_column(Numeric(24, 6), nullable=True)

    def __repr__(self) -> str:
        return f"<FinancialDataReviewEvent {self.action} {self.previous_status}->{self.new_status}>"
