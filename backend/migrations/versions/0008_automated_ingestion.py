"""Automated Ingestion (Tracking & Execution Journal)

Creates the `ingestion_runs` table to record execution history, counters,
target years, and granular errors for automated (2x/day) and manual runs.

Revision ID: 0008_automated_ingestion
Revises: 0007_deal_intelligence
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008_automated_ingestion"
down_revision = "0007_deal_intelligence"
branch_labels = None
depends_on = None

STATUSES = ("running", "completed", "partial_failure", "failed", "skipped_concurrent")
TRIGGER_TYPES = ("scheduled", "manual", "cli")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def upgrade() -> None:
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("trigger_type", sa.String(20), nullable=False, server_default="scheduled"),
        sa.Column("status", sa.String(30), nullable=False, server_default="running"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_years", sa.String(255), nullable=True),
        sa.Column("sources_checked", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_found", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_new", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_downloaded", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_skipped", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("documents_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_points_extracted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("data_points_needing_review", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("errors", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.CheckConstraint(f"status IN ({_in(STATUSES)})", name="ck_ingestion_runs_status"),
        sa.CheckConstraint(f"trigger_type IN ({_in(TRIGGER_TYPES)})", name="ck_ingestion_runs_trigger_type"),
    )
    op.create_index("ix_ingestion_runs_status", "ingestion_runs", ["status"])
    op.create_index("ix_ingestion_runs_started_at", "ingestion_runs", ["started_at"])


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_started_at", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_status", table_name="ingestion_runs")
    op.drop_table("ingestion_runs")
