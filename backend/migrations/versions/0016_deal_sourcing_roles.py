"""Deal sourcing: closed taxonomy, named roles, use of proceeds, source classes, SGI -> bank links

Phase 19 — implements the decisions D1-D5 validated on 05/10/2026
(audits/ape_amf/07_proposition.md). Additive migration:
- deals: deal types extended (sovereign_bond_ape, corporate_bond_ape, ... takeover_offer);
  use_of_proceeds (quoted text), use_of_proceeds_categories (JSONB list, closed vocabulary),
  filing_agent_raw ("SGI déclarante" as given by the AMF API — never a role, D2);
- deal_participants: roles extended (lead_manager, co_lead_manager, ...); role widened to 40 chars;
  page_number, excerpt, extraction_method (text | visual_logo | visual_scan);
- deal_sources: source_class (primary_regulatory ... press_reported), publisher, title, url,
  published_at, paywalled (press metadata only: an article body is never stored, D4);
- deal_field_sources: the three new deal fields join the provenance vocabulary;
- new table institution_links (SGI -> bank at two levels, D3).

Every new column is NULL for existing rows. Downgrade is refused while a row uses the new
vocabulary or columns (nothing is ever deleted to make a downgrade pass).

Revision ID: 0016_deal_sourcing_roles
Revises: 0015_deal_validation_flags
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0016_deal_sourcing_roles"
down_revision = "0015_deal_validation_flags"
branch_labels = None
depends_on = None

OLD_DEAL_TYPES = (
    "term_loan", "syndicated_loan", "project_finance", "trade_finance", "bond", "guarantee", "equity", "ipo",
    "sovereign_bond", "corporate_bond", "sukuk", "blended_finance", "m_and_a", "other",
)
NEW_DEAL_TYPES = OLD_DEAL_TYPES + (
    "sovereign_bond_ape", "corporate_bond_ape", "corporate_bond_private", "debt_buyback", "debt_exchange",
    "debt_reprofiling", "securitisation", "capital_increase", "share_sale_public", "takeover_offer",
)
OLD_ROLES = (
    "borrower", "lender", "arranger", "co_arranger", "agent", "guarantor", "sponsor", "advisor", "investor",
    "insurer", "reinsurer", "issuer", "underwriter", "trustee", "facility_agent", "security_agent",
)
NEW_ROLES = OLD_ROLES + (
    "lead_manager", "co_lead_manager", "placement_syndicate_member", "financial_advisor", "anchor_investor",
    "refinanced_lender", "selling_shareholder", "paying_agent",
)
OLD_FIELDS = (
    "title", "deal_type", "country_code", "sector", "project_name", "amount", "amount_original", "currency",
    "unit", "interest_rate", "interest_rate_type", "benchmark", "spread_bps", "maturity_months",
    "grace_period_months", "fees", "guarantees", "announcement_date", "signing_date", "financial_close_date",
    "closing_date", "instrument_type", "isin", "auction_reference", "auction_date", "value_date",
    "maturity_date", "yield_rate",
)
NEW_FIELDS = OLD_FIELDS + ("use_of_proceeds", "use_of_proceeds_categories", "filing_agent_raw")
EXTRACTION_METHODS = ("text", "visual_logo", "visual_scan")
SOURCE_CLASSES = (
    "primary_regulatory", "primary_market", "issuer_official", "issuer_press_release", "regulator_index",
    "press_reported",
)
LINK_LEVELS = ("documented_bank", "documented_group_only")
LINK_RELATIONS = ("subsidiary", "shareholder")
LINK_STATUSES = ("needs_review", "reviewed", "verified", "rejected")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _replace_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    _replace_check("ck_deals_deal_type", "deals", f"deal_type IS NULL OR deal_type IN ({_in(NEW_DEAL_TYPES)})")
    op.add_column("deals", sa.Column("use_of_proceeds", sa.Text(), nullable=True))
    op.add_column("deals", sa.Column("use_of_proceeds_categories", postgresql.JSONB(), nullable=True))
    op.add_column("deals", sa.Column("filing_agent_raw", sa.String(255), nullable=True))

    op.alter_column("deal_participants", "role", type_=sa.String(40), existing_type=sa.String(20),
                    existing_nullable=False)
    _replace_check("ck_deal_participants_role", "deal_participants", f"role IN ({_in(NEW_ROLES)})")
    op.add_column("deal_participants", sa.Column("page_number", sa.Integer(), nullable=True))
    op.add_column("deal_participants", sa.Column("excerpt", sa.Text(), nullable=True))
    op.add_column("deal_participants", sa.Column("extraction_method", sa.String(20), nullable=True))
    op.create_check_constraint("ck_deal_participants_page_positive", "deal_participants",
                               "page_number IS NULL OR page_number > 0")
    op.create_check_constraint("ck_deal_participants_extraction_method", "deal_participants",
                               f"extraction_method IS NULL OR extraction_method IN ({_in(EXTRACTION_METHODS)})")

    op.add_column("deal_sources", sa.Column("source_class", sa.String(30), nullable=True))
    op.add_column("deal_sources", sa.Column("publisher", sa.String(255), nullable=True))
    op.add_column("deal_sources", sa.Column("title", sa.Text(), nullable=True))
    op.add_column("deal_sources", sa.Column("url", sa.Text(), nullable=True))
    op.add_column("deal_sources", sa.Column("published_at", sa.Date(), nullable=True))
    op.add_column("deal_sources", sa.Column("paywalled", sa.Boolean(), nullable=True))
    op.create_check_constraint("ck_deal_sources_source_class", "deal_sources",
                               f"source_class IS NULL OR source_class IN ({_in(SOURCE_CLASSES)})")
    op.create_index("ix_deal_sources_source_class", "deal_sources", ["source_class"])

    _replace_check("ck_deal_field_sources_field", "deal_field_sources", f"field_name IN ({_in(NEW_FIELDS)})")

    op.create_table(
        "institution_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_name", sa.String(255), nullable=False),
        sa.Column("from_entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("link_level", sa.String(30), nullable=False),
        sa.Column("to_institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("group_label", sa.String(255), nullable=True),
        sa.Column("relation", sa.String(20), nullable=False),
        sa.Column("pct", sa.Numeric(7, 4), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("excerpt", sa.Text(), nullable=False),
        sa.Column("observed_at", sa.Date(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="needs_review"),
        sa.Column("verified_by", sa.String(255), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"link_level IN ({_in(LINK_LEVELS)})", name="ck_institution_links_level"),
        sa.CheckConstraint(f"relation IN ({_in(LINK_RELATIONS)})", name="ck_institution_links_relation"),
        sa.CheckConstraint(f"status IN ({_in(LINK_STATUSES)})", name="ck_institution_links_status"),
        sa.CheckConstraint(
            "(link_level = 'documented_bank' AND to_institution_id IS NOT NULL AND group_label IS NULL) OR "
            "(link_level = 'documented_group_only' AND to_institution_id IS NULL AND group_label IS NOT NULL)",
            name="ck_institution_links_level_target",
        ),
        sa.CheckConstraint("pct IS NULL OR (pct > 0 AND pct <= 100)", name="ck_institution_links_pct"),
        sa.CheckConstraint(
            "status != 'verified' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_institution_links_verified_requires_validator",
        ),
    )
    op.create_index("ix_institution_links_from_name", "institution_links", ["from_name"])
    op.create_index("ix_institution_links_to_institution", "institution_links", ["to_institution_id"])


def downgrade() -> None:
    bind = op.get_bind()
    checks = {
        "deals using the new types or columns": (
            f"SELECT count(*) FROM deals WHERE deal_type NOT IN ({_in(OLD_DEAL_TYPES)}) "
            "OR use_of_proceeds IS NOT NULL OR use_of_proceeds_categories IS NOT NULL "
            "OR filing_agent_raw IS NOT NULL"
        ),
        "participants using the new roles or columns": (
            f"SELECT count(*) FROM deal_participants WHERE role NOT IN ({_in(OLD_ROLES)}) "
            "OR page_number IS NOT NULL OR excerpt IS NOT NULL OR extraction_method IS NOT NULL"
        ),
        "deal sources carrying a class or press metadata": (
            "SELECT count(*) FROM deal_sources WHERE source_class IS NOT NULL OR publisher IS NOT NULL "
            "OR title IS NOT NULL OR url IS NOT NULL OR published_at IS NOT NULL OR paywalled IS NOT NULL"
        ),
        "institution links": "SELECT count(*) FROM institution_links",
    }
    for label, sql in checks.items():
        used = bind.execute(sa.text(sql)).scalar()
        if used:
            raise RuntimeError(f"downgrade of 0016 refused: {used} {label} (dropping them would lose data)")
    op.drop_index("ix_institution_links_to_institution", table_name="institution_links")
    op.drop_index("ix_institution_links_from_name", table_name="institution_links")
    op.drop_table("institution_links")
    _replace_check("ck_deal_field_sources_field", "deal_field_sources", f"field_name IN ({_in(OLD_FIELDS)})")
    op.drop_index("ix_deal_sources_source_class", table_name="deal_sources")
    op.drop_constraint("ck_deal_sources_source_class", "deal_sources", type_="check")
    for col in ("paywalled", "published_at", "url", "title", "publisher", "source_class"):
        op.drop_column("deal_sources", col)
    op.drop_constraint("ck_deal_participants_extraction_method", "deal_participants", type_="check")
    op.drop_constraint("ck_deal_participants_page_positive", "deal_participants", type_="check")
    for col in ("extraction_method", "excerpt", "page_number"):
        op.drop_column("deal_participants", col)
    _replace_check("ck_deal_participants_role", "deal_participants", f"role IN ({_in(OLD_ROLES)})")
    op.alter_column("deal_participants", "role", type_=sa.String(20), existing_type=sa.String(40),
                    existing_nullable=False)
    for col in ("filing_agent_raw", "use_of_proceeds_categories", "use_of_proceeds"):
        op.drop_column("deals", col)
    _replace_check("ck_deals_deal_type", "deals", f"deal_type IS NULL OR deal_type IN ({_in(OLD_DEAL_TYPES)})")
