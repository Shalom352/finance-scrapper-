"""Record automatic completion of previously imported deal fields.

Revision ID: 0026_source_enrichment_events
Revises: 0025_execution_progress_boad_type
"""

import sqlalchemy as sa
from alembic import op

revision = "0026_source_enrichment_events"
down_revision = "0025_execution_progress_boad_type"
branch_labels = None
depends_on = None

OLD_ACTIONS = (
    "review", "verify", "reject", "import", "mark_same_deal", "mark_distinct",
    "mark_same_deal_multi_source", "auto_validate", "revoke_automatic",
)
NEW_ACTIONS = (*OLD_ACTIONS, "source_enrichment")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join("'" + value.replace("'", "''") + "'" for value in values)


def upgrade() -> None:
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint(
        "ck_review_events_action", "financial_data_review_events", f"action IN ({_in(NEW_ACTIONS)})"
    )


def downgrade() -> None:
    used = op.get_bind().execute(sa.text(
        "SELECT count(*) FROM financial_data_review_events WHERE action = 'source_enrichment'"
    )).scalar()
    if used:
        raise RuntimeError(f"downgrade refused: {used} source-enrichment event(s) exist")
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint(
        "ck_review_events_action", "financial_data_review_events", f"action IN ({_in(OLD_ACTIONS)})"
    )
