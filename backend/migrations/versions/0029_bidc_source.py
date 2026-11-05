"""Register BIDC for official deal collection.

The collector reads BIDC's public French financing announcements and uses their official pages as
primary-source evidence. Existing deal/source schema already supports DFI provenance.

Revision ID: 0029_bidc_source
Revises: 0028_ingestion_page_progress
"""
import uuid

import sqlalchemy as sa
from alembic import op

revision = "0029_bidc_source"
down_revision = "0028_ingestion_page_progress"
branch_labels = None
depends_on = None

SHORT_NAME = "BIDC"


def upgrade() -> None:
    op.execute(
        sa.text(
            """
            INSERT INTO sources (id, name, short_name, publisher, url, source_type, priority, country_code,
                                 language, description, is_active, created_at, updated_at)
            SELECT :id, :name, :short_name, :publisher, :url, 'development_institution', 1, NULL, 'fr',
                   :description, true, NOW(), NOW()
            WHERE NOT EXISTS (SELECT 1 FROM sources WHERE short_name = :short_name)
            """
        ).bindparams(
            id=str(uuid.uuid4()),
            name="Banque d'Investissement et de Développement de la CEDEAO",
            short_name=SHORT_NAME,
            publisher="BIDC / ECOWAS Bank for Investment and Development",
            url="https://www.bidc-ebid.org/fr/category/actualites/",
            description="Annonces officielles de financements et d'opérations approuvées par la BIDC.",
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    used = bind.execute(sa.text(
        "SELECT (SELECT count(*) FROM documents d JOIN sources s ON s.id = d.source_id WHERE s.short_name = :n) "
        "     + (SELECT count(*) FROM deal_sources ds JOIN sources s ON s.id = ds.source_id WHERE s.short_name = :n)"
    ).bindparams(n=SHORT_NAME)).scalar()
    if used:
        raise RuntimeError(f"downgrade of 0029 refused: {used} documents / deal sources of BIDC")
    op.execute(sa.text("DELETE FROM sources WHERE short_name = :n").bindparams(n=SHORT_NAME))
