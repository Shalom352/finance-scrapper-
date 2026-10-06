"""Seed Markets and Public Debt infrastructure (BRVM & UMOA-Titres).

Phase 14 — Step 2:
- Official market sources: BRVM, UMOA-Titres, AMF-UMOA, DC/BR;
- Core market entities: Stock Exchange (BRVM), Central Depository (DC/BR),
  Public Debt Agency (UMOA-Titres), Regional Market Authority (AMF-UMOA),
  and the 8 Sovereign Treasuries (BJ, BF, CI, GW, ML, NE, SN, TG);
- Institutional relationships: Supervision and Clearing links;
- Official market and sovereign debt metrics catalogue in `metric_definitions`.

Revision ID: 0010_seed_markets_and_public_debt
Revises: 0009_unified_financial_intelligence
"""

import uuid
from typing import Any
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.constants.markets import (
    MARKET_METRIC_CODES,
    MARKET_METRICS,
    MARKET_OFFICIAL_SOURCES,
)

revision = "0010_seed_markets_and_public_debt"
down_revision = "0009_unified_financial_intelligence"
branch_labels = None
depends_on = None

SOVEREIGN_TREASURIES = [
    {"code": "BJ", "name": "Trésor Public du Bénin", "short_name": "Trésor Bénin"},
    {"code": "BF", "name": "Trésor Public du Burkina Faso", "short_name": "Trésor Burkina"},
    {"code": "CI", "name": "Trésor Public de Côte d'Ivoire", "short_name": "Trésor Côte d'Ivoire"},
    {"code": "GW", "name": "Trésor Public de Guinée-Bissau", "short_name": "Trésor Guinée-Bissau"},
    {"code": "ML", "name": "Trésor Public du Mali", "short_name": "Trésor Mali"},
    {"code": "NE", "name": "Trésor Public du Niger", "short_name": "Trésor Niger"},
    {"code": "SN", "name": "Trésor Public du Sénégal", "short_name": "Trésor Sénégal"},
    {"code": "TG", "name": "Trésor Public du Togo", "short_name": "Trésor Togo"},
]

CORE_MARKET_ENTITIES = [
    {
        "canonical_name": "Bourse Régionale des Valeurs Mobilières",
        "short_name": "BRVM",
        "entity_class": "market_infrastructure",
        "entity_type": "stock_exchange",
        "country_code": "CI",
        "description": "Bourse de valeurs mobilières de l'UMOA.",
    },
    {
        "canonical_name": "Dépositaire Central / Banque de Règlement",
        "short_name": "DC/BR",
        "entity_class": "market_infrastructure",
        "entity_type": "central_depository",
        "country_code": "CI",
        "description": "Dépositaire central et banque de règlement du marché financier régional.",
    },
    {
        "canonical_name": "Agence UMOA-Titres",
        "short_name": "UMOA-Titres",
        "entity_class": "market_infrastructure",
        "entity_type": "other",
        "country_code": "SN",
        "description": "Agence régionale pour l'émission et la gestion des titres de dettes publiques.",
    },
    {
        "canonical_name": "Autorité des Marchés Financiers de l'UMOA",
        "short_name": "AMF-UMOA",
        "entity_class": "regulator",
        "entity_type": "other",
        "country_code": "CI",
        "description": "Régulateur du marché financier régional de l'UMOA.",
    },
]

_METRIC_COLUMNS = (
    "code",
    "label_fr",
    "label_en",
    "definition_fr",
    "definition_en",
    "statement_type",
    "category",
    "value_type",
    "currency_type",
    "sector",
    "metric_family",
    "is_calculated",
    "is_active",
    "is_debt_related",
    "display_order",
    "description_synth",
)


