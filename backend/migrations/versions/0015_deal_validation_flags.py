"""Deal validation flags

Additive migration: deals.validation_flags (JSONB list of {code, detail}, NULL when none) records
the validation rules an automated ingestion applied to a deal (e.g. a rounded printed total, a
truncated issuer label confirmed by the ISIN). A flag never changes a value or a status.

Downgrade is refused while a deal carries a flag (dropping the column would lose that trace).

Revision ID: 0015_deal_validation_flags
Revises: 0014_public_debt_instruments
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015_deal_validation_flags"
down_revision = "0014_public_debt_instruments"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deals", sa.Column("validation_flags", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM deals WHERE validation_flags IS NOT NULL")).scalar_one()
    if used:
        raise RuntimeError(f"downgrade of 0015 refused: {used} deal(s) carry validation flags")
    op.drop_column("deals", "validation_flags")
