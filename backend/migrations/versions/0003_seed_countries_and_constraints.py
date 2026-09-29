"""Seed 8 UMOA countries and add CHECK constraints on sources and institutions.

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-28
"""
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_seed_countries_and_constraints"
down_revision = "0002_seed_metric_catalogue"
branch_labels = None
depends_on = None

countries = [
    {"code": "BJ", "name_fr": "Bénin", "name_en": "Benin", "flag_emoji": "🇧🇯", "capital_fr": "Porto-Novo", "capital_en": "Porto-Novo"},
    {"code": "BF", "name_fr": "Burkina Faso", "name_en": "Burkina Faso", "flag_emoji": "🇧🇫", "capital_fr": "Ouagadougou", "capital_en": "Ouagadougou"},
    {"code": "CI", "name_fr": "Côte d'Ivoire", "name_en": "Côte d'Ivoire", "flag_emoji": "🇨🇮", "capital_fr": "Yamoussoukro", "capital_en": "Yamoussoukro"},
    {"code": "GW", "name_fr": "Guinée-Bissau", "name_en": "Guinea-Bissau", "flag_emoji": "🇬🇼", "capital_fr": "Bissau", "capital_en": "Bissau"},
    {"code": "ML", "name_fr": "Mali", "name_en": "Mali", "flag_emoji": "🇲🇱", "capital_fr": "Bamako", "capital_en": "Bamako"},
    {"code": "NE", "name_fr": "Niger", "name_en": "Niger", "flag_emoji": "🇳🇪", "capital_fr": "Niamey", "capital_en": "Niamey"},
    {"code": "SN", "name_fr": "Sénégal", "name_en": "Senegal", "flag_emoji": "🇸🇳", "capital_fr": "Dakar", "capital_en": "Dakar"},
    {"code": "TG", "name_fr": "Togo", "name_en": "Togo", "flag_emoji": "🇹🇬", "capital_fr": "Lomé", "capital_en": "Lomé"},
]

def upgrade() -> None:
    # A. Add CHECK constraints
    op.create_check_constraint(
        "ck_sources_source_type",
        "sources",
        "source_type IN ('regulatory', 'central_bank', 'bank', 'banking_group', 'government', 'financial_market', 'secondary')"
    )
    op.create_check_constraint(
        "ck_institutions_status",
        "institutions",
        "status IN ('active', 'closed', 'in_liquidation', 'merged', 'unknown')"
    )
    op.create_check_constraint(
        "ck_institutions_institution_type",
        "institutions",
        "institution_type IN ('bank', 'microfinance', 'insurance', 'financial_holding', 'development_bank', 'other')"
    )

    # B. Seed the 8 UMOA countries
    for country in countries:
        op.execute(
            sa.text(
                """
                INSERT INTO countries (id, code, name_fr, name_en, flag_emoji, capital_fr, capital_en, is_active, created_at, updated_at)
                VALUES (:id, :code, :name_fr, :name_en, :flag_emoji, :capital_fr, :capital_en, :is_active, NOW(), NOW())
                ON CONFLICT (code) DO NOTHING
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                code=country["code"],
                name_fr=country["name_fr"],
                name_en=country["name_en"],
                flag_emoji=country["flag_emoji"],
                capital_fr=country["capital_fr"],
                capital_en=country["capital_en"],
                is_active=True
            )
        )

def downgrade() -> None:
    op.drop_constraint("ck_institutions_institution_type", "institutions", type_="check")
    op.drop_constraint("ck_institutions_status", "institutions", type_="check")
    op.drop_constraint("ck_sources_source_type", "sources", type_="check")

    codes = [c["code"] for c in countries]
    op.execute(
        sa.text("DELETE FROM countries WHERE code = ANY(:codes)")
        .bindparams(sa.bindparam("codes", value=codes, type_=postgresql.ARRAY(sa.String)))
    )