def upgrade() -> None:
    # 1. Seed official market sources
    for src in MARKET_OFFICIAL_SOURCES:
        op.execute(
            sa.text(
                """
                INSERT INTO sources (id, name, short_name, publisher, url, source_type, priority, country_code, language, description, is_active, created_at, updated_at)
                SELECT :id, :name, :short_name, :publisher, :url, :source_type, :priority, :country_code, :language, :description, :is_active, NOW(), NOW()
                WHERE NOT EXISTS (
                    SELECT 1 FROM sources WHERE short_name = :short_name
                );
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                name=src["name"],
                short_name=src["short_name"],
                publisher=src["publisher"],
                url=src["url"],
                source_type=src["source_type"],
                priority=src["priority"],
                country_code=src["country_code"],
                language=src["language"],
                description=src["description"],
                is_active=src["is_active"],
            )
        )

    # 2. Seed core market entities
    for ent in CORE_MARKET_ENTITIES:
        op.execute(
            sa.text(
                """
                INSERT INTO entities (id, entity_class, entity_type, canonical_name, short_name, country_id, status, description, created_at, updated_at)
                SELECT :id, :entity_class, :entity_type, :canonical_name, :short_name, countries.id, 'active', :description, NOW(), NOW()
                FROM countries
                WHERE countries.code = :country_code
                  AND NOT EXISTS (
                      SELECT 1 FROM entities WHERE canonical_name = :canonical_name
                  );
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                entity_class=ent["entity_class"],
                entity_type=ent["entity_type"],
                canonical_name=ent["canonical_name"],
                short_name=ent["short_name"],
                country_code=ent["country_code"],
                description=ent["description"],
            )
        )

    # 3. Seed sovereign entities (Treasuries of the 8 countries)
    for sov in SOVEREIGN_TREASURIES:
        op.execute(
            sa.text(
                """
                INSERT INTO entities (id, entity_class, entity_type, canonical_name, short_name, country_id, status, description, created_at, updated_at)
                SELECT :id, 'sovereign_entity', 'sovereign_state', :canonical_name, :short_name, countries.id, 'active', 'Trésor public national émetteur de titres publics souverains.', NOW(), NOW()
                FROM countries
                WHERE countries.code = :country_code
                  AND NOT EXISTS (
                      SELECT 1 FROM entities WHERE canonical_name = :canonical_name
                  );
                """
            ).bindparams(
                id=str(uuid.uuid4()),
                canonical_name=sov["name"],
                short_name=sov["short_name"],
                country_code=sov["code"],
            )
        )

    # 4. Seed market institutional relationships
    # AMF-UMOA -> BRVM (supervises)
    op.execute(
        """
        INSERT INTO entity_relationships (id, source_entity_id, target_entity_id, relationship_type, role_context, is_current, created_at, updated_at)
        SELECT
            substr(md5(amf.id || brvm.id || 'supervises'), 1, 36),
            amf.id,
            brvm.id,
            'supervises',
            'market_regulator',
            true,
            NOW(),
            NOW()
        FROM entities amf, entities brvm
        WHERE amf.canonical_name = 'Autorité des Marchés Financiers de l''UMOA'
          AND brvm.canonical_name = 'Bourse Régionale des Valeurs Mobilières'
          AND NOT EXISTS (
              SELECT 1 FROM entity_relationships
              WHERE source_entity_id = amf.id AND target_entity_id = brvm.id AND relationship_type = 'supervises'
          );
        """
    )
    # AMF-UMOA -> DC/BR (supervises)
    op.execute(
        """
        INSERT INTO entity_relationships (id, source_entity_id, target_entity_id, relationship_type, role_context, is_current, created_at, updated_at)
        SELECT
            substr(md5(amf.id || dcbr.id || 'supervises'), 1, 36),
            amf.id,
            dcbr.id,
            'supervises',
            'market_regulator',
            true,
            NOW(),
            NOW()
        FROM entities amf, entities dcbr
        WHERE amf.canonical_name = 'Autorité des Marchés Financiers de l''UMOA'
          AND dcbr.canonical_name = 'Dépositaire Central / Banque de Règlement'
          AND NOT EXISTS (
              SELECT 1 FROM entity_relationships
              WHERE source_entity_id = amf.id AND target_entity_id = dcbr.id AND relationship_type = 'supervises'
          );
        """
    )
    # BRVM -> DC/BR (cleared_by_depository)
    op.execute(
        """
        INSERT INTO entity_relationships (id, source_entity_id, target_entity_id, relationship_type, role_context, is_current, created_at, updated_at)
        SELECT
            substr(md5(brvm.id || dcbr.id || 'cleared_by_depository'), 1, 36),
            brvm.id,
            dcbr.id,
            'cleared_by_depository',
            'settlement_and_custody',
            true,
            NOW(),
            NOW()
        FROM entities brvm, entities dcbr
        WHERE brvm.canonical_name = 'Bourse Régionale des Valeurs Mobilières'
          AND dcbr.canonical_name = 'Dépositaire Central / Banque de Règlement'
          AND NOT EXISTS (
              SELECT 1 FROM entity_relationships
              WHERE source_entity_id = brvm.id AND target_entity_id = dcbr.id AND relationship_type = 'cleared_by_depository'
          );
        """
    )

    # 5. Seed market & sovereign debt metrics
    metric_table = sa.table(
        "metric_definitions",
        sa.column("code", sa.String),
        sa.column("label_fr", sa.String),
        sa.column("label_en", sa.String),
        sa.column("definition_fr", sa.Text),
        sa.column("definition_en", sa.Text),
        sa.column("statement_type", sa.String),
        sa.column("category", sa.String),
        sa.column("value_type", sa.String),
        sa.column("currency_type", sa.String),
        sa.column("sector", sa.String),
        sa.column("metric_family", sa.String),
        sa.column("is_calculated", sa.Boolean),
        sa.column("is_active", sa.Boolean),
        sa.column("is_debt_related", sa.Boolean),
        sa.column("display_order", sa.Integer),
        sa.column("description_synth", sa.Text),
        sa.column("id", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    rows: list[dict[str, Any]] = []
    for metric in MARKET_METRICS:
        row: dict[str, Any] = {col: metric.get(col) for col in _METRIC_COLUMNS}
        row["id"] = str(uuid.uuid4())
        row["created_at"] = sa.func.now()
        row["updated_at"] = sa.func.now()
        rows.append(row)

    insert_stmt = postgresql.insert(metric_table).values(rows).on_conflict_do_nothing(
        index_elements=["code"]
    )
    op.execute(insert_stmt)


def downgrade() -> None:
    source_short_names = [s["short_name"] for s in MARKET_OFFICIAL_SOURCES]

    # 1. Clean up any dependent test rows referencing market metrics, sources, entities
    op.execute(
        sa.text(
            """
            DELETE FROM financial_data
            WHERE metric_code = ANY(:codes)
               OR source_id IN (SELECT id FROM sources WHERE short_name = ANY(:short_names));
            """
        ).bindparams(
            sa.bindparam("codes", value=list(MARKET_METRIC_CODES), type_=postgresql.ARRAY(sa.String)),
            sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)),
        )
    )
    op.execute(
        sa.text(
            """
            DELETE FROM deal_field_sources
            WHERE deal_source_id IN (
                SELECT id FROM deal_sources WHERE source_id IN (SELECT id FROM sources WHERE short_name = ANY(:short_names))
            );
            """
        ).bindparams(sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)))
    )
    op.execute(
        sa.text(
            """
            DELETE FROM deal_participants
            WHERE deal_source_id IN (
                SELECT id FROM deal_sources WHERE source_id IN (SELECT id FROM sources WHERE short_name = ANY(:short_names))
            );
            """
        ).bindparams(sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)))
    )
    op.execute(
        sa.text(
            """
            DELETE FROM deal_sources
            WHERE source_id IN (SELECT id FROM sources WHERE short_name = ANY(:short_names));
            """
        ).bindparams(sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)))
    )
    op.execute(
        sa.text(
            """
            DELETE FROM documents
            WHERE source_id IN (SELECT id FROM sources WHERE short_name = ANY(:short_names));
            """
        ).bindparams(sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)))
    )

    # 2. Delete seeded market metrics
    op.execute(
        sa.text(
            "DELETE FROM metric_definitions WHERE code = ANY(:codes);"
        ).bindparams(sa.bindparam("codes", value=list(MARKET_METRIC_CODES), type_=postgresql.ARRAY(sa.String)))
    )

    # 3. Delete market relationships
    op.execute(
        """
        DELETE FROM entity_relationships
        WHERE source_entity_id IN (
            SELECT id FROM entities WHERE canonical_name IN ('Autorité des Marchés Financiers de l''UMOA', 'Bourse Régionale des Valeurs Mobilières')
        );
        """
    )

    # 4. Delete seeded market & sovereign entities
    all_entity_names = [e["canonical_name"] for e in CORE_MARKET_ENTITIES] + [s["name"] for s in SOVEREIGN_TREASURIES]
    op.execute(
        sa.text(
            "DELETE FROM entities WHERE canonical_name = ANY(:names);"
        ).bindparams(sa.bindparam("names", value=all_entity_names, type_=postgresql.ARRAY(sa.String)))
    )

    # 5. Delete seeded market sources
    op.execute(
        sa.text(
            "DELETE FROM sources WHERE short_name = ANY(:short_names);"
        ).bindparams(sa.bindparam("short_names", value=source_short_names, type_=postgresql.ARRAY(sa.String)))
    )
