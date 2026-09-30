"""Deal Intelligence (Phase 13)

- deals, deal_sources, deal_field_sources, deal_participants, deal_duplicate_candidates;
- the Phase 12 audit journal becomes the single journal of the platform: an event targets
  EITHER a financial observation OR a deal (CHECK), new deal actions are allowed;
- financial_data.verified_by widened 100 -> 255 (same bound as the audit actor).

Non destructive: existing rows are kept untouched (all existing events target an observation).

Revision ID: 0007_deal_intelligence
Revises: 0006_financial_data_review_events
"""
import sqlalchemy as sa
from alembic import op

revision = "0007_deal_intelligence"
down_revision = "0006_financial_data_review_events"
branch_labels = None
depends_on = None

DEAL_TYPES = ("term_loan", "syndicated_loan", "project_finance", "trade_finance", "bond", "guarantee", "other")
DEAL_STATUSES = ("extracted", "needs_review", "reviewed", "verified", "rejected")
ROLES = ("borrower", "lender", "arranger", "co_arranger", "agent", "guarantor", "sponsor", "advisor", "investor")
DUPLICATE_STATES = ("duplicate_candidate", "same_deal", "distinct_deals", "same_deal_multi_source")
PROVENANCE_FIELDS = (
    "title", "deal_type", "country_code", "sector", "project_name", "amount", "amount_original", "currency",
    "unit", "interest_rate", "interest_rate_type", "benchmark", "spread_bps", "maturity_months",
    "grace_period_months", "fees", "guarantees", "announcement_date", "signing_date", "financial_close_date",
    "closing_date",
)
OLD_ACTIONS = ("review", "verify", "reject")
NEW_ACTIONS = OLD_ACTIONS + ("import", "mark_same_deal", "mark_distinct", "mark_same_deal_multi_source")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "deals",
        *_audit_columns(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("deal_type", sa.String(30), nullable=True),
        sa.Column("country_id", sa.String(36), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("sector", sa.String(100), nullable=True),
        sa.Column("project_name", sa.Text(), nullable=True),
        sa.Column("amount_original", sa.Text(), nullable=True),
        sa.Column("amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("currency", sa.String(3), nullable=True),
        sa.Column("unit", sa.String(20), nullable=True),
        sa.Column("interest_rate", sa.Numeric(9, 4), nullable=True),
        sa.Column("interest_rate_type", sa.String(20), nullable=True),
        sa.Column("benchmark", sa.String(50), nullable=True),
        sa.Column("spread_bps", sa.Numeric(9, 2), nullable=True),
        sa.Column("maturity_months", sa.Integer(), nullable=True),
        sa.Column("grace_period_months", sa.Integer(), nullable=True),
        sa.Column("fees", sa.Text(), nullable=True),
        sa.Column("guarantees", sa.Text(), nullable=True),
        sa.Column("announcement_date", sa.Date(), nullable=True),
        sa.Column("signing_date", sa.Date(), nullable=True),
        sa.Column("financial_close_date", sa.Date(), nullable=True),
        sa.Column("closing_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(255), nullable=True),
        sa.Column("merged_into_deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True),
        sa.CheckConstraint(f"deal_type IS NULL OR deal_type IN ({_in(DEAL_TYPES)})", name="ck_deals_deal_type"),
        sa.CheckConstraint(f"status IN ({_in(DEAL_STATUSES)})", name="ck_deals_status"),
        sa.CheckConstraint(
            "interest_rate_type IS NULL OR interest_rate_type IN ('fixed', 'floating')",
            name="ck_deals_interest_rate_type",
        ),
        sa.CheckConstraint("amount IS NULL OR amount > 0", name="ck_deals_amount_positive"),
        sa.CheckConstraint("currency IS NULL OR currency ~ '^[A-Z]{3}$'", name="ck_deals_currency_iso"),
        sa.CheckConstraint("maturity_months IS NULL OR maturity_months > 0", name="ck_deals_maturity_positive"),
        sa.CheckConstraint(
            "grace_period_months IS NULL OR grace_period_months >= 0", name="ck_deals_grace_non_negative"
        ),
        sa.CheckConstraint(
            "status != 'verified' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_deals_verified_requires_validator",
        ),
        sa.CheckConstraint(
            "merged_into_deal_id IS NULL OR merged_into_deal_id != id", name="ck_deals_not_merged_into_itself"
        ),
    )
    op.create_index("ix_deals_status", "deals", ["status"])
    op.create_index("ix_deals_country_signing", "deals", ["country_id", "signing_date"])
    op.create_index("ix_deals_deal_type", "deals", ["deal_type"])
    op.create_index("ix_deals_currency", "deals", ["currency"])
    op.create_index("ix_deals_merged_into", "deals", ["merged_into_deal_id"])

    op.create_table(
        "deal_sources",
        *_audit_columns(),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=True),
        sa.CheckConstraint("page_number > 0", name="ck_deal_sources_page_positive"),
        sa.UniqueConstraint("deal_id", "document_id", "page_number", name="uq_deal_sources_deal_document_page"),
    )
    op.create_index("ix_deal_sources_deal", "deal_sources", ["deal_id"])
    op.create_index("ix_deal_sources_document", "deal_sources", ["document_id"])

    op.create_table(
        "deal_field_sources",
        *_audit_columns(),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("field_name", sa.String(40), nullable=False),
        sa.Column(
            "deal_source_id", sa.String(36), sa.ForeignKey("deal_sources.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.CheckConstraint(f"field_name IN ({_in(PROVENANCE_FIELDS)})", name="ck_deal_field_sources_field"),
        sa.UniqueConstraint("deal_id", "field_name", "deal_source_id", name="uq_deal_field_sources"),
    )
    op.create_index("ix_deal_field_sources_deal", "deal_field_sources", ["deal_id"])

    op.create_table(
        "deal_participants",
        *_audit_columns(),
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("participant_name", sa.String(255), nullable=False),
        sa.Column(
            "institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="RESTRICT"), nullable=True
        ),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("commitment_amount", sa.Numeric(24, 6), nullable=True),
        sa.Column("commitment_currency", sa.String(3), nullable=True),
        sa.Column(
            "deal_source_id", sa.String(36), sa.ForeignKey("deal_sources.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.CheckConstraint(f"role IN ({_in(ROLES)})", name="ck_deal_participants_role"),
        sa.CheckConstraint(
            "commitment_amount IS NULL OR commitment_amount > 0", name="ck_deal_participants_commitment_positive"
        ),
        sa.CheckConstraint(
            "commitment_currency IS NULL OR commitment_currency ~ '^[A-Z]{3}$'",
            name="ck_deal_participants_currency_iso",
        ),
    )
    op.create_index("ix_deal_participants_deal", "deal_participants", ["deal_id"])
    op.create_index("ix_deal_participants_institution_role", "deal_participants", ["institution_id", "role"])

    op.create_table(
        "deal_duplicate_candidates",
        *_audit_columns(),
        sa.Column("deal_a_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("deal_b_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("matched_criteria", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("primary_deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.CheckConstraint("deal_a_id < deal_b_id", name="ck_deal_duplicates_ordered_pair"),
        sa.CheckConstraint(f"state IN ({_in(DUPLICATE_STATES)})", name="ck_deal_duplicates_state"),
        sa.CheckConstraint(
            "state = 'duplicate_candidate' OR (decided_by IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_deal_duplicates_decision_traced",
        ),
        sa.UniqueConstraint("deal_a_id", "deal_b_id", name="uq_deal_duplicates_pair"),
    )
    op.create_index("ix_deal_duplicates_state", "deal_duplicate_candidates", ["state"])

    # --- Single audit journal: observations OR deals ---
    op.add_column(
        "financial_data_review_events",
        sa.Column("deal_id", sa.String(36), sa.ForeignKey("deals.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "financial_data_review_events",
        sa.Column(
            "deal_duplicate_candidate_id",
            sa.String(36),
            sa.ForeignKey("deal_duplicate_candidates.id", ondelete="RESTRICT"),
            nullable=True,
        ),
    )
    op.alter_column("financial_data_review_events", "financial_data_id", existing_type=sa.String(36), nullable=True)
    op.alter_column(
        "financial_data_review_events", "action", existing_type=sa.String(20), type_=sa.String(30)
    )
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint("ck_review_events_action", "financial_data_review_events",
                               f"action IN ({_in(NEW_ACTIONS)})")
    op.create_check_constraint(
        "ck_review_events_single_target",
        "financial_data_review_events",
        "(financial_data_id IS NOT NULL AND deal_id IS NULL) OR (financial_data_id IS NULL AND deal_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_review_events_candidate_on_deal",
        "financial_data_review_events",
        "deal_duplicate_candidate_id IS NULL OR deal_id IS NOT NULL",
    )
    op.create_index("ix_review_events_deal_created", "financial_data_review_events", ["deal_id", "created_at"])

    op.alter_column("financial_data", "verified_by", existing_type=sa.String(100), type_=sa.String(255))


def downgrade() -> None:
    # Refuse to silently destroy deal audit events: the downgrade only works while the
    # journal holds observation events exclusively (deal tables are dropped below).
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM financial_data_review_events WHERE deal_id IS NOT NULL) "
        "THEN RAISE EXCEPTION 'downgrade refused: deal audit events exist'; END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM financial_data WHERE length(verified_by) > 100) "
        "THEN RAISE EXCEPTION 'downgrade refused: verified_by longer than 100 characters'; END IF; END $$;"
    )
    op.alter_column("financial_data", "verified_by", existing_type=sa.String(255), type_=sa.String(100))

    op.drop_index("ix_review_events_deal_created", table_name="financial_data_review_events")
    op.drop_constraint("ck_review_events_candidate_on_deal", "financial_data_review_events", type_="check")
    op.drop_constraint("ck_review_events_single_target", "financial_data_review_events", type_="check")
    op.drop_constraint("ck_review_events_action", "financial_data_review_events", type_="check")
    op.create_check_constraint("ck_review_events_action", "financial_data_review_events",
                               f"action IN ({_in(OLD_ACTIONS)})")
    op.alter_column(
        "financial_data_review_events", "action", existing_type=sa.String(30), type_=sa.String(20)
    )
    op.alter_column("financial_data_review_events", "financial_data_id", existing_type=sa.String(36), nullable=False)
    op.drop_column("financial_data_review_events", "deal_duplicate_candidate_id")
    op.drop_column("financial_data_review_events", "deal_id")

    op.drop_index("ix_deal_duplicates_state", table_name="deal_duplicate_candidates")
    op.drop_table("deal_duplicate_candidates")
    op.drop_index("ix_deal_participants_institution_role", table_name="deal_participants")
    op.drop_index("ix_deal_participants_deal", table_name="deal_participants")
    op.drop_table("deal_participants")
    op.drop_index("ix_deal_field_sources_deal", table_name="deal_field_sources")
    op.drop_table("deal_field_sources")
    op.drop_index("ix_deal_sources_document", table_name="deal_sources")
    op.drop_index("ix_deal_sources_deal", table_name="deal_sources")
    op.drop_table("deal_sources")
    for name in ("ix_deals_merged_into", "ix_deals_currency", "ix_deals_deal_type", "ix_deals_country_signing",
                 "ix_deals_status"):
        op.drop_index(name, table_name="deals")
    op.drop_table("deals")
