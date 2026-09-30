"""Review audit trail (Phase 12)

Append-only record of every human decision on a financial observation
(review / verify / reject): previous and new status, reason, declared actor,
normalized value before / after, timestamp.

Revision ID: 0006_financial_data_review_events
Revises: 0005_financial_data_explorer_indexes
"""
import sqlalchemy as sa
from alembic import op

revision = "0006_financial_data_review_events"
down_revision = "0005_financial_data_explorer_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "financial_data_review_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "financial_data_id",
            sa.String(36),
            sa.ForeignKey("financial_data.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("value_before", sa.Numeric(24, 6), nullable=True),
        sa.Column("value_after", sa.Numeric(24, 6), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("action IN ('review', 'verify', 'reject')", name="ck_review_events_action"),
    )
    op.create_index(
        "ix_review_events_data_created", "financial_data_review_events", ["financial_data_id", "created_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_review_events_data_created", table_name="financial_data_review_events")
    op.drop_table("financial_data_review_events")
