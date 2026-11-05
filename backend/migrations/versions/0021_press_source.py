"""Financial press source for the automated deal collection (decision D4)

Inserts, only when absent, the source "Presse financière" (Sika Finance, Agence Ecofin, Financial Afrik).
Its deals are of class ``press_reported``: needs_review, never verified without a primary source; the
actual publisher of each article is kept on deal_sources.publisher. No schema change.
Downgrade is refused while a document or a deal source uses it.

Revision ID: 0021_press_source
Revises: 0020_deal_collection
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0021_press_source"
down_revision = "0020_deal_collection"
branch_labels = None
depends_on = None

SHORT_NAME = "Presse financière"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO sources (id, name, short_name, publisher, url, source_type, priority, country_code,
                                 language, description, is_active, created_at, updated_at)
            SELECT :id, :name, :short_name, :publisher, :url, 'secondary', 3, NULL, 'fr', :description, true,
                   NOW(), NOW()
            WHERE NOT EXISTS (SELECT 1 FROM sources WHERE short_name = :short_name)
            """
        ).bindparams(
            id=str(uuid.uuid4()), name="Presse financière (Sika Finance, Agence Ecofin, Financial Afrik)",
            short_name=SHORT_NAME, publisher="Sika Finance / Agence Ecofin / Financial Afrik",
            url="https://www.sikafinance.com",
            description="Articles de presse repérés par leurs flux RSS publics. Métadonnées et citations courtes "
                        "uniquement (décision D4) ; classe press_reported, jamais vérifiable sans source primaire.",
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM documents d JOIN sources s ON s.id = d.source_id WHERE s.short_name = :n) "
        "     + (SELECT count(*) FROM deal_sources ds JOIN sources s ON s.id = ds.source_id WHERE s.short_name = :n)"
    ).bindparams(n=SHORT_NAME)).scalar()
    if used:
        raise RuntimeError(f"downgrade of 0021 refused: {used} documents / deal sources of the press source")
    op.execute(sa.text("DELETE FROM sources WHERE short_name = :n").bindparams(n=SHORT_NAME))
