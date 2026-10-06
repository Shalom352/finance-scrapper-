"""Scope evidence and document scope (Phase 16)

Additive migration:
- financial_data: scope_evidence_class (A/B/C/D), scope_reason_code, scope_evidence,
  quality_flags (JSONB), source_location;
- documents: document_scope (regulatory_aggregate | institution_specific | reference_listing |
  market | unknown).

Backfill (deterministic, evidence-based) — NO status and NO value is modified:
- observations from the BCEAO fascicle (document linked as 'financial_statement' to entities by the
  discovery engine, BCEAO source) → class C + scope_inferred_from_regulatory_per_entity_reporting_convention;
- other observations carrying the Phase-13 note "scope not detected" → class D + scope_not_stated;
- market / sovereign observations (consolidation_scope = not_applicable) → reason scope_not_applicable;
- document_scope derived from the discovery links / sources.

Revision ID: 0012_scope_evidence_and_document_scope
Revises: 0011_entity_source_discovery
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0012_scope_evidence_and_document_scope"
down_revision = "0011_entity_source_discovery"
branch_labels = None
depends_on = None

SCOPE_EVIDENCE_CLASSES = ("A", "B", "C", "D")
SCOPE_REASON_CODES = (
    "scope_explicit_page",
    "scope_explicit_document_title",
    "scope_inferred_from_regulatory_per_entity_reporting_convention",
    "scope_mentioned_elsewhere_only",
    "scope_not_stated",
    "scope_conflicting_mentions",
    "document_not_machine_readable",
    "scope_not_applicable",
)
DOCUMENT_SCOPES = ("regulatory_aggregate", "institution_specific", "reference_listing", "market", "unknown")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    # ------------------------------------------------------------------ financial_data
    op.add_column("financial_data", sa.Column("scope_evidence_class", sa.String(1), nullable=True))
    op.add_column("financial_data", sa.Column("scope_reason_code", sa.String(80), nullable=True))
    op.add_column("financial_data", sa.Column("scope_evidence", sa.Text(), nullable=True))
    op.add_column("financial_data", sa.Column("quality_flags", JSONB(), nullable=True))
    op.add_column("financial_data", sa.Column("source_location", sa.String(500), nullable=True))
    op.create_index("ix_financial_data_scope_evidence_class", "financial_data", ["scope_evidence_class"])
    op.create_check_constraint(
        "ck_financial_data_scope_evidence_class",
        "financial_data",
        f"scope_evidence_class IS NULL OR scope_evidence_class IN ({_in(SCOPE_EVIDENCE_CLASSES)})",
    )
    op.create_check_constraint(
        "ck_financial_data_scope_reason_code",
        "financial_data",
        f"scope_reason_code IS NULL OR scope_reason_code IN ({_in(SCOPE_REASON_CODES)})",
    )

    # ------------------------------------------------------------------ documents
    op.add_column(
        "documents", sa.Column("document_scope", sa.String(30), nullable=False, server_default="unknown")
    )
    op.create_index("ix_documents_document_scope", "documents", ["document_scope"])
    op.create_check_constraint(
        "ck_documents_document_scope", "documents", f"document_scope IN ({_in(DOCUMENT_SCOPES)})"
    )

    # ------------------------------------------------------------------ backfill: document_scope
    # Order matters: the most specific evidence wins.
    op.execute(
        """
        UPDATE documents SET document_scope = 'reference_listing'
        WHERE EXISTS (SELECT 1 FROM document_entities de
                      WHERE de.document_id = documents.id AND de.link_type = 'reference_listing'
                        AND de.deleted_at IS NULL);
        """
    )
    op.execute(
        """
        UPDATE documents SET document_scope = 'regulatory_aggregate'
        WHERE document_scope = 'unknown'
          AND documents.source_id IN (SELECT id FROM sources WHERE short_name IN ('BCEAO', 'CB-UMOA'))
          AND EXISTS (SELECT 1 FROM document_entities de
                      WHERE de.document_id = documents.id AND de.link_type = 'financial_statement'
                        AND de.deleted_at IS NULL);
        """
    )
    op.execute(
        """
        UPDATE documents SET document_scope = 'institution_specific'
        WHERE document_scope = 'unknown' AND documents.entity_id IS NOT NULL
          AND documents.source_id NOT IN (SELECT id FROM sources
                                          WHERE short_name IN ('BCEAO', 'CB-UMOA', 'BRVM', 'UMOA-Titres'));
        """
    )
    op.execute(
        """
        UPDATE documents SET document_scope = 'market'
        WHERE document_scope = 'unknown'
          AND documents.source_id IN (SELECT id FROM sources WHERE short_name IN ('BRVM', 'UMOA-Titres'));
        """
    )

    # ------------------------------------------------------------------ backfill: scope evidence
    op.execute(
        """
        UPDATE financial_data SET
            scope_evidence_class = 'C',
            scope_reason_code = 'scope_inferred_from_regulatory_per_entity_reporting_convention',
            scope_evidence = 'BCEAO fascicle: one statement page per licensed institution; the document '
                             'does not state individual / consolidated'
        FROM documents d
        WHERE financial_data.document_id = d.id AND d.document_scope = 'regulatory_aggregate'
          AND financial_data.scope_evidence_class IS NULL;
        """
    )
    op.execute(
        """
        UPDATE financial_data SET scope_evidence_class = 'D', scope_reason_code = 'scope_not_stated'
        WHERE scope_evidence_class IS NULL AND notes LIKE '%scope not detected%';
        """
    )
    op.execute(
        """
        UPDATE financial_data SET scope_reason_code = 'scope_not_applicable'
        WHERE scope_evidence_class IS NULL AND scope_reason_code IS NULL
          AND consolidation_scope = 'not_applicable';
        """
    )
    # Only after the backfill (C/D rows are all needs_review / human statuses): automatic
    # 'extracted' requires explicit A/B evidence from now on.
    op.create_check_constraint(
        "ck_financial_data_extracted_requires_explicit_scope",
        "financial_data",
        "scope_evidence_class IS NULL OR scope_evidence_class IN ('A', 'B') OR status != 'extracted'",
    )


def downgrade() -> None:
    op.drop_constraint("ck_financial_data_extracted_requires_explicit_scope", "financial_data", type_="check")
    op.drop_constraint("ck_documents_document_scope", "documents", type_="check")
    op.drop_index("ix_documents_document_scope", table_name="documents")
    op.drop_column("documents", "document_scope")

    op.drop_constraint("ck_financial_data_scope_reason_code", "financial_data", type_="check")
    op.drop_constraint("ck_financial_data_scope_evidence_class", "financial_data", type_="check")
    op.drop_index("ix_financial_data_scope_evidence_class", table_name="financial_data")
    for column in ("source_location", "quality_flags", "scope_evidence", "scope_reason_code", "scope_evidence_class"):
        op.drop_column("financial_data", column)
