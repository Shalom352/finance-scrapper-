"""Financing directory and internal mandates (Phase 20)

Additive migration:
- entities: entity_type 'guarantee_fund' added; website (official site of the entity);
- new table mandates: TOMASTEED's own financing mandates (internal data, never published);
- new table mandate_counterparties: banks / institutions approached on a mandate and their answer
  (stage), linked to the directory only by exact identifier.

Downgrade is refused while a mandate exists, an entity is a guarantee_fund or carries a website.

Revision ID: 0017_directory_and_mandates
Revises: 0016_deal_sourcing_roles
"""

import sqlalchemy as sa
from alembic import op

revision = "0017_directory_and_mandates"
down_revision = "0016_deal_sourcing_roles"
branch_labels = None
depends_on = None

OLD_ENTITY_TYPES = (
    "commercial_bank", "central_bank", "insurance_company", "reinsurer", "development_bank", "sfd", "fintech",
    "stock_exchange", "central_depository", "sovereign_state", "company", "holding_group", "project_company", "other",
)
NEW_ENTITY_TYPES = OLD_ENTITY_TYPES + ("guarantee_fund",)
MANDATE_STATUSES = ("prospect", "active", "on_hold", "closed_won", "closed_lost")
STAGES = ("approached", "interested", "declined", "term_sheet", "committed", "disbursed", "withdrawn")
SECTORS = (
    "infrastructure_public", "energy", "agriculture", "industry", "telecom_media_tech", "real_estate",
    "financial_services", "public_finance", "other",
)


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _base_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.drop_constraint("ck_entities_entity_type", "entities", type_="check")
    op.create_check_constraint("ck_entities_entity_type", "entities", f"entity_type IN ({_in(NEW_ENTITY_TYPES)})")
    op.add_column("entities", sa.Column("website", sa.String(2048), nullable=True))

    op.create_table(
        "mandates",
        *_base_columns(),
        sa.Column("code", sa.String(50), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("country_id", sa.String(36), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sector", sa.String(40), nullable=True),
        sa.Column("deal_type", sa.String(30), nullable=True),
        sa.Column("amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("maturity_months", sa.Integer(), nullable=True),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.UniqueConstraint("code", name="uq_mandates_code"),
        sa.CheckConstraint(f"status IN ({_in(MANDATE_STATUSES)})", name="ck_mandates_status"),
        sa.CheckConstraint(f"sector IS NULL OR sector IN ({_in(SECTORS)})", name="ck_mandates_sector"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_mandates_amount_positive"),
        sa.CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_mandates_currency_iso"),
        sa.CheckConstraint("amount IS NULL OR currency IS NOT NULL", name="ck_mandates_amount_has_currency"),
        sa.CheckConstraint("maturity_months IS NULL OR maturity_months > 0", name="ck_mandates_maturity_positive"),
    )
    op.create_table(
        "mandate_counterparties",
        *_base_columns(),
        sa.Column("mandate_id", sa.String(36), sa.ForeignKey("mandates.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("counterparty_name", sa.String(255), nullable=False),
        sa.Column("institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("stage", sa.String(20), nullable=False),
        sa.Column("amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("contact_date", sa.Date(), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.CheckConstraint(f"stage IN ({_in(STAGES)})", name="ck_mandate_counterparties_stage"),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_mandate_counterparties_amount_positive"),
        sa.CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_mandate_counterparties_currency_iso"),
        sa.CheckConstraint("amount IS NULL OR currency IS NOT NULL", name="ck_mandate_counterparties_amount_has_currency"),
    )
    op.create_index("ix_mandate_counterparties_mandate", "mandate_counterparties", ["mandate_id"])
    op.create_index("ix_mandate_counterparties_institution", "mandate_counterparties", ["institution_id"])
    op.create_index("ix_mandate_counterparties_entity", "mandate_counterparties", ["entity_id"])


def downgrade() -> None:
    bind = op.get_bind()
    for label, sql in {
        "mandates": "SELECT count(*) FROM mandates",
        "entities typed guarantee_fund or carrying a website": (
            "SELECT count(*) FROM entities WHERE entity_type = 'guarantee_fund' OR website IS NOT NULL"
        ),
    }.items():
        used = bind.execute(sa.text(sql)).scalar()
        if used:
            raise RuntimeError(f"downgrade of 0017 refused: {used} {label} (dropping them would lose data)")
    for name in ("ix_mandate_counterparties_entity", "ix_mandate_counterparties_institution",
                 "ix_mandate_counterparties_mandate"):
        op.drop_index(name, table_name="mandate_counterparties")
    op.drop_table("mandate_counterparties")
    op.drop_table("mandates")
    op.drop_column("entities", "website")
    op.drop_constraint("ck_entities_entity_type", "entities", type_="check")
    op.create_check_constraint("ck_entities_entity_type", "entities", f"entity_type IN ({_in(OLD_ENTITY_TYPES)})")
