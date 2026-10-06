"""Automatic validation (Phase 21) — reversible by a human

Additive migration, on financial_data AND deals:
- validation_method ('human' | 'automatic', NULL = no decision yet / legacy);
- auto_validation (JSONB): ruleset version, date and the result of every check;
- auto_validation_blocked: set when a human withdraws an automatic validation — the robot
  never validates that row again.
Review events: actions 'auto_validate' and 'revoke_automatic' join the closed list.

Downgrade is refused while an automatic validation or a withdrawal exists.

Revision ID: 0018_automatic_validation
Revises: 0017_directory_and_mandates
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0018_automatic_validation"
down_revision = "0017_directory_and_mandates"
branch_labels = None
depends_on = None

OLD_ACTIONS = ("review", "verify", "reject", "import", "mark_same_deal", "mark_distinct",
               "mark_same_deal_multi_source")
NEW_ACTIONS = OLD_ACTIONS + ("auto_validate", "revoke_automatic")
TABLES = ("financial_data", "deals")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("validation_method", sa.String(10), nullable=True))
        op.add_column(table, sa.Column("auto_validation", postgresql.JSONB(), nullable=True))
        op.add_column(table, sa.Column("auto_validation_blocked", sa.Boolean(), nullable=False,
                                       server_default=sa.text("false")))
        op.create_check_constraint(f"ck_{table}_validation_method", table,
                                   "validation_method IS NULL OR validation_method IN ('human', 'automatic')")
        op.create_index(f"ix_{table}_validation_method", table, ["validation_method"])
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint("ck_review_events_action", "financial_data_review_events",
                               f"action IN ({_in(NEW_ACTIONS)})")


def downgrade() -> None:
    bind = op.get_bind()
    for table in TABLES:
        used = bind.execute(sa.text(
            f"SELECT count(*) FROM {table} WHERE validation_method = 'automatic' OR auto_validation_blocked"
        )).scalar()
        if used:
            raise RuntimeError(f"downgrade of 0018 refused: {used} {table} row(s) carry an automatic validation trace")
    events = bind.execute(sa.text(
        "SELECT count(*) FROM financial_data_review_events WHERE action IN ('auto_validate', 'revoke_automatic')"
    )).scalar()
    if events:
        raise RuntimeError(f"downgrade of 0018 refused: {events} automatic validation event(s)")
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint("ck_review_events_action", "financial_data_review_events",
                               f"action IN ({_in(OLD_ACTIONS)})")
    for table in TABLES:
        op.drop_index(f"ix_{table}_validation_method", table_name=table)
        op.drop_constraint(f"ck_{table}_validation_method", table, type_="check")
        for col in ("auto_validation_blocked", "auto_validation", "validation_method"):
            op.drop_column(table, col)
