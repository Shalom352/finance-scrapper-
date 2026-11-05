"""Track last progress separately from the run start time.

Revision ID: 0027_ingestion_progress_heartbeat
Revises: 0026_source_enrichment_events
"""

from alembic import op
import sqlalchemy as sa

revision = "0027_ingestion_progress_heartbeat"
down_revision = "0026_source_enrichment_events"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("last_progress_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE ingestion_runs SET last_progress_at = started_at WHERE last_progress_at IS NULL")


def downgrade() -> None:
    op.drop_column("ingestion_runs", "last_progress_at")
