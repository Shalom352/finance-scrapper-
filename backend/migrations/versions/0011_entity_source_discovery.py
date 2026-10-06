"""Entity & Source Discovery Engine (Phase 15)

Additive migration:
- New tables: reference_universes, reference_universe_members, entity_identifiers,
  entity_names, discovery_runs, entity_sources, document_entities, discovery_rounds,
  discovery_gaps;
- sources: lifecycle_status (+ deterministic backfill), last_checked_at, last_http_status,
  last_error, check_frequency_days;
- documents: entity_id (+ backfill from institutions.entity_id).

No existing row, ID or relation is modified other than the two documented backfills.
Downgrade drops only the objects created here.

Revision ID: 0011_entity_source_discovery
Revises: 0010_seed_markets_and_public_debt
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0011_entity_source_discovery"
down_revision = "0010_seed_markets_and_public_debt"
branch_labels = None
depends_on = None

# Frozen copies of the vocabularies (a migration must not depend on evolving app constants).
UNIVERSE_STATUSES = ("COMPLETE", "INCOMPLETE", "UNKNOWN", "SOURCE_UNAVAILABLE", "AMBIGUOUS")
MEMBER_CATEGORIES = ("bank", "financial_establishment")
MEMBER_FORMS = ("subsidiary", "branch", "unspecified")
RESOLUTION_STATUSES = ("matched", "created", "ambiguous", "unresolved")
REVIEW_DECISIONS = ("confirmed", "rejected")
IDENTIFIER_TYPES = ("bceao_registration_number",)
NAME_TYPES = ("official", "acronym", "former", "alias", "commercial", "regulatory_label")
SOURCE_LIFECYCLE_STATUSES = ("CANDIDATE", "VERIFIED", "ACTIVE", "BLOCKED", "RETIRED")
LINK_ROLES = (
    "regulatory_listing",
    "official_website",
    "official_publications",
    "market_infrastructure",
    "public_body",
    "professional_federation",
    "secondary",
)
DOCUMENT_LINK_TYPES = ("reference_listing", "financial_statement", "annual_report", "regulatory_mention", "other")
DISCOVERY_RUN_STATUSES = ("running", "completed", "failed")
DISCOVERY_TRIGGER_TYPES = ("cli", "scheduled", "manual", "test")
STOP_CONDITIONS = ("A_UNIVERSE_COVERED", "B_STRATEGIES_EXHAUSTED", "C_REFERENCE_UNAVAILABLE", "SAFETY_CAP_REACHED")
GAP_TYPES = (
    "ENTITY_UNRESOLVED",
    "REGULATORY_SOURCE",
    "OFFICIAL_WEBSITE",
    "ANNUAL_REPORT",
    "FINANCIAL_DOCUMENT",
    "FINANCIAL_DATA",
    "VALIDATION",
)
GAP_PRIORITIES = ("HIGH", "MEDIUM", "LOW")
GAP_STATUSES = ("OPEN", "SEARCHING", "NOT_FOUND", "BLOCKED", "RESOLVED")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def _fk(table: str, ondelete: str) -> sa.ForeignKey:
    return sa.ForeignKey(f"{table}.id", ondelete=ondelete)


def upgrade() -> None:
    # ------------------------------------------------------------------ reference_universes
    op.create_table(
        "reference_universes",
        *_audit_columns(),
        sa.Column("universe_code", sa.String(50), nullable=False),
        sa.Column("entity_class", sa.String(50), nullable=False, server_default="financial_institution"),
        sa.Column("entity_type", sa.String(50), nullable=False, server_default="commercial_bank"),
        sa.Column("country_id", sa.String(36), _fk("countries", "RESTRICT"), nullable=True),
        sa.Column("reference_source_id", sa.String(36), _fk("sources", "RESTRICT"), nullable=True),
        sa.Column("reference_document_id", sa.String(36), _fk("documents", "RESTRICT"), nullable=True),
        sa.Column("reference_date", sa.Date(), nullable=True),
        sa.Column("expected_count", sa.Integer(), nullable=True),
        sa.Column("expected_count_evidence", sa.Text(), nullable=True),
        sa.Column("discovered_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("matched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("coverage_ratio", sa.Numeric(6, 5), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="UNKNOWN"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("self_check", JSONB(), nullable=True),
        sa.Column("history_events", JSONB(), nullable=True),
        sa.CheckConstraint(f"status IN ({_in(UNIVERSE_STATUSES)})", name="ck_reference_universes_status"),
        sa.CheckConstraint("expected_count IS NULL OR expected_count >= 0", name="ck_reference_universes_expected"),
        sa.CheckConstraint(
            "coverage_ratio IS NULL OR (coverage_ratio >= 0 AND coverage_ratio <= 1)",
            name="ck_reference_universes_ratio",
        ),
    )
    op.create_index("ix_reference_universes_code_current", "reference_universes", ["universe_code", "is_current"])
    op.create_index("ix_reference_universes_document", "reference_universes", ["reference_document_id"])
    op.create_index(
        "uq_reference_universes_snapshot",
        "reference_universes",
        ["universe_code", "reference_document_id", sa.text("COALESCE(country_id, 'UMOA')")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ reference_universe_members
    op.create_table(
        "reference_universe_members",
        *_audit_columns(),
        sa.Column("universe_id", sa.String(36), _fk("reference_universes", "RESTRICT"), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("member_form", sa.String(20), nullable=False, server_default="unspecified"),
        sa.Column("raw_name", sa.Text(), nullable=False),
        sa.Column("official_name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("acronym", sa.String(100), nullable=True),
        sa.Column("former_names", JSONB(), nullable=True),
        sa.Column("parent_name_raw", sa.String(500), nullable=True),
        sa.Column("registration_number", sa.String(30), nullable=True),
        sa.Column("row_index", sa.Integer(), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("raw_text", sa.Text(), nullable=True),
        sa.Column("flags", JSONB(), nullable=True),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=True),
        sa.Column("resolution_status", sa.String(20), nullable=False, server_default="unresolved"),
        sa.Column("resolution_method", sa.String(50), nullable=True),
        sa.Column("confidence", sa.Numeric(4, 3), nullable=True),
        sa.Column("candidate_entity_ids", JSONB(), nullable=True),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("review_decision", sa.String(20), nullable=True),
        sa.Column("decided_by", sa.String(255), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(f"category IN ({_in(MEMBER_CATEGORIES)})", name="ck_universe_members_category"),
        sa.CheckConstraint(f"member_form IN ({_in(MEMBER_FORMS)})", name="ck_universe_members_form"),
        sa.CheckConstraint(
            f"resolution_status IN ({_in(RESOLUTION_STATUSES)})", name="ck_universe_members_resolution"
        ),
        sa.CheckConstraint(
            f"review_decision IS NULL OR review_decision IN ({_in(REVIEW_DECISIONS)})",
            name="ck_universe_members_review_decision",
        ),
        sa.CheckConstraint(
            "resolution_status NOT IN ('matched', 'created') OR entity_id IS NOT NULL",
            name="ck_universe_members_resolved_has_entity",
        ),
        sa.CheckConstraint(
            "resolution_status != 'ambiguous' OR entity_id IS NULL", name="ck_universe_members_ambiguous"
        ),
        sa.CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_universe_members_page"),
    )
    op.create_index("ix_universe_members_universe", "reference_universe_members", ["universe_id"])
    op.create_index("ix_universe_members_entity", "reference_universe_members", ["entity_id"])
    op.create_index("ix_universe_members_registration", "reference_universe_members", ["registration_number"])
    op.create_index(
        "uq_universe_members_line",
        "reference_universe_members",
        ["universe_id", "category", sa.text("COALESCE(registration_number, normalized_name)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ entity_identifiers
    op.create_table(
        "entity_identifiers",
        *_audit_columns(),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=False),
        sa.Column("id_type", sa.String(50), nullable=False),
        sa.Column("value", sa.String(100), nullable=False),
        sa.Column("authority_entity_id", sa.String(36), _fk("entities", "SET NULL"), nullable=True),
        sa.Column("authority_name", sa.String(255), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_id", sa.String(36), _fk("sources", "SET NULL"), nullable=True),
        sa.Column("document_id", sa.String(36), _fk("documents", "SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.CheckConstraint(f"id_type IN ({_in(IDENTIFIER_TYPES)})", name="ck_entity_identifiers_type"),
        sa.CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_entity_identifiers_page"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_entity_identifiers_dates"
        ),
    )
    op.create_index("ix_entity_identifiers_entity", "entity_identifiers", ["entity_id"])
    op.create_index(
        "uq_entity_identifiers_value",
        "entity_identifiers",
        ["id_type", "value"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ entity_names
    op.create_table(
        "entity_names",
        *_audit_columns(),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=False),
        sa.Column("name", sa.String(500), nullable=False),
        sa.Column("normalized_name", sa.String(500), nullable=False),
        sa.Column("name_type", sa.String(30), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("source_id", sa.String(36), _fk("sources", "SET NULL"), nullable=True),
        sa.Column("document_id", sa.String(36), _fk("documents", "SET NULL"), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.CheckConstraint(f"name_type IN ({_in(NAME_TYPES)})", name="ck_entity_names_type"),
        sa.CheckConstraint("page_number IS NULL OR page_number > 0", name="ck_entity_names_page"),
        sa.CheckConstraint(
            "valid_to IS NULL OR valid_from IS NULL OR valid_to >= valid_from", name="ck_entity_names_dates"
        ),
    )
    op.create_index("ix_entity_names_entity", "entity_names", ["entity_id"])
    op.create_index("ix_entity_names_normalized", "entity_names", ["normalized_name"])
    op.create_index(
        "uq_entity_names_entry",
        "entity_names",
        ["entity_id", "name_type", "normalized_name"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ discovery_runs
    op.create_table(
        "discovery_runs",
        *_audit_columns(),
        sa.Column("universe_code", sa.String(50), nullable=False),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="cli"),
        sa.Column("status", sa.String(20), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_condition", sa.String(40), nullable=True),
        sa.Column("stop_reason", sa.Text(), nullable=True),
        sa.Column("parameters", JSONB(), nullable=True),
        sa.Column("coverage_before", JSONB(), nullable=True),
        sa.Column("coverage_after", JSONB(), nullable=True),
        sa.Column("errors", JSONB(), nullable=True),
        sa.CheckConstraint(f"status IN ({_in(DISCOVERY_RUN_STATUSES)})", name="ck_discovery_runs_status"),
        sa.CheckConstraint(f"trigger_type IN ({_in(DISCOVERY_TRIGGER_TYPES)})", name="ck_discovery_runs_trigger"),
        sa.CheckConstraint(
            f"stop_condition IS NULL OR stop_condition IN ({_in(STOP_CONDITIONS)})",
            name="ck_discovery_runs_stop_condition",
        ),
    )
    op.create_index("ix_discovery_runs_started", "discovery_runs", ["started_at"])

    # ------------------------------------------------------------------ entity_sources
    op.create_table(
        "entity_sources",
        *_audit_columns(),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=False),
        sa.Column("source_id", sa.String(36), _fk("sources", "SET NULL"), nullable=True),
        sa.Column("url", sa.String(2048), nullable=True),
        sa.Column("link_role", sa.String(40), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("lifecycle_status", sa.String(20), nullable=False, server_default="CANDIDATE"),
        sa.Column("discovery_method", sa.String(100), nullable=True),
        sa.Column("discovery_run_id", sa.String(36), _fk("discovery_runs", "SET NULL"), nullable=True),
        sa.Column("evidence_document_id", sa.String(36), _fk("documents", "SET NULL"), nullable=True),
        sa.Column("evidence_page", sa.Integer(), nullable=True),
        sa.Column("verification_evidence", sa.Text(), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_http_status", sa.Integer(), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.CheckConstraint(f"link_role IN ({_in(LINK_ROLES)})", name="ck_entity_sources_role"),
        sa.CheckConstraint(
            f"lifecycle_status IN ({_in(SOURCE_LIFECYCLE_STATUSES)})", name="ck_entity_sources_lifecycle"
        ),
        sa.CheckConstraint("priority >= 1 AND priority <= 7", name="ck_entity_sources_priority"),
    )
    op.create_index("ix_entity_sources_entity", "entity_sources", ["entity_id"])
    op.create_index("ix_entity_sources_role_status", "entity_sources", ["link_role", "lifecycle_status"])
    op.create_index(
        "uq_entity_sources_link",
        "entity_sources",
        ["entity_id", "link_role", sa.text("COALESCE(source_id, '')"), sa.text("COALESCE(url, '')")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ document_entities
    op.create_table(
        "document_entities",
        *_audit_columns(),
        sa.Column("document_id", sa.String(36), _fk("documents", "RESTRICT"), nullable=False),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=False),
        sa.Column("link_type", sa.String(30), nullable=False),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("label_in_document", sa.String(500), nullable=True),
        sa.Column("method", sa.String(50), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.CheckConstraint(f"link_type IN ({_in(DOCUMENT_LINK_TYPES)})", name="ck_document_entities_type"),
        sa.CheckConstraint("page_from IS NULL OR page_from > 0", name="ck_document_entities_page_from"),
        sa.CheckConstraint(
            "page_to IS NULL OR page_from IS NULL OR page_to >= page_from", name="ck_document_entities_pages"
        ),
    )
    op.create_index("ix_document_entities_entity", "document_entities", ["entity_id"])
    op.create_index("ix_document_entities_document", "document_entities", ["document_id"])
    op.create_index(
        "uq_document_entities_link",
        "document_entities",
        ["document_id", "entity_id", "link_type", sa.text("COALESCE(page_from, 0)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------ discovery_rounds
    op.create_table(
        "discovery_rounds",
        *_audit_columns(),
        sa.Column("run_id", sa.String(36), _fk("discovery_runs", "RESTRICT"), nullable=False),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("strategy_code", sa.String(80), nullable=False),
        sa.Column("strategy_description", sa.Text(), nullable=True),
        sa.Column("targets_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sources_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_entities", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_documents", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_document_links", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("new_observations", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("coverage_before", JSONB(), nullable=True),
        sa.Column("coverage_after", JSONB(), nullable=True),
        sa.Column("details", JSONB(), nullable=True),
        sa.Column("errors", JSONB(), nullable=True),
        sa.CheckConstraint("round_number >= 1", name="ck_discovery_rounds_number"),
    )
    op.create_index("ix_discovery_rounds_run", "discovery_rounds", ["run_id", "round_number"])

    # ------------------------------------------------------------------ discovery_gaps
    op.create_table(
        "discovery_gaps",
        *_audit_columns(),
        sa.Column("universe_id", sa.String(36), _fk("reference_universes", "SET NULL"), nullable=True),
        sa.Column("entity_id", sa.String(36), _fk("entities", "RESTRICT"), nullable=True),
        sa.Column("member_id", sa.String(36), _fk("reference_universe_members", "SET NULL"), nullable=True),
        sa.Column("country_id", sa.String(36), _fk("countries", "RESTRICT"), nullable=True),
        sa.Column("gap_type", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(10), nullable=False, server_default="MEDIUM"),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("strategies_tried", JSONB(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.CheckConstraint(f"gap_type IN ({_in(GAP_TYPES)})", name="ck_discovery_gaps_type"),
        sa.CheckConstraint(f"priority IN ({_in(GAP_PRIORITIES)})", name="ck_discovery_gaps_priority"),
        sa.CheckConstraint(f"status IN ({_in(GAP_STATUSES)})", name="ck_discovery_gaps_status"),
        sa.CheckConstraint("attempts >= 0", name="ck_discovery_gaps_attempts"),
    )
    op.create_index("ix_discovery_gaps_status", "discovery_gaps", ["status", "gap_type"])
    op.create_index("ix_discovery_gaps_entity", "discovery_gaps", ["entity_id"])
    op.create_index(
        "uq_discovery_gaps_open",
        "discovery_gaps",
        [sa.text("COALESCE(entity_id, '')"), sa.text("COALESCE(member_id, '')"), "gap_type"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND status != 'RESOLVED'"),
    )

    # ------------------------------------------------------------------ sources: lifecycle
    op.add_column(
        "sources", sa.Column("lifecycle_status", sa.String(20), nullable=False, server_default="CANDIDATE")
    )
    op.add_column("sources", sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("sources", sa.Column("last_http_status", sa.Integer(), nullable=True))
    op.add_column("sources", sa.Column("last_error", sa.Text(), nullable=True))
    op.add_column("sources", sa.Column("check_frequency_days", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_sources_lifecycle_status", "sources", f"lifecycle_status IN ({_in(SOURCE_LIFECYCLE_STATUSES)})"
    )
    # Deterministic, evidence-based backfill:
    #   ACTIVE   : the source already produced at least one downloaded document;
    #   VERIFIED : monitored (is_active) but no downloaded document yet;
    #   RETIRED  : no longer monitored.
    op.execute(
        """
        UPDATE sources SET lifecycle_status = CASE
            WHEN EXISTS (
                SELECT 1 FROM documents d
                WHERE d.source_id = sources.id AND d.download_status = 'downloaded' AND d.deleted_at IS NULL
            ) THEN 'ACTIVE'
            WHEN sources.is_active THEN 'VERIFIED'
            ELSE 'RETIRED'
        END;
        """
    )

    # ------------------------------------------------------------------ documents: entity_id
    op.add_column("documents", sa.Column("entity_id", sa.String(36), _fk("entities", "SET NULL"), nullable=True))
    op.create_index("ix_documents_entity_id", "documents", ["entity_id"])
    op.execute(
        """
        UPDATE documents SET entity_id = institutions.entity_id
        FROM institutions
        WHERE documents.institution_id = institutions.id
          AND institutions.entity_id IS NOT NULL
          AND documents.entity_id IS NULL;
        """
    )


def downgrade() -> None:
    op.drop_index("ix_documents_entity_id", table_name="documents")
    op.drop_column("documents", "entity_id")

    op.drop_constraint("ck_sources_lifecycle_status", "sources", type_="check")
    for column in ("check_frequency_days", "last_error", "last_http_status", "last_checked_at", "lifecycle_status"):
        op.drop_column("sources", column)

    for table in (
        "discovery_gaps",
        "discovery_rounds",
        "document_entities",
        "entity_sources",
        "discovery_runs",
        "entity_names",
        "entity_identifiers",
        "reference_universe_members",
        "reference_universes",
    ):
        op.drop_table(table)
