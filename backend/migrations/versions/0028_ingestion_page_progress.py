"""Track page-level progress during long source discovery runs.

Revision ID: 0028_ingestion_page_progress
Revises: 0027_ingestion_progress_heartbeat
"""

from alembic import op
import sqlalchemy as sa

revision = "0028_ingestion_page_progress"
down_revision = "0027_ingestion_progress_heartbeat"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_runs", sa.Column("current_items_done", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("ingestion_runs", sa.Column("current_items_total", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("ingestion_runs", "current_items_total")
    op.drop_column("ingestion_runs", "current_items_done")
