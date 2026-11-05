"""Persist page-numbered OCR text with its source document.

Revision ID: 0024_document_ocr_transcript
Revises: 0023_collect_parser_version
"""

import sqlalchemy as sa
from alembic import op

revision = "0024_document_ocr_transcript"
down_revision = "0023_collect_parser_version"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("ocr_text", sa.Text(), nullable=True))


def downgrade() -> None:
    used = op.get_bind().execute(sa.text("SELECT count(*) FROM documents WHERE ocr_text IS NOT NULL")).scalar()
    if used:
        raise RuntimeError(f"downgrade refused: {used} document(s) have an OCR transcript")
    op.drop_column("documents", "ocr_text")
