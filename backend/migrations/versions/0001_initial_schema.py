"""initial schema (countries, sources, banking_groups, institutions, metric_definitions, documents, financial_data)

Creates the complete V1 PostgreSQL schema with:
- primary keys (VARCHAR(36) UUID strings, generated application-side)
- audit columns (created_at, updated_at, deleted_at) from the declarative Base
- foreign keys with the documented ON DELETE behaviours
- UNIQUE constraints (countries.code, metric_definitions.code, documents.file_hash)
- CHECK constraints (canonical enumerations + numeric integrity + workflow)
- indexes declared on the ORM models

Explicit (non auto-generated) migration so the DDL is fully deterministic.
Validated against the SQLAlchemy models' rendered DDL (PostgreSQL dialect).

Reference: docs/specification-v1.md sections 6, 10, 12, 13, 14, 15.

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-09-21

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial_schema"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # countries
    op.create_table(
        "countries",
        sa.Column("code", sa.String(length=2), nullable=False),
        sa.Column("name_fr", sa.String(length=100), nullable=False),
        sa.Column("name_en", sa.String(length=100), nullable=False),
        sa.Column("flag_emoji", sa.String(length=10), nullable=True),
        sa.Column("capital_fr", sa.String(length=100), nullable=True),
        sa.Column("capital_en", sa.String(length=100), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_countries_code"),
    )
    op.create_index("ix_countries_code", "countries", ["code"])

    # sources
    op.create_table(
        "sources",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=50), nullable=True),
        sa.Column("publisher", sa.String(length=255), nullable=True),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("country_code", sa.String(length=2), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sources_source_type", "sources", ["source_type"])
    op.create_index("ix_sources_country_code", "sources", ["country_code"])

    # banking_groups
    op.create_table(
        "banking_groups",
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("short_name", sa.String(length=100), nullable=True),
        sa.Column("headquarter_country_code", sa.String(length=2), nullable=True),
        sa.Column("headquarter_city", sa.String(length=100), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_banking_groups_source_id_sources",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_banking_groups_source_id", "banking_groups", ["source_id"])

    # institutions
    op.create_table(
        "institutions",
        sa.Column("name_official", sa.String(length=255), nullable=False),
        sa.Column("name_commercial", sa.String(length=255), nullable=True),
        sa.Column("institution_type", sa.String(length=50), nullable=False),
        sa.Column("country_id", sa.String(length=36), nullable=False),
        sa.Column("banking_group_id", sa.String(length=36), nullable=True),
        sa.Column("regulatory_id", sa.String(length=100), nullable=True),
        sa.Column("website_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_notes", sa.Text(), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["country_id"],
            ["countries.id"],
            name="fk_institutions_country_id_countries",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["banking_group_id"],
            ["banking_groups.id"],
            name="fk_institutions_banking_group_id_banking_groups",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_institutions_source_id_sources",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_institutions_name_official", "institutions", ["name_official"])
    op.create_index("ix_institutions_institution_type", "institutions", ["institution_type"])
    op.create_index("ix_institutions_country_id", "institutions", ["country_id"])
    op.create_index("ix_institutions_banking_group_id", "institutions", ["banking_group_id"])
    op.create_index("ix_institutions_status", "institutions", ["status"])
    op.create_index("ix_institutions_source_id", "institutions", ["source_id"])

    # metric_definitions (catalogue officiel — seeded in migration 0002)
    op.create_table(
        "metric_definitions",
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label_fr", sa.String(length=150), nullable=False),
        sa.Column("label_en", sa.String(length=150), nullable=False),
        sa.Column("definition_fr", sa.Text(), nullable=False),
        sa.Column("definition_en", sa.Text(), nullable=False),
        sa.Column("statement_type", sa.String(length=30), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("value_type", sa.String(length=20), nullable=False),
        sa.Column("currency_type", sa.String(length=20), nullable=False),
        sa.Column("is_calculated", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_debt_related", sa.Boolean(), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("description_synth", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_metric_definitions_code"),
        sa.CheckConstraint(
            "statement_type IN ('balance_sheet', 'income_statement', "
            "'cash_flow_statement', 'off_balance_sheet', 'not_applicable')",
            name="ck_metric_definitions_statement_type",
        ),
        sa.CheckConstraint(
            "category IN ('assets', 'liabilities', 'equity', "
            "'income_statement', 'cash_flow', 'debt_indicator')",
            name="ck_metric_definitions_category",
        ),
        sa.CheckConstraint(
            "value_type IN ('amount', 'percentage', 'ratio', 'rate')",
            name="ck_metric_definitions_value_type",
        ),
        sa.CheckConstraint(
            "currency_type IN ('monetary', 'non_monetary')",
            name="ck_metric_definitions_currency_type",
        ),
    )
    op.create_index("ix_metric_definitions_code", "metric_definitions", ["code"])
    op.create_index(
        "ix_metric_definitions_statement_type", "metric_definitions", ["statement_type"]
    )
    op.create_index("ix_metric_definitions_category", "metric_definitions", ["category"])

    # documents
    op.create_table(
        "documents",
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("institution_id", sa.String(length=36), nullable=True),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=True),
        sa.Column("file_hash", sa.String(length=64), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("storage_path", sa.String(length=500), nullable=True),
        sa.Column("download_status", sa.String(length=20), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("extraction_status", sa.String(length=20), nullable=False),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("published_at", sa.Date(), nullable=True),
        sa.Column("period_year", sa.Integer(), nullable=True),
        sa.Column("period_type", sa.String(length=20), nullable=True),
        sa.Column("language", sa.String(length=5), nullable=True),
        sa.Column("collected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "document_type IN ('annual_report', 'financial_statement', "
            "'regulatory_report', 'press_release', 'web_page', 'other')",
            name="ck_documents_document_type",
        ),
        sa.CheckConstraint(
            "download_status IN ('pending', 'downloaded', 'failed')",
            name="ck_documents_download_status",
        ),
        sa.CheckConstraint(
            "extraction_status IN ('pending', 'extracted', 'failed', 'skipped')",
            name="ck_documents_extraction_status",
        ),
        sa.CheckConstraint(
            "period_type IS NULL OR period_type IN ('annual', 'semi_annual', 'quarterly')",
            name="ck_documents_period_type",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_documents_page_count_positive",
        ),
        sa.CheckConstraint(
            "file_size IS NULL OR file_size >= 0",
            name="ck_documents_file_size_non_negative",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_documents_institution_id_institutions",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_documents_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("file_hash"),
    )
    op.create_index("ix_documents_document_type", "documents", ["document_type"])
    op.create_index("ix_documents_institution_id", "documents", ["institution_id"])
    op.create_index("ix_documents_source_id", "documents", ["source_id"])
    op.create_index("ix_documents_download_status", "documents", ["download_status"])
    op.create_index("ix_documents_extraction_status", "documents", ["extraction_status"])
    op.create_index("ix_documents_period_year", "documents", ["period_year"])

    # financial_data
    op.create_table(
        "financial_data",
        sa.Column("institution_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("document_id", sa.String(length=36), nullable=False),
        sa.Column("metric_code", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=20), nullable=False),
        sa.Column("period_type", sa.String(length=20), nullable=False),
        sa.Column("period_year", sa.Integer(), nullable=False),
        sa.Column("period_label", sa.String(length=20), nullable=True),
        sa.Column("value_original", sa.Text(), nullable=False),
        sa.Column("unit_original", sa.String(length=50), nullable=True),
        sa.Column("currency_original", sa.String(length=10), nullable=True),
        sa.Column("value_normalized", sa.Numeric(precision=24, scale=6), nullable=True),
        sa.Column("unit_normalized", sa.String(length=20), nullable=True),
        sa.Column("currency_normalized", sa.String(length=10), nullable=True),
        sa.Column("page_number", sa.Integer(), nullable=True),
        sa.Column("extraction_method", sa.String(length=20), nullable=False),
        sa.Column("confidence_score", sa.Numeric(precision=4, scale=3), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("extracted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_by", sa.String(length=100), nullable=True),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "scope IN ('individual', 'consolidated')",
            name="ck_financial_data_scope",
        ),
        sa.CheckConstraint(
            "period_type IN ('annual', 'semi_annual', 'quarterly')",
            name="ck_financial_data_period_type",
        ),
        sa.CheckConstraint(
            "extraction_method IN ('pdf_table', 'pdf_text', 'ocr', 'web_html', 'manual')",
            name="ck_financial_data_extraction_method",
        ),
        sa.CheckConstraint(
            "status IN ('extracted', 'needs_review', 'reviewed', 'verified', 'rejected')",
            name="ck_financial_data_status",
        ),
        sa.CheckConstraint(
            "confidence_score IS NULL OR (confidence_score >= 0 AND confidence_score <= 1)",
            name="ck_financial_data_confidence_range",
        ),
        sa.CheckConstraint(
            "page_number IS NULL OR page_number > 0",
            name="ck_financial_data_page_number_positive",
        ),
        sa.CheckConstraint(
            "period_year >= 1900 AND period_year <= 2100",
            name="ck_financial_data_period_year_range",
        ),
        sa.CheckConstraint(
            "status NOT IN ('reviewed', 'verified') OR value_normalized IS NOT NULL",
            name="ck_financial_data_reviewed_requires_normalized",
        ),
        sa.CheckConstraint(
            "status != 'verified' OR (verified_at IS NOT NULL AND verified_by IS NOT NULL)",
            name="ck_financial_data_verified_requires_validator",
        ),
        sa.ForeignKeyConstraint(
            ["institution_id"],
            ["institutions.id"],
            name="fk_financial_data_institution_id_institutions",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name="fk_financial_data_source_id_sources",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_financial_data_document_id_documents",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["metric_code"],
            ["metric_definitions.code"],
            name="fk_financial_data_metric_code_metric_definitions",
            ondelete="RESTRICT",
        ),
    )
    op.create_index("ix_financial_data_institution_id", "financial_data", ["institution_id"])
    op.create_index("ix_financial_data_source_id", "financial_data", ["source_id"])
    op.create_index("ix_financial_data_document_id", "financial_data", ["document_id"])
    op.create_index("ix_financial_data_metric_code", "financial_data", ["metric_code"])
    op.create_index("ix_financial_data_scope", "financial_data", ["scope"])
    op.create_index("ix_financial_data_period_year", "financial_data", ["period_year"])
    op.create_index("ix_financial_data_status", "financial_data", ["status"])


def downgrade() -> None:
    op.drop_index("ix_financial_data_status", table_name="financial_data")
    op.drop_index("ix_financial_data_period_year", table_name="financial_data")
    op.drop_index("ix_financial_data_scope", table_name="financial_data")
    op.drop_index("ix_financial_data_metric_code", table_name="financial_data")
    op.drop_index("ix_financial_data_document_id", table_name="financial_data")
    op.drop_index("ix_financial_data_source_id", table_name="financial_data")
    op.drop_index("ix_financial_data_institution_id", table_name="financial_data")
    op.drop_table("financial_data")
    op.drop_index("ix_documents_period_year", table_name="documents")
    op.drop_index("ix_documents_extraction_status", table_name="documents")
    op.drop_index("ix_documents_download_status", table_name="documents")
    op.drop_index("ix_documents_source_id", table_name="documents")
    op.drop_index("ix_documents_institution_id", table_name="documents")
    op.drop_index("ix_documents_document_type", table_name="documents")
    op.drop_table("documents")
    op.drop_index("ix_metric_definitions_category", table_name="metric_definitions")
    op.drop_index("ix_metric_definitions_statement_type", table_name="metric_definitions")
    op.drop_index("ix_metric_definitions_code", table_name="metric_definitions")
    op.drop_table("metric_definitions")
    op.drop_index("ix_institutions_source_id", table_name="institutions")
    op.drop_index("ix_institutions_status", table_name="institutions")
    op.drop_index("ix_institutions_banking_group_id", table_name="institutions")
    op.drop_index("ix_institutions_country_id", table_name="institutions")
    op.drop_index("ix_institutions_institution_type", table_name="institutions")
    op.drop_index("ix_institutions_name_official", table_name="institutions")
    op.drop_table("institutions")
    op.drop_index("ix_banking_groups_source_id", table_name="banking_groups")
    op.drop_table("banking_groups")
    op.drop_index("ix_sources_country_code", table_name="sources")
    op.drop_index("ix_sources_source_type", table_name="sources")
    op.drop_table("sources")
    op.drop_index("ix_countries_code", table_name="countries")
    op.drop_table("countries")
