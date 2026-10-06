"""
UMOA Banking Intelligence — Phase 1 tests (models + metric catalogue).

These tests are intentionally DB-free: they verify structural definitions
(imports, keys, relationships, constraints and catalogue integrity) without
requiring a live PostgreSQL connection.

Alembic/API integration tests belong to later phases.

Reference: docs/specification-v1.md sections 6, 7, 8, 12, 14.
"""

from typing import Any, cast

from sqlalchemy import CheckConstraint, Table, UniqueConstraint

from app.constants.metrics import (
    CATEGORIES,
    CURRENCY_TYPES,
    STATEMENT_TYPES,
    V1_METRIC_CODES,
    V1_METRICS,
    V1_METRICS_BY_CODE,
    VALUE_TYPES,
)
from app.db.base import Base
from app.models import Document, FinancialData, MetricDefinition


def _table(model: type[Any]) -> Table:
    """Return the underlying SQLAlchemy Table for a mapped class."""
    return cast(Table, model.__table__)


def _check_names(table: Table) -> set[str]:
    return {
        str(cons.name)
        for cons in table.constraints
        if isinstance(cons, CheckConstraint)
    }


def _unique_column_sets(table: Table) -> set[tuple[str, ...]]:
    return {
        tuple(col.name for col in cons.columns)
        for cons in table.constraints
        if isinstance(cons, UniqueConstraint)
    }


def _check_sql(table: Table, name: str) -> str:
    return next(
        str(cons.sqltext.text)
        for cons in table.constraints
        if isinstance(cons, CheckConstraint) and cons.name == name
    )


# ============================================================
# Imports & table registration
# ============================================================


def test_models_are_importable() -> None:
    """The three Phase-1 models must be importable from app.models."""
    assert MetricDefinition is not None
    assert Document is not None
    assert FinancialData is not None


def test_expected_tables_registered() -> None:
    """All Phase-1 tables must be registered on the shared metadata."""
    tables = set(Base.metadata.tables)
    assert "metric_definitions" in tables
    assert "documents" in tables
    assert "financial_data" in tables


def test_only_expected_new_tables_added() -> None:
    """No User table (and no V2/V3 table) is introduced in Phase 1."""
    assert "users" not in Base.metadata.tables
    assert "debt_instruments" not in Base.metadata.tables
    assert "covenants" not in Base.metadata.tables


# ============================================================
# Keys & relationships
# ============================================================


def test_metric_definition_code_is_unique() -> None:
    """metric_definitions.code must be UNIQUE (FK target)."""
    assert ("code",) in _unique_column_sets(_table(MetricDefinition))


def test_financial_data_foreign_keys() -> None:
    """financial_data must reference institutions, sources, documents and metrics."""
    fks = {fk.column.table.name for fk in _table(FinancialData).foreign_keys}
    assert "institutions" in fks
    assert "sources" in fks
    assert "documents" in fks
    assert "metric_definitions" in fks


def test_document_foreign_keys() -> None:
    """documents must reference sources (required) and institutions (optional)."""
    fks = {fk.column.table.name for fk in _table(Document).foreign_keys}
    assert "sources" in fks
    assert "institutions" in fks


def test_financial_data_required_columns_not_nullable() -> None:
    """Core provenance columns are NOT NULL (institution_id decoupled in Phase 14)."""
    cols = _table(FinancialData).columns
    for name in (
        "source_id",
        "document_id",
        "metric_code",
        "value_original",
        "scope",
        "period_type",
        "period_year",
        "status",
    ):
        assert cols[name].nullable is False, f"{name} must be NOT NULL"
    # In Phase 14, institution_id is nullable and guarded by ck_financial_data_target
    assert cols["institution_id"].nullable is True


def test_document_source_id_not_nullable() -> None:
    """documents.source_id is required; institution_id is optional."""
    cols = _table(Document).columns
    assert cols["source_id"].nullable is False
    assert cols["institution_id"].nullable is True


def test_relationships_are_wired() -> None:
    """Bidirectional relationships are declared."""
    fd_rels = FinancialData.__mapper__.relationships
    assert {"institution", "source", "document", "metric"} <= set(fd_rels.keys())
    assert fd_rels["metric"].back_populates == "financial_data"
    assert fd_rels["document"].back_populates == "financial_data"
    assert fd_rels["source"].back_populates == "financial_data"
    assert fd_rels["institution"].back_populates == "financial_data"
    assert Document.__mapper__.relationships["source"].back_populates == "documents"
    assert (
        MetricDefinition.__mapper__.relationships["financial_data"].back_populates
        == "metric"
    )


# ============================================================
# Structural constraints (defined on the table)
# ============================================================


def test_financial_data_check_constraints_present() -> None:
    """Workflow/scope/value integrity constraints are defined."""
    names = _check_names(_table(FinancialData))
    assert "ck_financial_data_scope" in names
    assert "ck_financial_data_status" in names
    assert "ck_financial_data_period_type" in names
    assert "ck_financial_data_extraction_method" in names
    assert "ck_financial_data_confidence_range" in names
    assert "ck_financial_data_page_number_positive" in names
    assert "ck_financial_data_reviewed_requires_normalized" in names
    assert "ck_financial_data_verified_requires_validator" in names


def test_document_check_constraints_present() -> None:
    names = _check_names(_table(Document))
    assert "ck_documents_document_type" in names
    assert "ck_documents_download_status" in names
    assert "ck_documents_extraction_status" in names
    assert "ck_documents_period_type" in names
    assert "ck_documents_page_count_positive" in names


