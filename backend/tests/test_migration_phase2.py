"""
UMOA Banking Intelligence — Phase 2 Tests (Alembic migrations)

These tests validate the Alembic migration chain WITHOUT requiring a live
PostgreSQL instance (the CI/dev environment may not have a database).

Strategy:
  - Import the migration modules and inspect the SQLAlchemy objects they use.
  - Render the full migration chain to PostgreSQL DDL using Alembic's
    *offline* mode (``alembic upgrade head --sql``) and assert that every
    expected table, foreign key, unique constraint and CHECK constraint is
    present in the generated SQL.
  - Assert the seed migration uses exactly the 26 canonical metrics from
    ``app.constants.metrics`` (single source of truth) and is idempotent.

Reference: docs/specification-v1.md sections 6, 10, 12, 13, 14, 15, 22, 23.
"""

from __future__ import annotations

import io
import re
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any

import pytest

from app.constants.metrics import V1_METRIC_CODES, V1_METRICS

# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parents[1]
VERSIONS_DIR = BACKEND_DIR / "migrations" / "versions"

EXPECTED_TABLES = [
    "countries",
    "sources",
    "banking_groups",
    "institutions",
    "metric_definitions",
    "documents",
    "financial_data",
]


def _load_migration_module(filename: str) -> Any:
    """Load a migration file by path (versions/ is not an importable package)."""
    import importlib.util

    path = VERSIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(filename[:-3], path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _render_offline_sql() -> str:
    """
    Render the whole migration chain to PostgreSQL DDL via Alembic offline mode.

    Uses a temporary in-memory config so no environment variables or database
    connection are required.
    """
    from alembic import command
    from alembic.config import Config as AlembicConfig

    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    # A synthetic URL is enough for offline rendering; no connection is opened.
    cfg.set_main_option(
        "sqlalchemy.url",
        "postgresql+asyncpg://user:pass@localhost:5432/umoa_banking",
    )

    buffer = io.StringIO()
    cfg.output_buffer = buffer
    with redirect_stdout(buffer):
        command.upgrade(cfg, "head", sql=True)
    return buffer.getvalue()


# ----------------------------------------------------------------------
# Migration files exist & are wired
# ----------------------------------------------------------------------


def test_migration_files_exist() -> None:
    names = {p.name for p in VERSIONS_DIR.glob("*.py")}
    assert "0001_initial_schema.py" in names
    assert "0002_seed_metric_catalogue.py" in names


def test_migration_chain_is_linear() -> None:
    m1 = _load_migration_module("0001_initial_schema.py")
    m2 = _load_migration_module("0002_seed_metric_catalogue.py")

    assert m1.down_revision is None
    assert m2.down_revision == m1.revision
    assert m1.revision == "0001_initial_schema"
    assert m2.revision == "0002_seed_metric_catalogue"


# ----------------------------------------------------------------------
# Schema: tables, FK, UNIQUE, CHECK constraints in rendered SQL
# ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def offline_sql() -> str:
    return _render_offline_sql()


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_all_tables_created(offline_sql: str, table: str) -> None:
    assert re.search(rf"CREATE TABLE {table} \(", offline_sql), f"missing table {table}"


@pytest.mark.parametrize(
    "constraint",
    [
        "uq_countries_code",
        "uq_metric_definitions_code",
        "fk_banking_groups_source_id_sources",
        "fk_institutions_country_id_countries",
        "fk_institutions_banking_group_id_banking_groups",
        "fk_documents_institution_id_institutions",
        "fk_documents_source_id_sources",
        "fk_financial_data_institution_id_institutions",
        "fk_financial_data_source_id_sources",
        "fk_financial_data_document_id_documents",
        "fk_financial_data_metric_code_metric_definitions",
    ],
)
def test_named_constraints_present(offline_sql: str, constraint: str) -> None:
    assert constraint in offline_sql, f"missing constraint {constraint}"


@pytest.mark.parametrize(
    "check_name",
    [
        "ck_metric_definitions_statement_type",
        "ck_metric_definitions_category",
        "ck_metric_definitions_value_type",
        "ck_metric_definitions_currency_type",
        "ck_documents_document_type",
        "ck_documents_download_status",
        "ck_documents_extraction_status",
        "ck_documents_period_type",
        "ck_documents_page_count_positive",
        "ck_financial_data_scope",
        "ck_financial_data_period_type",
        "ck_financial_data_extraction_method",
        "ck_financial_data_status",
        "ck_financial_data_confidence_range",
        "ck_financial_data_page_number_positive",
        "ck_financial_data_reviewed_requires_normalized",
        "ck_financial_data_verified_requires_validator",
    ],
)
def test_check_constraints_present(offline_sql: str, check_name: str) -> None:
    assert check_name in offline_sql, f"missing CHECK constraint {check_name}"


def test_scope_check_only_allows_individual_and_consolidated(offline_sql: str) -> None:
    assert "scope IN ('individual', 'consolidated')" in offline_sql
    # Forbidden V1 scopes must not be accepted by the constraint.
    for forbidden in ("'country'", "'sector'", "'umoa'"):
        # The only place these would appear is inside the scope CHECK; ensure
        # they are not part of the scope constraint expression.
        assert f"scope IN ({forbidden}" not in offline_sql


def test_no_user_table_created(offline_sql: str) -> None:
    # No User table in V1 (verified_by is a plain string column).
    assert not re.search(r"CREATE TABLE users \(", offline_sql)
    assert "verified_by VARCHAR(100)" in offline_sql


def test_file_hash_unique_and_nullable(offline_sql: str) -> None:
    assert "file_hash VARCHAR(64)" in offline_sql
    # UNIQUE on file_hash rendered without a name => "UNIQUE (file_hash)"
    assert "UNIQUE (file_hash)" in offline_sql


def test_numeric_columns_precision(offline_sql: str) -> None:
    assert "value_normalized NUMERIC(24, 6)" in offline_sql
    assert "confidence_score NUMERIC(4, 3)" in offline_sql


# ----------------------------------------------------------------------
# Seed: exactly the 26 canonical metrics, idempotent
# ----------------------------------------------------------------------


def test_catalogue_has_26_metrics() -> None:
    assert len(V1_METRICS) == 26
    assert len(V1_METRIC_CODES) == 26
    assert len(set(V1_METRIC_CODES)) == 26


def test_seed_inserts_26_metric_rows(offline_sql: str) -> None:
    # Count value tuples in the metric_definitions INSERT statement.
    match = re.search(
        r"INSERT INTO metric_definitions \(.*?\) VALUES (.*?) ON CONFLICT",
        offline_sql,
        re.DOTALL,
    )
    assert match, "seed INSERT INTO metric_definitions not found"
    values_blob = match.group(1)
    # Each metric row starts with a quoted code, e.g. ('total_actifs', ...
    row_count = len(re.findall(r"\('([a-z_]+)',", values_blob))
    assert row_count == 26, f"expected 26 seeded rows, found {row_count}"


def test_seed_is_idempotent(offline_sql: str) -> None:
    assert "ON CONFLICT (code) DO NOTHING" in offline_sql


def test_seed_contains_all_canonical_codes(offline_sql: str) -> None:
    for code in V1_METRIC_CODES:
        assert f"('{code}'," in offline_sql, f"metric {code} not seeded"


def test_seed_downgrade_deletes_only_catalogue_codes() -> None:
    src = (VERSIONS_DIR / "0002_seed_metric_catalogue.py").read_text(encoding="utf-8")
    assert "DELETE FROM metric_definitions WHERE code = ANY(:codes)" in src
    assert "V1_METRIC_CODES" in src
