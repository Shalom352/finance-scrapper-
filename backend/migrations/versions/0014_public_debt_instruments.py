"""Public-debt instruments in Deal Intelligence (UMOA-Titres auctions)

Additive migration:
- deals: instrument_type (OAT | BAT), isin, auction_reference, auction_date, value_date,
  maturity_date, yield_rate, ingestion_key (deterministic idempotence key, unique among
  non-deleted deals);
- deal_participants: entity_id (Entity Hub link, e.g. one of the 8 sovereign_state entities);
- deal_field_sources: the new fields join the field-level provenance vocabulary.

Every new column is NULL for existing deals: Phase 13 deals keep working unchanged.

Downgrade is refused while a deal or participant uses the new columns: dropping them would
silently lose published data (nothing is ever deleted to make a downgrade pass).

Revision ID: 0014_public_debt_instruments
Revises: 0013_institutional_discovery
"""

import sqlalchemy as sa
from alembic import op

revision = "0014_public_debt_instruments"
down_revision = "0013_institutional_discovery"
branch_labels = None
depends_on = None

LEGACY_FIELDS = (
    "title", "deal_type", "country_code", "sector", "project_name", "amount", "amount_original", "currency",
    "unit", "interest_rate", "interest_rate_type", "benchmark", "spread_bps", "maturity_months",
    "grace_period_months", "fees", "guarantees", "announcement_date", "signing_date", "financial_close_date",
    "closing_date",
)
INSTRUMENT_FIELDS = (
    "instrument_type", "isin", "auction_reference", "auction_date", "value_date", "maturity_date", "yield_rate",
)
INSTRUMENT_TYPES = ("OAT", "BAT")
NEW_DEAL_COLUMNS = (*INSTRUMENT_FIELDS, "ingestion_key")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.add_column("deals", sa.Column("instrument_type", sa.String(10), nullable=True))
    op.add_column("deals", sa.Column("isin", sa.String(12), nullable=True))
    op.add_column("deals", sa.Column("auction_reference", sa.String(100), nullable=True))
    op.add_column("deals", sa.Column("auction_date", sa.Date(), nullable=True))
    op.add_column("deals", sa.Column("value_date", sa.Date(), nullable=True))
    op.add_column("deals", sa.Column("maturity_date", sa.Date(), nullable=True))
    op.add_column("deals", sa.Column("yield_rate", sa.Numeric(9, 4), nullable=True))
    op.add_column("deals", sa.Column("ingestion_key", sa.String(255), nullable=True))
    op.create_check_constraint(
        "ck_deals_instrument_type", "deals", f"instrument_type IS NULL OR instrument_type IN ({_in(INSTRUMENT_TYPES)})"
    )
    op.create_check_constraint("ck_deals_isin_format", "deals", "isin IS NULL OR isin ~ '^[A-Z]{2}[A-Z0-9]{9}[0-9]$'")
    op.create_check_constraint(
        "ck_deals_maturity_after_value_date", "deals",
        "maturity_date IS NULL OR value_date IS NULL OR maturity_date > value_date",
    )
    op.create_index("ix_deals_isin", "deals", ["isin"])
    op.create_index("ix_deals_auction_reference", "deals", ["auction_reference"])
    op.create_index("ix_deals_value_date", "deals", ["value_date"])
    op.create_index(
        "uq_deals_ingestion_key", "deals", ["ingestion_key"], unique=True,
        postgresql_where=sa.text("ingestion_key IS NOT NULL AND deleted_at IS NULL"),
    )

    op.add_column(
        "deal_participants",
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_index("ix_deal_participants_entity_role", "deal_participants", ["entity_id", "role"])

    op.drop_constraint("ck_deal_field_sources_field", "deal_field_sources", type_="check")
    op.create_check_constraint(
        "ck_deal_field_sources_field", "deal_field_sources",
        f"field_name IN ({_in(LEGACY_FIELDS + INSTRUMENT_FIELDS)})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM deals WHERE " + " OR ".join(f"{c} IS NOT NULL" for c in NEW_DEAL_COLUMNS)
        + ") + (SELECT count(*) FROM deal_participants WHERE entity_id IS NOT NULL)"
        + f" + (SELECT count(*) FROM deal_field_sources WHERE field_name IN ({_in(INSTRUMENT_FIELDS)}))"
    )).scalar_one()
    if used:
        raise RuntimeError(
            f"downgrade of 0014 refused: {used} row(s) use public-debt instrument fields; "
            "dropping them would lose published data"
        )
    op.drop_constraint("ck_deal_field_sources_field", "deal_field_sources", type_="check")
    op.create_check_constraint(
        "ck_deal_field_sources_field", "deal_field_sources", f"field_name IN ({_in(LEGACY_FIELDS)})"
    )
    op.drop_index("ix_deal_participants_entity_role", table_name="deal_participants")
    op.drop_column("deal_participants", "entity_id")
    op.drop_index("uq_deals_ingestion_key", table_name="deals")
    for name in ("ix_deals_value_date", "ix_deals_auction_reference", "ix_deals_isin"):
        op.drop_index(name, table_name="deals")
    for name in ("ck_deals_maturity_after_value_date", "ck_deals_isin_format", "ck_deals_instrument_type"):
        op.drop_constraint(name, "deals", type_="check")
    for column in reversed(NEW_DEAL_COLUMNS):
        op.drop_column("deals", column)
