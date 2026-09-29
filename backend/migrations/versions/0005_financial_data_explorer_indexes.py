"""Financial data explorer indexes (Phase 11)

- (period_type, scope, period_year): the explorer always filters one period type and one scope;
- logical key (institution, metric, year, period_type, scope): sibling lookup for row qualification;
- (currency_normalized, value_normalized): currency filter and the value sort grouped by currency.

Revision ID: 0005_financial_data_explorer_indexes
Revises: 0004_seed_official_sources
"""
from alembic import op

revision = "0005_financial_data_explorer_indexes"
down_revision = "0004_seed_official_sources"
branch_labels = None
depends_on = None

INDEXES = {
    "ix_financial_data_period_scope_year": ["period_type", "scope", "period_year"],
    "ix_financial_data_logical_key": ["institution_id", "metric_code", "period_year", "period_type", "scope"],
    "ix_financial_data_currency_value": ["currency_normalized", "value_normalized"],
}


def upgrade() -> None:
    for name, columns in INDEXES.items():
        op.create_index(name, "financial_data", columns)


def downgrade() -> None:
    for name in reversed(INDEXES):
        op.drop_index(name, table_name="financial_data")
