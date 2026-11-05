"""Syndication tracker: Excel imports, syndication terms per counterparty, internal contacts

Additive migration for TOMASTEED's internal "Suivi de Syndication" (docs/syndication.md):
- new table syndication_imports (each upload: preview plan, then applied; file SHA-256 and date);
- mandates: stage_raw, country_code_raw, last_updated_from_file, origin, import_batch_id,
  excel_snapshot (values of the last import, for the 3-way merge), manually_edited_at;
- mandate_counterparties: lender_type, appetite, amount_text, rate_text, arrangement_fee_text,
  commitment_fee_text, maturity_text, dossier_status_raw, nda_sent_on, nda_received_on, next_steps,
  origin, import_batch_id;
- new table institution_contacts (internal CRM: personal data, served by internal routes only).
Existing rows keep origin = 'manual'. Downgrade is refused while the new data exists.

Revision ID: 0022_syndication
Revises: 0021_press_source
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0022_syndication"
down_revision = "0021_press_source"
branch_labels = None
depends_on = None

LENDER_TYPES = ("dfi", "bank", "guarantor", "investor", "other")
ORIGINS = ("excel_import", "manual")
STATUSES = ("preview", "applied", "discarded")


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "syndication_imports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("file_sha256", sa.String(64), nullable=False),
        sa.Column("file_updated_on", sa.Date(), nullable=True),
        sa.Column("status", sa.String(15), nullable=False),
        sa.Column("actor", sa.String(255), nullable=False),
        sa.Column("plan", postgresql.JSONB(), nullable=False),
        sa.Column("counts", postgresql.JSONB(), nullable=True),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=True),
        *_audit_columns(),
        sa.CheckConstraint(f"status IN ({_in(STATUSES)})", name="ck_syndication_imports_status"),
    )
    op.create_index("ix_syndication_imports_sha", "syndication_imports", ["file_sha256"])
    # The same file is applied once (a preview of an already applied file is refused by the service).
    op.create_index("uq_syndication_imports_applied_sha", "syndication_imports", ["file_sha256"], unique=True,
                    postgresql_where=sa.text("status = 'applied'"))

    for col in (
        sa.Column("stage_raw", sa.Text(), nullable=True),
        sa.Column("country_code_raw", sa.String(10), nullable=True),
        sa.Column("last_updated_from_file", sa.Date(), nullable=True),
        sa.Column("origin", sa.String(15), nullable=False, server_default="manual"),
        sa.Column("import_batch_id", sa.String(36), sa.ForeignKey("syndication_imports.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("excel_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("manually_edited_at", sa.DateTime(timezone=True), nullable=True),
    ):
        op.add_column("mandates", col)
    op.create_check_constraint("ck_mandates_origin", "mandates", f"origin IN ({_in(ORIGINS)})")

    for col in (
        sa.Column("lender_type", sa.String(15), nullable=True),
        sa.Column("appetite", sa.Boolean(), nullable=True),
        sa.Column("amount_text", sa.Text(), nullable=True),
        sa.Column("rate_text", sa.Text(), nullable=True),
        sa.Column("arrangement_fee_text", sa.Text(), nullable=True),
        sa.Column("commitment_fee_text", sa.Text(), nullable=True),
        sa.Column("maturity_text", sa.Text(), nullable=True),
        sa.Column("dossier_status_raw", sa.Text(), nullable=True),
        sa.Column("nda_sent_on", sa.Date(), nullable=True),
        sa.Column("nda_received_on", sa.Date(), nullable=True),
        sa.Column("next_steps", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(15), nullable=False, server_default="manual"),
        sa.Column("import_batch_id", sa.String(36), sa.ForeignKey("syndication_imports.id", ondelete="RESTRICT"),
                  nullable=True),
    ):
        op.add_column("mandate_counterparties", col)
    op.create_check_constraint("ck_mandate_counterparties_lender_type", "mandate_counterparties",
                               f"lender_type IS NULL OR lender_type IN ({_in(LENDER_TYPES)})")
    op.create_check_constraint("ck_mandate_counterparties_origin", "mandate_counterparties",
                               f"origin IN ({_in(ORIGINS)})")

    op.create_table(
        "institution_contacts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("contact_key", sa.String(400), nullable=False),
        sa.Column("institution_name", sa.String(255), nullable=False),
        sa.Column("institution_id", sa.String(36), sa.ForeignKey("institutions.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("entity_id", sa.String(36), sa.ForeignKey("entities.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("job_title", sa.Text(), nullable=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("phone", sa.Text(), nullable=True),
        sa.Column("last_interaction_on", sa.Date(), nullable=True),
        sa.Column("context", sa.Text(), nullable=True),
        sa.Column("mandate_id", sa.String(36), sa.ForeignKey("mandates.id", ondelete="RESTRICT"), nullable=True),
        sa.Column("dataroom_access", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(15), nullable=False, server_default="manual"),
        sa.Column("import_batch_id", sa.String(36), sa.ForeignKey("syndication_imports.id", ondelete="RESTRICT"),
                  nullable=True),
        sa.Column("excel_snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("manually_edited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        *_audit_columns(),
        sa.CheckConstraint(f"origin IN ({_in(ORIGINS)})", name="ck_institution_contacts_origin"),
        sa.UniqueConstraint("contact_key", name="uq_institution_contacts_key"),
    )
    op.create_index("ix_institution_contacts_institution", "institution_contacts", ["institution_id"])
    op.create_index("ix_institution_contacts_entity", "institution_contacts", ["entity_id"])
    op.create_index("ix_institution_contacts_mandate", "institution_contacts", ["mandate_id"])


def downgrade() -> None:
    bind = op.get_bind()
    checks = {
        "syndication imports": "SELECT count(*) FROM syndication_imports",
        "institution contacts": "SELECT count(*) FROM institution_contacts",
        "mandates or counterparties carrying syndication data": (
            "SELECT (SELECT count(*) FROM mandates WHERE origin <> 'manual' OR stage_raw IS NOT NULL "
            "        OR excel_snapshot IS NOT NULL OR manually_edited_at IS NOT NULL) "
            "     + (SELECT count(*) FROM mandate_counterparties WHERE origin <> 'manual' OR lender_type IS NOT NULL "
            "        OR appetite IS NOT NULL OR amount_text IS NOT NULL OR rate_text IS NOT NULL "
            "        OR dossier_status_raw IS NOT NULL OR next_steps IS NOT NULL)"
        ),
    }
    for label, sql in checks.items():
        used = bind.execute(sa.text(sql)).scalar()
        if used:
            raise RuntimeError(f"downgrade of 0022 refused: {used} {label} (dropping them would lose data)")
    op.drop_index("ix_institution_contacts_mandate", table_name="institution_contacts")
    op.drop_index("ix_institution_contacts_entity", table_name="institution_contacts")
    op.drop_index("ix_institution_contacts_institution", table_name="institution_contacts")
    op.drop_table("institution_contacts")
    op.drop_constraint("ck_mandate_counterparties_origin", "mandate_counterparties", type_="check")
    op.drop_constraint("ck_mandate_counterparties_lender_type", "mandate_counterparties", type_="check")
    for name in ("import_batch_id", "origin", "next_steps", "nda_received_on", "nda_sent_on", "dossier_status_raw",
                 "maturity_text", "commitment_fee_text", "arrangement_fee_text", "rate_text", "amount_text",
                 "appetite", "lender_type"):
        op.drop_column("mandate_counterparties", name)
    op.drop_constraint("ck_mandates_origin", "mandates", type_="check")
    for name in ("manually_edited_at", "excel_snapshot", "import_batch_id", "origin", "last_updated_from_file",
                 "country_code_raw", "stage_raw"):
        op.drop_column("mandates", name)
    op.drop_index("uq_syndication_imports_applied_sha", table_name="syndication_imports")
    op.drop_index("ix_syndication_imports_sha", table_name="syndication_imports")
    op.drop_table("syndication_imports")
