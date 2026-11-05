"""Automated deal collection: debt / equity split, field-level excerpts, DFI sources, checkpoints

Additive migration:
- deals: debt_amount, equity_amount (> 0, NULL unless published as such), debt_type (closed list);
- deal_field_sources: excerpt (the quotation attesting THIS field);
- deal_sources: source class 'dfi_official' (disclosure on IFC / BOAD / Proparco's own domain);
- deal_field_sources: debt_amount, equity_amount, debt_type join the provenance vocabulary;
- ingestion_runs: deal_summary (per-source report of the deal collection phase);
- new table deal_collection_checkpoints (what a collector already read: source, url, lastmod, outcome);
- sources: IFC, BOAD and Proparco (development_institution), inserted only when absent.
Validation flag codes live in the importer schema (no CHECK constraint), nothing to migrate for them.
Downgrade is refused while a row uses the new columns or vocabulary (nothing is deleted to make it pass).

Revision ID: 0020_deal_collection
Revises: 0019_fascicle_corroboration
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0020_deal_collection"
down_revision = "0019_fascicle_corroboration"
branch_labels = None
depends_on = None

OLD_SOURCE_CLASSES = (
    "primary_regulatory", "primary_market", "issuer_official", "issuer_press_release", "regulator_index",
    "press_reported",
)
NEW_SOURCE_CLASSES = OLD_SOURCE_CLASSES + ("dfi_official",)
OLD_FIELDS = (
    "title", "deal_type", "country_code", "sector", "project_name", "amount", "amount_original", "currency",
    "unit", "interest_rate", "interest_rate_type", "benchmark", "spread_bps", "maturity_months",
    "grace_period_months", "fees", "guarantees", "announcement_date", "signing_date", "financial_close_date",
    "closing_date", "instrument_type", "isin", "auction_reference", "auction_date", "value_date",
    "maturity_date", "yield_rate", "use_of_proceeds", "use_of_proceeds_categories", "filing_agent_raw",
)
NEW_FIELDS = OLD_FIELDS + ("debt_amount", "equity_amount", "debt_type")
DEBT_TYPES = ("senior_loan", "subordinated_loan", "mezzanine", "convertible", "credit_line", "guarantee", "bond")
OUTCOMES = (
    "produced", "already_imported", "out_of_scope", "not_a_deal", "refused", "import_refused", "fetch_failed",
    "restricted", "error",
)
DFI_SOURCES = [
    {
        "name": "International Finance Corporation",
        "short_name": "IFC",
        "publisher": "IFC (World Bank Group)",
        "url": "https://disclosures.ifc.org",
        "description": "Divulgations publiques des projets de la SFI (Summary of Investment Information) : "
                       "contrepartie, pays, statut, investissement approuvé par le Conseil.",
    },
    {
        "name": "Banque Ouest Africaine de Développement",
        "short_name": "BOAD",
        "publisher": "BOAD",
        "url": "https://www.boad.org",
        "description": "Projets approuvés publiés par la BOAD : intitulé, date, montant, pays, secteur.",
    },
    {
        "name": "Proparco",
        "short_name": "Proparco",
        "publisher": "Proparco (Groupe AFD)",
        "url": "https://www.proparco.fr",
        "description": "Carte des projets Proparco : date de signature, localisation, outils et montant du financement, client.",
    },
]


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _replace_check(name: str, table: str, condition: str) -> None:
    op.drop_constraint(name, table, type_="check")
    op.create_check_constraint(name, table, condition)


def upgrade() -> None:
    op.add_column("deals", sa.Column("debt_amount", sa.Numeric(24, 6), nullable=True))
    op.add_column("deals", sa.Column("equity_amount", sa.Numeric(24, 6), nullable=True))
    op.add_column("deals", sa.Column("debt_type", sa.String(30), nullable=True))
    op.create_check_constraint("ck_deals_debt_amount_positive", "deals", "debt_amount IS NULL OR debt_amount > 0")
    op.create_check_constraint("ck_deals_equity_amount_positive", "deals",
                               "equity_amount IS NULL OR equity_amount > 0")
    op.create_check_constraint("ck_deals_debt_type", "deals", f"debt_type IS NULL OR debt_type IN ({_in(DEBT_TYPES)})")

    op.add_column("deal_field_sources", sa.Column("excerpt", sa.Text(), nullable=True))
    _replace_check("ck_deal_field_sources_field", "deal_field_sources", f"field_name IN ({_in(NEW_FIELDS)})")
    _replace_check("ck_deal_sources_source_class", "deal_sources",
                   f"source_class IS NULL OR source_class IN ({_in(NEW_SOURCE_CLASSES)})")

    op.add_column("ingestion_runs", sa.Column("deal_summary", postgresql.JSONB(), nullable=True))

    op.create_table(
        "deal_collection_checkpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_key", sa.String(30), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("lastmod", sa.String(40), nullable=True),
        sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("source_key", "url", name="uq_deal_collection_checkpoints_source_url"),
        sa.CheckConstraint(f"outcome IN ({_in(OUTCOMES)})", name="ck_deal_collection_checkpoints_outcome"),
    )
    op.create_index("ix_deal_collection_checkpoints_source", "deal_collection_checkpoints", ["source_key"])

    for src in DFI_SOURCES:
        op.execute(
            sa.text(
                """
                INSERT INTO sources (id, name, short_name, publisher, url, source_type, priority, country_code,
                                     language, description, is_active, created_at, updated_at)
                SELECT :id, :name, :short_name, :publisher, :url, 'development_institution', 1, NULL,
                       :language, :description, true, NOW(), NOW()
                WHERE NOT EXISTS (SELECT 1 FROM sources WHERE short_name = :short_name)
                """
            ).bindparams(id=str(uuid.uuid4()), language="en" if src["short_name"] == "IFC" else "fr", **src)
        )


def downgrade() -> None:
    bind = op.get_bind()
    short_names = [s["short_name"] for s in DFI_SOURCES]
    checks = {
        "deals using the debt / equity columns": (
            "SELECT count(*) FROM deals WHERE debt_amount IS NOT NULL OR equity_amount IS NOT NULL "
            "OR debt_type IS NOT NULL"
        ),
        "field sources carrying an excerpt or a new field": (
            f"SELECT count(*) FROM deal_field_sources WHERE excerpt IS NOT NULL OR field_name NOT IN ({_in(OLD_FIELDS)})"
        ),
        "deal sources of class dfi_official": "SELECT count(*) FROM deal_sources WHERE source_class = 'dfi_official'",
        "documents or deal sources of the IFC / BOAD / Proparco sources": (
            "SELECT (SELECT count(*) FROM documents d JOIN sources s ON s.id = d.source_id "
            "        WHERE s.short_name = ANY(:names)) "
            "     + (SELECT count(*) FROM deal_sources ds JOIN sources s ON s.id = ds.source_id "
            "        WHERE s.short_name = ANY(:names))"
        ),
    }
    for label, sql in checks.items():
        used = bind.execute(sa.text(sql).bindparams(sa.bindparam("names", value=short_names,
                                                                  type_=postgresql.ARRAY(sa.String)))
                            if ":names" in sql else sa.text(sql)).scalar()
        if used:
            raise RuntimeError(f"downgrade of 0020 refused: {used} {label} (dropping them would lose data)")

    op.execute(sa.text("DELETE FROM sources WHERE short_name = ANY(:names)").bindparams(
        sa.bindparam("names", value=short_names, type_=postgresql.ARRAY(sa.String))))
    op.drop_index("ix_deal_collection_checkpoints_source", table_name="deal_collection_checkpoints")
    op.drop_table("deal_collection_checkpoints")
    op.drop_column("ingestion_runs", "deal_summary")
    _replace_check("ck_deal_sources_source_class", "deal_sources",
                   f"source_class IS NULL OR source_class IN ({_in(OLD_SOURCE_CLASSES)})")
    _replace_check("ck_deal_field_sources_field", "deal_field_sources", f"field_name IN ({_in(OLD_FIELDS)})")
    op.drop_column("deal_field_sources", "excerpt")
    op.drop_constraint("ck_deals_debt_type", "deals", type_="check")
    op.drop_constraint("ck_deals_equity_amount_positive", "deals", type_="check")
    op.drop_constraint("ck_deals_debt_amount_positive", "deals", type_="check")
    op.drop_column("deals", "debt_type")
    op.drop_column("deals", "equity_amount")
    op.drop_column("deals", "debt_amount")
