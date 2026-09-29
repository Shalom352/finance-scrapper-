"""seed the 26 official V1 metrics into metric_definitions

Inserts exactly the metric catalogue defined in ``app.constants.metrics``
(the single source of truth). No metric is invented, renamed or removed.

Idempotency:
  - uses ``ON CONFLICT (code) DO NOTHING`` so the migration can be re-run
    from a fresh database and is safe if a code already exists.
  - existing curated rows are never overwritten.

Downgrade removes only the 26 catalogue codes (no other row is touched).

Reference: docs/specification-v1.md sections 7, 8, 9.

Revision ID: 0002_seed_metric_catalogue
Revises: 0001_initial_schema
Create Date: 2026-09-21

"""

import uuid
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.constants.metrics import V1_METRIC_CODES, V1_METRICS

revision: str = "0002_seed_metric_catalogue"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Catalogue columns to seed; id and audit timestamps are added per row in upgrade()
# (the schema has no server-side defaults for them, as in 0003 / 0004).
_SEED_COLUMNS = (
    "code",
    "label_fr",
    "label_en",
    "definition_fr",
    "definition_en",
    "statement_type",
    "category",
    "value_type",
    "currency_type",
    "is_calculated",
    "is_active",
    "is_debt_related",
    "display_order",
    "description_synth",
)


def upgrade() -> None:
    # Guard: the catalogue must contain exactly the 26 frozen V1 metrics.
    assert len(V1_METRICS) == 26, "V1 metric catalogue must contain 26 metrics"
    assert len(set(V1_METRIC_CODES)) == 26, "V1 metric codes must be unique"

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
    for metric in V1_METRICS:
        row: dict[str, Any] = {col: metric.get(col) for col in _SEED_COLUMNS}
        row["id"] = str(uuid.uuid4())
        row["created_at"] = sa.func.now()
        row["updated_at"] = sa.func.now()
        rows.append(row)

    insert_stmt = postgresql.insert(metric_table).values(rows).on_conflict_do_nothing(
        index_elements=["code"]
    )
    op.execute(insert_stmt)


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM metric_definitions WHERE code = ANY(:codes)"
        ).bindparams(sa.bindparam("codes", value=list(V1_METRIC_CODES), type_=postgresql.ARRAY(sa.String)))
    )