def test_metric_definition_check_constraints_present() -> None:
    names = _check_names(_table(MetricDefinition))
    assert "ck_metric_definitions_statement_type" in names
    assert "ck_metric_definitions_category" in names
    assert "ck_metric_definitions_value_type" in names
    assert "ck_metric_definitions_currency_type" in names


def test_scope_check_is_limited_to_institution_scopes() -> None:
    """Only individual/consolidated scopes are allowed (no sector/umoa/country)."""
    sqltext = _check_sql(_table(FinancialData), "ck_financial_data_scope")
    assert "individual" in sqltext
    assert "consolidated" in sqltext
    assert "sector" not in sqltext
    assert "umoa" not in sqltext
    assert "country" not in sqltext


def test_verified_rule_is_enforced_at_db_level() -> None:
    """status='verified' requires verified_at AND verified_by."""
    sqltext = _check_sql(_table(FinancialData), "ck_financial_data_verified_requires_validator")
    assert "verified" in sqltext
    assert "verified_at" in sqltext
    assert "verified_by" in sqltext


def test_file_hash_is_unique_when_present() -> None:
    """documents.file_hash is UNIQUE (content-addressed deduplication)."""
    assert _table(Document).columns["file_hash"].unique is True


# ============================================================
# Metric catalogue integrity
# ============================================================


def test_catalogue_contains_exactly_26_metrics() -> None:
    assert len(V1_METRICS) == 26
    assert len(V1_METRIC_CODES) == 26
    assert len(V1_METRICS_BY_CODE) == 26


def test_no_duplicate_metric_codes() -> None:
    codes = [m["code"] for m in V1_METRICS]
    assert len(codes) == len(set(codes)), "duplicate metric_code detected"


def test_exact_metric_codes_match_specification() -> None:
    expected = {
        # assets
        "total_actifs",
        "tresorerie",
        "creances_clients",
        "creances_banques",
        "immobilisations",
        "autres_actifs",
        # liabilities
        "total_passifs",
        "depots_clients",
        "depots_banques",
        "emprunts_bancaires",
        "obligations_emises",
        "dettes_totales",
        "autres_passifs",
        # equity
        "capitaux_propres",
        # income statement
        "produit_net_bancaire",
        "produits_totaux",
        "charges_totales",
        "resultat_exploitation",
        "resultat_net",
        "chiffre_affaires",
        # cash flow
        "flux_exploitation",
        "flux_investissement",
        "flux_financement",
        # debt indicators
        "facilities_de_change",
        "taux_interet_moyen",
        "endettement_actifs",
    }
    assert set(V1_METRIC_CODES) == expected


def test_every_metric_has_all_required_fields() -> None:
    required = {
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
    }
    for metric in V1_METRICS:
        missing = required - set(metric)
        assert not missing, f"{metric.get('code')} missing fields: {missing}"
        assert metric["label_fr"] and metric["label_en"]
        assert metric["definition_fr"] and metric["definition_en"]


def test_enum_values_are_within_canonical_enumerations() -> None:
    for m in V1_METRICS:
        assert m["statement_type"] in STATEMENT_TYPES, m["code"]
        assert m["category"] in CATEGORIES, m["code"]
        assert m["value_type"] in VALUE_TYPES, m["code"]
        assert m["currency_type"] in CURRENCY_TYPES, m["code"]


def test_display_order_is_unique_and_sequential() -> None:
    orders = sorted(m["display_order"] for m in V1_METRICS)
    assert orders == list(range(1, 27))


def test_all_v1_metrics_are_not_calculated() -> None:
    """V1 collects published values only."""
    assert all(m["is_calculated"] is False for m in V1_METRICS)


def test_debt_related_metrics_match_specification() -> None:
    expected = {
        "emprunts_bancaires",
        "obligations_emises",
        "dettes_totales",
        "facilities_de_change",
        "taux_interet_moyen",
        "endettement_actifs",
    }
    actual = {m["code"] for m in V1_METRICS if m["is_debt_related"]}
    assert actual == expected


def test_non_monetary_metrics_match_specification() -> None:
    """Rate/ratio debt indicators are non-monetary; all amounts are monetary."""
    expected_non_monetary = {"taux_interet_moyen", "endettement_actifs"}
    actual = {m["code"] for m in V1_METRICS if m["currency_type"] == "non_monetary"}
    assert actual == expected_non_monetary
    monetary_amounts = [m for m in V1_METRICS if m["value_type"] == "amount"]
    assert all(m["currency_type"] == "monetary" for m in monetary_amounts)


def test_statement_type_distribution_matches_specification() -> None:
    by_statement: dict[str, int] = {}
    for m in V1_METRICS:
        by_statement[m["statement_type"]] = by_statement.get(m["statement_type"], 0) + 1
    assert by_statement["balance_sheet"] == 14
    assert by_statement["income_statement"] == 6
    assert by_statement["cash_flow_statement"] == 3
    assert by_statement["off_balance_sheet"] == 1
    assert by_statement["not_applicable"] == 2


def test_chiffre_affaires_is_not_calculated() -> None:
    """Revenue must never be derived from net banking income."""
    assert V1_METRICS_BY_CODE["chiffre_affaires"]["is_calculated"] is False
    assert V1_METRICS_BY_CODE["produit_net_bancaire"]["is_calculated"] is False


def test_catalogue_keys_align_with_metric_definition_columns() -> None:
    """Catalogue dict keys must map to existing MetricDefinition columns."""
    columns = set(_table(MetricDefinition).columns.keys())
    for key in V1_METRICS[0]:
        assert key in columns, f"catalogue key '{key}' has no matching column"
