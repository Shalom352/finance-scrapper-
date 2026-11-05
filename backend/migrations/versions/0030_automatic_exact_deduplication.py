"""Trace automatic exact-deduplication decisions in the review journal.

Revision ID: 0030_automatic_exact_deduplication
Revises: 0029_bidc_source
"""

import sqlalchemy as sa
from alembic import op

revision = "0030_automatic_exact_deduplication"
down_revision = "0029_bidc_source"
branch_labels = None
depends_on = None

OLD_ACTIONS = (
    "review", "verify", "reject", "import", "mark_same_deal", "mark_distinct",
    "mark_same_deal_multi_source", "auto_validate", "revoke_automatic", "source_enrichment",
)
NEW_ACTIONS = (*OLD_ACTIONS, "auto_deduplicate")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def upgrade() -> None:
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint(
        "ck_review_events_action", "financial_data_review_events", f"action IN ({_in(NEW_ACTIONS)})"
    )


def downgrade() -> None:
    used = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM financial_data_review_events WHERE action = 'auto_deduplicate'"
    )).scalar()
    if used:
        raise RuntimeError(f"downgrade refused: {used} automatic deduplication event(s) exist")
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint(
        "ck_review_events_action", "financial_data_review_events", f"action IN ({_in(OLD_ACTIONS)})"
    )
