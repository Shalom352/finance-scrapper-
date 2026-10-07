"""Scope corroborated by the BCEAO fascicle (Phase 22)

Adds the scope reason code 'scope_corroborated_by_regulatory_fascicle' to the closed list:
an institution document value equal to the BCEAO fascicle value for the same entity / metric /
year inherits the fascicle's per-entity scope (class C).

Downgrade is refused while a row uses the new code.

Revision ID: 0019_fascicle_corroboration
Revises: 0018_automatic_validation
"""

import sqlalchemy as sa
from alembic import op

revision = "0019_fascicle_corroboration"
down_revision = "0018_automatic_validation"
branch_labels = None
depends_on = None

OLD_CODES = (
    "scope_explicit_page",
    "scope_explicit_document_title",
    "scope_inferred_from_regulatory_per_entity_reporting_convention",
    "scope_mentioned_elsewhere_only",
    "scope_not_stated",
    "scope_conflicting_mentions",
    "document_not_machine_readable",
    "scope_not_applicable",
)
NEW_CODE = "scope_corroborated_by_regulatory_fascicle"


def _in(values) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _constraint(codes) -> None:
    op.drop_constraint("ck_financial_data_scope_reason_code", "financial_data", type_="check")
    op.create_check_constraint(
        "ck_financial_data_scope_reason_code",
        "financial_data",
        f"scope_reason_code IS NULL OR scope_reason_code IN ({_in(codes)})",
    )


def upgrade() -> None:
    _constraint(OLD_CODES + (NEW_CODE,))


def downgrade() -> None:
    used = op.get_bind().execute(
        sa.text("SELECT count(*) FROM financial_data WHERE scope_reason_code = :c"), {"c": NEW_CODE}
    ).scalar()
    if used:
        raise RuntimeError(f"downgrade of 0019 refused: {used} row(s) use '{NEW_CODE}'")
    _constraint(OLD_CODES)
