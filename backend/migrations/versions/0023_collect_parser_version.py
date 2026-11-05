"""Parser version on the deal collection checkpoints (audit 22/10/2026, finding H1)

A page whose reading ended with a "final" outcome (not_a_deal, refused...) was never read again while
its published lastmod did not change — even after the parser was fixed. Each collector now has a
parser version; a checkpoint written by an older version is read again. Existing rows: NULL (= read
again once by the current parsers).

Revision ID: 0023_collect_parser_version
Revises: 0022_syndication
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_collect_parser_version"
down_revision = "0022_syndication"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("deal_collection_checkpoints", sa.Column("parser_version", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("deal_collection_checkpoints", "parser_version")
