"""Expose live ingestion progress and distinguish credit lines from term loans.

Revision ID: 0025_execution_progress_boad_type
Revises: 0024_document_ocr_transcript
"""

import sqlalchemy as sa
from alembic import op

revision = "0025_execution_progress_boad_type"
down_revision = "0024_document_ocr_transcript"
branch_labels = None
depends_on = None

OLD_DEAL_TYPES = (
    "term_loan", "syndicated_loan", "project_finance", "trade_finance", "bond", "guarantee", "equity",
    "ipo", "sovereign_bond", "corporate_bond", "sukuk", "blended_finance", "m_and_a", "other",
    "sovereign_bond_ape", "corporate_bond_ape", "corporate_bond_private", "debt_buyback", "debt_exchange",
    "debt_reprofiling", "securitisation", "capital_increase", "share_sale_public", "takeover_offer",
)
NEW_DEAL_TYPES = (*OLD_DEAL_TYPES[:1], "credit_line", *OLD_DEAL_TYPES[1:])


def _in(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("sources_total", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ingestion_runs", sa.Column("current_phase", sa.String(length=40), nullable=True))
    op.add_column("ingestion_runs", sa.Column("current_source", sa.String(length=100), nullable=True))
    op.drop_constraint("ck_deals_deal_type", "deals", type_="check")
    op.create_check_constraint(
        "ck_deals_deal_type", "deals", f"deal_type IS NULL OR deal_type IN ({_in(NEW_DEAL_TYPES)})"
    )


def downgrade() -> None:
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM deals WHERE deal_type = 'credit_line'")).scalar()
    if used:
        raise RuntimeError(f"downgrade refused: {used} deal(s) use deal_type='credit_line'")
    op.drop_constraint("ck_deals_deal_type", "deals", type_="check")
    op.create_check_constraint(
        "ck_deals_deal_type", "deals", f"deal_type IS NULL OR deal_type IN ({_in(OLD_DEAL_TYPES)})"
    )
    op.drop_column("ingestion_runs", "current_source")
    op.drop_column("ingestion_runs", "current_phase")
    op.drop_column("ingestion_runs", "sources_total")
