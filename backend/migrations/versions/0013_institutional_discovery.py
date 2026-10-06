"""Institution-specific source & document discovery (Phase 17)

Additive migration:
- discovery_gaps: Phase-17 gap taxonomy added to the CHECK (Phase-15 types kept for history),
  columns evidence, last_strategy;
- documents: text_layer_status (machine_readable | partially_corrupted | not_machine_readable |
  unknown), file_format, reporting_year.

No existing row, value or status is modified (new columns are NULL / 'unknown').

Revision ID: 0013_institutional_discovery
Revises: 0012_scope_evidence_and_document_scope
"""

import sqlalchemy as sa
from alembic import op

revision = "0013_institutional_discovery"
down_revision = "0012_scope_evidence_and_document_scope"
branch_labels = None
depends_on = None

OLD_GAP_TYPES = (
    "ENTITY_UNRESOLVED", "REGULATORY_SOURCE", "OFFICIAL_WEBSITE", "ANNUAL_REPORT", "FINANCIAL_DOCUMENT",
    "FINANCIAL_DATA", "VALIDATION",
)
NEW_GAP_TYPES = OLD_GAP_TYPES + (
    "SOURCE_NOT_FOUND", "SOURCE_FOUND_UNVERIFIED", "SOURCE_BLOCKED", "DOCUMENT_NOT_FOUND",
    "DOCUMENT_FOUND_UNVERIFIED", "DOCUMENT_NOT_MACHINE_READABLE", "ENTITY_AMBIGUOUS",
    "PARENT_SUBSIDIARY_AMBIGUITY", "HISTORICAL_NAME_AMBIGUITY",
)
TEXT_LAYER_STATUSES = ("machine_readable", "partially_corrupted", "not_machine_readable", "unknown")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.drop_constraint("ck_discovery_gaps_type", "discovery_gaps", type_="check")
    op.create_check_constraint("ck_discovery_gaps_type", "discovery_gaps", f"gap_type IN ({_in(NEW_GAP_TYPES)})")
    op.add_column("discovery_gaps", sa.Column("evidence", sa.Text(), nullable=True))
    op.add_column("discovery_gaps", sa.Column("last_strategy", sa.String(80), nullable=True))

    op.add_column(
        "documents", sa.Column("text_layer_status", sa.String(30), nullable=False, server_default="unknown")
    )
    op.add_column("documents", sa.Column("file_format", sa.String(20), nullable=True))
    op.add_column("documents", sa.Column("reporting_year", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_documents_text_layer_status", "documents", f"text_layer_status IN ({_in(TEXT_LAYER_STATUSES)})"
    )


def downgrade() -> None:
    op.drop_constraint("ck_documents_text_layer_status", "documents", type_="check")
    for column in ("reporting_year", "file_format", "text_layer_status"):
        op.drop_column("documents", column)
    op.drop_column("discovery_gaps", "last_strategy")
    op.drop_column("discovery_gaps", "evidence")
    # Rows using Phase-17 gap types cannot satisfy the old CHECK: they are soft-deleted (kept, never
    # physically removed) before the old constraint is restored.
    op.execute(
        f"UPDATE discovery_gaps SET deleted_at = COALESCE(deleted_at, now()) "
        f"WHERE gap_type NOT IN ({_in(OLD_GAP_TYPES)})"
    )
    op.drop_constraint("ck_discovery_gaps_type", "discovery_gaps", type_="check")
    op.create_check_constraint(
        "ck_discovery_gaps_type", "discovery_gaps",
        f"gap_type IN ({_in(OLD_GAP_TYPES)}) OR deleted_at IS NOT NULL",
    )
