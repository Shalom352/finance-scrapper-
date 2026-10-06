"""Unified Financial Intelligence (Phase 14 — Step 1 Socle Structurel)

- Tables `entities` and `entity_relationships`;
- Foreign key `institutions.entity_id` -> `entities.id`;
- Columns `financial_data.entity_id`, `financial_data.observation_level`, `financial_data.consolidation_scope`;
- Columns `metric_definitions.sector`, `metric_definitions.metric_family`;
- Updated CHECK constraints for institutions, sources, deals, and deal participants;
- Deterministic data backfill for existing institutions, financial_data, and metric_definitions;
- Strict zero-regression and non-destructive downgrade.

Revision ID: 0009_unified_financial_intelligence
Revises: 0008_automated_ingestion
"""

import sqlalchemy as sa
from alembic import op

revision = "0009_unified_financial_intelligence"
down_revision = "0008_automated_ingestion"
branch_labels = None
depends_on = None

ENTITY_CLASSES = (
    "financial_institution",
    "regulator",
    "market_infrastructure",
    "sovereign_entity",
    "corporate",
    "project_spv",
    "macro_region",
)
ENTITY_TYPES = (
    "commercial_bank",
    "central_bank",
    "insurance_company",
    "reinsurer",
    "development_bank",
    "sfd",
    "fintech",
    "stock_exchange",
    "central_depository",
    "sovereign_state",
    "company",
    "holding_group",
    "project_company",
    "other",
)
ENTITY_STATUSES = (
    "active",
    "inactive",
    "under_resolution",
    "liquidated",
    "merged",
    "unknown",
)
RELATIONSHIP_TYPES = (
    "owns_equity",
    "controls_subsidiary",
    "holding_of",
    "branch_of",
    "finances_project",
    "syndicates_loan",
    "insures_asset",
    "reinsures_portfolio",
    "guarantees_debt",
    "listed_on_exchange",
    "cleared_by_depository",
    "supervises",
    "operates_in",
    "other",
)
OBSERVATION_LEVELS = (
    "entity",
    "group",
    "country",
    "regional",
    "market",
    "project",
    "deal",
)
CONSOLIDATION_SCOPES = (
    "individual",
    "consolidated",
    "not_applicable",
)
SECTORS = (
    "banking",
    "insurance",
    "markets",
    "sovereign",
    "microfinance",
    "corporate",
    "macro",
    "cross_sector",
)
METRIC_FAMILIES = (
    "balance_sheet",
    "income_statement",
    "prudential",
    "market_data",
    "debt_service",
    "claims_underwriting",
    "operational",
    "solvency",
    "other",
)

OLD_INSTITUTION_TYPES = ("bank", "microfinance", "insurance", "financial_holding", "development_bank", "other")
NEW_INSTITUTION_TYPES = OLD_INSTITUTION_TYPES + ("reinsurance", "fintech")

OLD_SOURCE_TYPES = (
    "regulatory",
    "central_bank",
    "bank",
    "banking_group",
    "government",
    "financial_market",
    "secondary",
)
NEW_SOURCE_TYPES = OLD_SOURCE_TYPES + (
    "development_institution",
    "insurance_supervisor",
    "market_authority",
    "regional_body",
    "other",
)

OLD_DEAL_TYPES = ("term_loan", "syndicated_loan", "project_finance", "trade_finance", "bond", "guarantee", "other")
NEW_DEAL_TYPES = (
    "term_loan",
    "syndicated_loan",
    "project_finance",
    "trade_finance",
    "bond",
    "guarantee",
    "equity",
    "ipo",
    "sovereign_bond",
    "corporate_bond",
    "sukuk",
    "blended_finance",
    "m_and_a",
    "other",
)

