"""Seed official sources.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-28
"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0004_seed_official_sources"
down_revision = "0003_seed_countries_and_constraints"
branch_labels = None
depends_on = None

sources = [
    {
        "name": "Banque Centrale des États de l'Afrique de l'Ouest",
        "short_name": "BCEAO",
        "publisher": "BCEAO",
        "url": "https://www.bceao.int",
        "source_type": "central_bank",
        "priority": 1,
        "country_code": None,
        "language": "fr",
        "description": "Banque centrale commune aux huit pays de l'UMOA. Source primaire pour les statistiques monétaires, bancaires et financières de la zone.",
        "is_active": True,
    },
    {
        "name": "Commission Bancaire de l'Union Monétaire Ouest Africaine",
        "short_name": "CB-UMOA",
        "publisher": "Commission Bancaire de l'UMOA",
        "url": "https://www.cb-umoa.org",
        "source_type": "regulatory",
        "priority": 1,
        "country_code": None,
        "language": "fr",
        "description": "Organe de supervision bancaire de l'UMOA. Publie les rapports annuels sur la situation du système bancaire et les listes des établissements agréés.",
        "is_active": True,
    },
]

def upgrade() -> None:
    for source in sources:
        op.execute(
            sa.text(
                """
                INSERT INTO sources (id, name, short_name, publisher, url, source_type, priority, country_code, language, description, is_active, created_at, updated_at)
                SELECT :id, :name, :short_name, :publisher, :url, :source_type, :priority, :country_code, :language, :description, :is_active, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM sources WHERE short_name = :short_name
                )
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                name=source["name"],
                short_name=source["short_name"],
                publisher=source["publisher"],
                url=source["url"],
                source_type=source["source_type"],
                priority=source["priority"],
                country_code=source["country_code"],
                language=source["language"],
                description=source["description"],
                is_active=source["is_active"]
            )
        )

def downgrade() -> None:
    short_names = [s["short_name"] for s in sources]
    op.execute(
        sa.text("DELETE FROM sources WHERE short_name = ANY(:short_names)")
        .bindparams(sa.bindparam("short_names", value=short_names, type_=postgresql.ARRAY(sa.String)))
    )