OLD_ROLES = ("borrower", "lender", "arranger", "co_arranger", "agent", "guarantor", "sponsor", "advisor", "investor")
NEW_ROLES = (
    "borrower",
    "lender",
    "arranger",
    "co_arranger",
    "agent",
    "guarantor",
    "sponsor",
    "advisor",
    "investor",
    "insurer",
    "reinsurer",
    "issuer",
    "underwriter",
    "trustee",
    "facility_agent",
    "security_agent",
)


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
    # 1. Create table `entities`
    op.create_table(
        "entities",
        *_audit_columns(),
        sa.Column("entity_class", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("canonical_name", sa.String(255), nullable=False),
        sa.Column("short_name", sa.String(50), nullable=True),
        sa.Column("country_id", sa.String(36), sa.ForeignKey("countries.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="active"),
        sa.CheckConstraint(f"entity_class IN ({_in(ENTITY_CLASSES)})", name="ck_entities_entity_class"),
        sa.CheckConstraint(f"entity_type IN ({_in(ENTITY_TYPES)})", name="ck_entities_entity_type"),
        sa.CheckConstraint(f"status IN ({_in(ENTITY_STATUSES)})", name="ck_entities_status"),
    )
    op.create_index("ix_entities_canonical_name", "entities", ["canonical_name"])
    op.create_index("ix_entities_entity_class", "entities", ["entity_class"])
    op.create_index("ix_entities_entity_type", "entities", ["entity_type"])
    op.create_index("ix_entities_country_id", "entities", ["country_id"])
    op.create_index("ix_entities_status", "entities", ["status"])

    # 2. Create table `entity_relationships`
    op.create_table(
        "entity_relationships",
        *_audit_columns(),
        sa.Column("source_entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("target_entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("relationship_type", sa.String(50), nullable=False),
        sa.Column("role_context", sa.String(50), nullable=True),
        sa.Column("ownership_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("voting_rights_percentage", sa.Numeric(5, 2), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("source_id", sa.String(36), sa.ForeignKey("sources.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Numeric(4, 3), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint("source_entity_id != target_entity_id", name="ck_entity_relationships_no_self_ref"),
        sa.CheckConstraint(f"relationship_type IN ({_in(RELATIONSHIP_TYPES)})", name="ck_entity_relationships_type"),
        sa.CheckConstraint(
            "ownership_percentage IS NULL OR (ownership_percentage >= 0 AND ownership_percentage <= 100)",
            name="ck_entity_relationships_ownership_pct",
        ),
        sa.CheckConstraint(
            "voting_rights_percentage IS NULL OR (voting_rights_percentage >= 0 AND voting_rights_percentage <= 100)",
            name="ck_entity_relationships_voting_pct",
        ),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from",
            name="ck_entity_relationships_dates",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_entity_relationships_page_positive",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_entity_relationships_confidence",
        ),
    )
    op.create_index("ix_entity_relationships_source", "entity_relationships", ["source_entity_id"])
    op.create_index("ix_entity_relationships_target", "entity_relationships", ["target_entity_id"])
    op.create_index("ix_entity_relationships_type", "entity_relationships", ["relationship_type"])
    op.create_index("ix_entity_relationships_is_current", "entity_relationships", ["is_current"])

    # 3. Add `entity_id` to `institutions`
    op.add_column(
        "institutions",
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
    )
    op.create_unique_constraint("uq_institutions_entity_id", "institutions", ["entity_id"])
    op.create_index("ix_institutions_entity_id", "institutions", ["entity_id"])

    # 4. Add `sector` and `metric_family` to `metric_definitions`
    op.add_column(
        "metric_definitions",
        sa.Column("sector", sa.String(50), nullable=False, server_default="banking"),
    )
    op.add_column(
        "metric_definitions",
        sa.Column("metric_family", sa.String(50), nullable=False, server_default="balance_sheet"),
    )
    op.create_check_constraint(
        "ck_metric_definitions_sector", "metric_definitions", f"sector IN ({_in(SECTORS)})"
    )
    op.create_check_constraint(
        "ck_metric_definitions_metric_family",
        "metric_definitions",
        f"metric_family IN ({_in(METRIC_FAMILIES)})",
    )
    op.create_index("ix_metric_definitions_sector", "metric_definitions", ["sector"])
    op.create_index("ix_metric_definitions_metric_family", "metric_definitions", ["metric_family"])

    # 5. Decouple `financial_data` target (institution_id nullable, entity_id FK, observation_level, consolidation_scope)
    op.alter_column("financial_data", "institution_id", existing_type=sa.String(36), nullable=True)
    op.add_column(
        "financial_data",
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
    )
    op.add_column(
        "financial_data",
        sa.Column("observation_level", sa.String(30), nullable=False, server_default="entity"),
    )
    op.add_column(
        "financial_data",
        sa.Column("consolidation_scope", sa.String(30), nullable=False, server_default="individual"),
    )
    op.create_check_constraint(
        "ck_financial_data_target",
        "financial_data",
        "institution_id IS NOT NULL OR entity_id IS NOT NULL",
    )
    op.create_check_constraint(
        "ck_financial_data_observation_level",
        "financial_data",
        f"observation_level IN ({_in(OBSERVATION_LEVELS)})",
    )
    op.create_check_constraint(
        "ck_financial_data_consolidation_scope",
        "financial_data",
        f"consolidation_scope IN ({_in(CONSOLIDATION_SCOPES)})",
    )
    op.create_index("ix_financial_data_entity_id", "financial_data", ["entity_id"])
    op.create_index("ix_financial_data_observation_level", "financial_data", ["observation_level"])
    op.create_index("ix_financial_data_consolidation_scope", "financial_data", ["consolidation_scope"])

    # 6. Update existing CHECK constraints for cross-sector compatibility
    op.drop_constraint("ck_institutions_institution_type", "institutions", type_="check")
    op.create_check_constraint(
        "ck_institutions_institution_type",
        "institutions",
        f"institution_type IN ({_in(NEW_INSTITUTION_TYPES)})",
    )

    op.drop_constraint("ck_sources_source_type", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_source_type",
        "sources",
        f"source_type IN ({_in(NEW_SOURCE_TYPES)})",
    )

    op.drop_constraint("ck_deals_deal_type", "deals", type_="check")
    op.create_check_constraint(
        "ck_deals_deal_type",
        "deals",
        f"deal_type IS NULL OR deal_type IN ({_in(NEW_DEAL_TYPES)})",
    )

    op.drop_constraint("ck_deal_participants_role", "deal_participants", type_="check")
    op.create_check_constraint(
        "ck_deal_participants_role",
        "deal_participants",
        f"role IN ({_in(NEW_ROLES)})",
    )

    # 7. Deterministic Data Backfill (compatible with both live DB and offline DDL generation)
    op.execute(
        """
        INSERT INTO entities (
            id, created_at, updated_at, deleted_at,
            entity_class, entity_type, canonical_name,
            short_name, country_id, status, description
        )
        SELECT
            institutions.id,
            institutions.created_at,
            institutions.updated_at,
            institutions.deleted_at,
            'financial_institution',
            CASE
                WHEN institutions.institution_type = 'microfinance' THEN 'sfd'
                WHEN institutions.institution_type = 'insurance' THEN 'insurance_company'
                WHEN institutions.institution_type = 'development_bank' THEN 'development_bank'
                WHEN institutions.institution_type = 'financial_holding' THEN 'holding_group'
                ELSE 'commercial_bank'
            END,
            institutions.name_official,
            institutions.name_commercial,
            institutions.country_id,
            CASE
                WHEN institutions.status IN ('active', 'inactive', 'under_resolution', 'liquidated', 'merged', 'unknown') THEN institutions.status
                ELSE 'active'
            END,
            institutions.description
        FROM institutions
        WHERE institutions.entity_id IS NULL
        ON CONFLICT (id) DO NOTHING;
        """
    )

    op.execute(
        """
        UPDATE institutions
        SET entity_id = institutions.id
        WHERE entity_id IS NULL;
        """
    )

    op.execute(
        """
        UPDATE financial_data
        SET entity_id = institutions.entity_id,
            observation_level = 'entity',
            consolidation_scope = CASE
                WHEN financial_data.scope IN ('individual', 'consolidated') THEN financial_data.scope
                ELSE 'individual'
            END
        FROM institutions
        WHERE financial_data.institution_id = institutions.id
          AND (financial_data.entity_id IS NULL OR financial_data.entity_id != institutions.entity_id);
        """
    )

    op.execute(
        """
        UPDATE metric_definitions
        SET sector = 'banking',
            metric_family = CASE
                WHEN statement_type = 'income_statement' THEN 'income_statement'
                ELSE 'balance_sheet'
            END
        WHERE sector IS NULL OR sector != 'banking';
        """
    )


def downgrade() -> None:
    # 1. Revert check constraints
    op.drop_constraint("ck_deal_participants_role", "deal_participants", type_="check")
    op.create_check_constraint(
        "ck_deal_participants_role", "deal_participants", f"role IN ({_in(OLD_ROLES)})"
    )

    op.drop_constraint("ck_deals_deal_type", "deals", type_="check")
    op.create_check_constraint(
        "ck_deals_deal_type", "deals", f"deal_type IS NULL OR deal_type IN ({_in(OLD_DEAL_TYPES)})"
    )

    op.drop_constraint("ck_sources_source_type", "sources", type_="check")
    op.create_check_constraint(
        "ck_sources_source_type", "sources", f"source_type IN ({_in(OLD_SOURCE_TYPES)})"
    )

    op.drop_constraint("ck_institutions_institution_type", "institutions", type_="check")
    op.create_check_constraint(
        "ck_institutions_institution_type", "institutions", f"institution_type IN ({_in(OLD_INSTITUTION_TYPES)})"
    )

    # 2. Revert financial_data
    op.drop_index("ix_financial_data_consolidation_scope", table_name="financial_data")
    op.drop_index("ix_financial_data_observation_level", table_name="financial_data")
    op.drop_index("ix_financial_data_entity_id", table_name="financial_data")
    op.drop_constraint("ck_financial_data_consolidation_scope", "financial_data", type_="check")
    op.drop_constraint("ck_financial_data_observation_level", "financial_data", type_="check")
    op.drop_constraint("ck_financial_data_target", "financial_data", type_="check")
    op.drop_column("financial_data", "consolidation_scope")
    op.drop_column("financial_data", "observation_level")
    op.drop_column("financial_data", "entity_id")
    op.alter_column("financial_data", "institution_id", existing_type=sa.String(36), nullable=False)

    # 3. Revert metric_definitions
    op.drop_index("ix_metric_definitions_metric_family", table_name="metric_definitions")
    op.drop_index("ix_metric_definitions_sector", table_name="metric_definitions")
    op.drop_constraint("ck_metric_definitions_metric_family", "metric_definitions", type_="check")
    op.drop_constraint("ck_metric_definitions_sector", "metric_definitions", type_="check")
    op.drop_column("metric_definitions", "metric_family")
    op.drop_column("metric_definitions", "sector")

    # 4. Revert institutions
    op.drop_index("ix_institutions_entity_id", table_name="institutions")
    op.drop_constraint("uq_institutions_entity_id", "institutions", type_="unique")
    op.drop_column("institutions", "entity_id")

    # 5. Revert entity_relationships
    op.drop_index("ix_entity_relationships_is_current", table_name="entity_relationships")
    op.drop_index("ix_entity_relationships_type", table_name="entity_relationships")
    op.drop_index("ix_entity_relationships_target", table_name="entity_relationships")
    op.drop_index("ix_entity_relationships_source", table_name="entity_relationships")
    op.drop_table("entity_relationships")

    # 6. Revert entities
    op.drop_index("ix_entities_status", table_name="entities")
    op.drop_index("ix_entities_country_id", table_name="entities")
    op.drop_index("ix_entities_entity_type", table_name="entities")
    op.drop_index("ix_entities_entity_class", table_name="entities")
    op.drop_index("ix_entities_canonical_name", table_name="entities")
    op.drop_table("entities")
