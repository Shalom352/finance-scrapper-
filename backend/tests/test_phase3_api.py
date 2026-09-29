"""
UMOA Banking Intelligence — Phase 3 API Tests

Comprehensive test suite covering:
  - Route existence and connectivity
  - Health checks (liveness and readiness)
  - Error handling (404, 422, structured JSON)
  - Pagination parameter validations
  - Pydantic schema validation
  - Rankings business logic (verified only, currency homogeneity, multiple institutions)
  - Search endpoint (q required, grouped results)
  - Entity 404 responses
  - OpenAPI specification completeness
  - Alembic migrations and seed structure
"""
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from app.db.session import get_db_session
from app.main import app
from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.metric_definition import MetricDefinition


@pytest.fixture
def client():
    """Synchronous test client for route existence tests."""
    return TestClient(app, raise_server_exceptions=False)


# ============================================================
# Route Existence Tests
# ============================================================

class TestRouteExistence:
    """Verify that all Phase 3 endpoints are reachable."""

    def test_health_routes_exist(self, client):
        assert client.get("/health").status_code == 200
        resp = client.get("/api/v1/health")
        assert resp.status_code != 405

    def test_countries_routes_exist(self, client):
        assert client.get("/api/v1/countries").status_code != 405

    def test_sources_routes_exist(self, client):
        assert client.get("/api/v1/sources").status_code != 405

    def test_banking_groups_routes_exist(self, client):
        assert client.get("/api/v1/banking-groups").status_code != 405

    def test_institutions_routes_exist(self, client):
        assert client.get("/api/v1/institutions").status_code != 405

    def test_metrics_routes_exist(self, client):
        assert client.get("/api/v1/metrics").status_code != 405

    def test_documents_routes_exist(self, client):
        assert client.get("/api/v1/documents").status_code != 405

    def test_financial_data_routes_exist(self, client):
        assert client.get("/api/v1/financial-data").status_code != 405

    def test_rankings_requires_metric_code(self, client):
        resp = client.get("/api/v1/rankings")
        assert resp.status_code == 422

    def test_search_requires_query(self, client):
        resp = client.get("/api/v1/search")
        assert resp.status_code == 422

    def test_rankings_with_metric_code(self, client):
        resp = client.get("/api/v1/rankings?metric_code=total_actifs")
        assert resp.status_code != 405

    def test_search_with_query(self, client):
        resp = client.get("/api/v1/search?q=test")
        assert resp.status_code != 405


# ============================================================
# Health Check Tests (Liveness & Readiness)
# ============================================================

class TestHealthChecks:
    """Verify liveness and readiness probe behaviour."""

    def test_health_liveness_success(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["app"] == "UMOA Banking Intelligence"
        assert "version" in data
        assert "timestamp" in data

    def test_health_readiness_db_ok(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one.return_value = 1
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "ok"
            assert data["database"]["status"] == "ok"
        finally:
            app.dependency_overrides.clear()

    def test_health_readiness_db_degraded(self):
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(side_effect=Exception("Connection refused"))

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/health")
            assert resp.status_code == 200
            data = resp.json()
            assert data["status"] == "degraded"
            assert data["database"]["status"] == "error"
            assert "Connection refused" in data["database"]["error"]
        finally:
            app.dependency_overrides.clear()


# ============================================================
# Error Handling Tests
# ============================================================

class TestErrorHandling:
    """Verify that global error handlers produce structured JSON."""

    def test_422_returns_structured_error(self, client):
        resp = client.get("/api/v1/countries?page=-1")
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in data["error"]

    def test_rankings_422_without_metric_code(self, client):
        resp = client.get("/api/v1/rankings")
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_search_422_without_query(self, client):
        resp = client.get("/api/v1/search")
        assert resp.status_code == 422
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "VALIDATION_ERROR"


# ============================================================
# Pagination Parameter Validation Tests
# ============================================================

class TestPaginationValidation:
    """Verify that pagination parameters are validated correctly."""

    def test_page_must_be_positive(self, client):
        resp = client.get("/api/v1/countries?page=0")
        assert resp.status_code == 422

    def test_page_size_max_100(self, client):
        resp = client.get("/api/v1/countries?page_size=101")
        assert resp.status_code == 422

    def test_page_size_must_be_positive(self, client):
        resp = client.get("/api/v1/countries?page_size=0")
        assert resp.status_code == 422


# ============================================================
# Rankings Business Logic Tests
# ============================================================

class TestRankingsLogic:
    """Verify the business logic of the rankings endpoint."""

    def test_rankings_metric_not_found(self):
        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/rankings?metric_code=inconnu")
            assert resp.status_code == 404
            data = resp.json()
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
        finally:
            app.dependency_overrides.clear()

    def test_rankings_empty_when_no_verified_data(self):
        mock_db = AsyncMock()
        metric = MagicMock(spec=MetricDefinition)
        metric.label_fr = "Total actifs"
        metric.label_en = "Total Assets"
        mock_db.scalar = AsyncMock(return_value=metric)

        cur_mock = MagicMock()
        cur_mock.scalars.return_value.all.return_value = []

        cnt_mock = MagicMock()
        cnt_mock.scalar_one.return_value = 0

        mock_db.execute = AsyncMock(side_effect=[cur_mock, cnt_mock])

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/rankings?metric_code=total_actifs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 0
            assert data["items"] == []
            assert data["metric_code"] == "total_actifs"
        finally:
            app.dependency_overrides.clear()

    def test_rankings_heterogeneous_currencies_rejected(self):
        mock_db = AsyncMock()
        metric = MagicMock(spec=MetricDefinition)
        metric.label_fr = "Total actifs"
        metric.label_en = "Total Assets"
        mock_db.scalar = AsyncMock(return_value=metric)

        cur_mock = MagicMock()
        cur_mock.scalars.return_value.all.return_value = ["XOF", "USD"]
        mock_db.execute = AsyncMock(return_value=cur_mock)

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/rankings?metric_code=total_actifs")
            assert resp.status_code == 400
            data = resp.json()
            assert data["error"]["code"] == "BAD_REQUEST"
            assert "Heterogeneous currencies" in data["error"]["message"]
        finally:
            app.dependency_overrides.clear()

    def test_rankings_multiple_institutions_ordered(self):
        mock_db = AsyncMock()
        metric = MagicMock(spec=MetricDefinition)
        metric.label_fr = "Total actifs"
        metric.label_en = "Total Assets"
        mock_db.scalar = AsyncMock(return_value=metric)

        cur_mock = MagicMock()
        cur_mock.scalars.return_value.all.return_value = ["XOF"]

        cnt_mock = MagicMock()
        cnt_mock.scalar_one.return_value = 2

        fd1 = MagicMock(spec=FinancialData)
        fd1.value_normalized = Decimal("5000000000.0")
        fd1.unit_normalized = "absolute"
        fd1.currency_normalized = "XOF"
        fd1.period_year = 2023
        fd1.scope = "individual"

        inst1 = MagicMock(spec=Institution)
        inst1.id = "inst-1"
        inst1.name_official = "Banque A"
        inst1.name_commercial = "BA"

        country1 = MagicMock(spec=Country)
        country1.code = "CI"

        fd2 = MagicMock(spec=FinancialData)
        fd2.value_normalized = Decimal("3000000000.0")
        fd2.unit_normalized = "absolute"
        fd2.currency_normalized = "XOF"
        fd2.period_year = 2023
        fd2.scope = "individual"

        inst2 = MagicMock(spec=Institution)
        inst2.id = "inst-2"
        inst2.name_official = "Banque B"
        inst2.name_commercial = None

        country2 = MagicMock(spec=Country)
        country2.code = "SN"

        rows_mock = MagicMock()
        rows_mock.all.return_value = [(fd1, inst1, country1), (fd2, inst2, country2)]

        mock_db.execute = AsyncMock(side_effect=[cur_mock, cnt_mock, rows_mock])

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/rankings?metric_code=total_actifs")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total"] == 2
            assert len(data["items"]) == 2
            assert data["items"][0]["rank"] == 1
            assert data["items"][0]["institution_name"] == "BA"
            assert data["items"][0]["value_normalized"] == 5000000000.0
            assert data["items"][0]["country_code"] == "CI"
            assert data["items"][1]["rank"] == 2
            assert data["items"][1]["institution_name"] == "Banque B"
            assert data["items"][1]["value_normalized"] == 3000000000.0
            assert data["items"][1]["country_code"] == "SN"
        finally:
            app.dependency_overrides.clear()


# ============================================================
# Search Logic Tests
# ============================================================

class TestSearchLogic:
    """Verify global search behaviour."""

    def test_search_returns_grouped_results(self):
        mock_db = AsyncMock()
        res_mock = MagicMock()
        res_mock.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=res_mock)

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get("/api/v1/search?q=BCEAO")
            assert resp.status_code == 200
            data = resp.json()
            assert data["query"] == "BCEAO"
            assert "institutions" in data
            assert "banking_groups" in data
            assert "sources" in data
            assert "documents" in data
        finally:
            app.dependency_overrides.clear()


# ============================================================
# Entity Detail 404 Tests
# ============================================================

class TestEntityDetail404:
    """Verify that all detail endpoints return structured 404 when not found."""

    @pytest.mark.parametrize(
        ("url", "detail_keyword"),
        [
            ("/api/v1/countries/missing-id", "Country"),
            ("/api/v1/sources/missing-id", "Source"),
            ("/api/v1/banking-groups/missing-id", "Banking Group"),
            ("/api/v1/institutions/missing-id", "Institution"),
            ("/api/v1/metrics/missing-code", "Metric"),
            ("/api/v1/documents/missing-id", "Document"),
            ("/api/v1/financial-data/missing-id", "Financial Data"),
        ],
    )
    def test_detail_endpoint_404(self, url, detail_keyword):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        app.dependency_overrides[get_db_session] = lambda: mock_db
        try:
            c = TestClient(app)
            resp = c.get(url)
            assert resp.status_code == 404
            data = resp.json()
            assert data["error"]["code"] == "RESOURCE_NOT_FOUND"
            assert detail_keyword in data["error"]["message"]
        finally:
            app.dependency_overrides.clear()


# ============================================================
# Schema Validation Tests
# ============================================================

class TestSchemas:
    """Verify that Pydantic schemas are correctly defined."""

    def test_paginated_response_schema(self):
        from app.schemas.common import PaginatedResponse
        resp = PaginatedResponse(
            items=[], total=0, page=1, page_size=20,
            has_next=False, has_prev=False,
        )
        assert resp.total == 0
        assert resp.items == []

    def test_country_read_schema(self):
        from app.schemas.country import CountryRead
        fields = CountryRead.model_fields
        assert "id" in fields
        assert "code" in fields
        assert "name_fr" in fields
        assert "is_active" in fields

    def test_metric_read_schema(self):
        from app.schemas.metric_definition import MetricRead
        fields = MetricRead.model_fields
        assert "code" in fields
        assert "label_fr" in fields
        assert "statement_type" in fields
        assert "value_type" in fields
        assert "is_debt_related" in fields

    def test_document_read_schema(self):
        from app.schemas.document import DocumentRead
        fields = DocumentRead.model_fields
        assert "title" in fields
        assert "document_type" in fields
        assert "download_status" in fields
        assert "extraction_status" in fields
        assert "source" in fields

    def test_financial_data_read_schema(self):
        from app.schemas.financial_data import FinancialDataRead
        fields = FinancialDataRead.model_fields
        assert "institution_id" in fields
        assert "metric_code" in fields
        assert "value_original" in fields
        assert "value_normalized" in fields
        assert "scope" in fields
        assert "status" in fields
        assert "institution" in fields
        assert "metric" in fields

    def test_financial_data_list_schema(self):
        from app.schemas.financial_data import FinancialDataList
        fields = FinancialDataList.model_fields
        assert "currency_original" in fields
        assert "currency_normalized" in fields
        assert "unit_original" in fields

    def test_ranking_response_schema(self):
        from app.api.v1.rankings import RankingEntry, RankingResponse
        fields = RankingResponse.model_fields
        assert "metric_code" in fields
        assert "currency" in fields
        assert "items" in fields
        entry_fields = RankingEntry.model_fields
        assert "rank" in entry_fields
        assert "institution_name" in entry_fields

    def test_search_results_schema(self):
        from app.api.v1.search import SearchResults
        fields = SearchResults.model_fields
        assert "query" in fields
        assert "institutions" in fields
        assert "banking_groups" in fields
        assert "sources" in fields
        assert "documents" in fields


# ============================================================
# OpenAPI Schema Tests
# ============================================================

class TestOpenAPI:
    """Verify OpenAPI spec is correctly generated."""

    def test_openapi_schema_loads(self, client):
        resp = client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema
        assert "info" in schema

    def test_openapi_contains_all_endpoints(self, client):
        resp = client.get("/openapi.json")
        paths = resp.json()["paths"]
        expected = [
            "/health",
            "/api/v1/health",
            "/api/v1/countries",
            "/api/v1/countries/{country_id}",
            "/api/v1/sources",
            "/api/v1/sources/{source_id}",
            "/api/v1/banking-groups",
            "/api/v1/banking-groups/{group_id}",
            "/api/v1/institutions",
            "/api/v1/institutions/{institution_id}",
            "/api/v1/metrics",
            "/api/v1/metrics/{code}",
            "/api/v1/documents",
            "/api/v1/documents/{document_id}",
            "/api/v1/financial-data",
            "/api/v1/financial-data/{data_id}",
            "/api/v1/rankings",
            "/api/v1/search",
        ]
        for path in expected:
            assert path in paths, f"Missing endpoint in OpenAPI: {path}"

    def test_openapi_title(self, client):
        resp = client.get("/openapi.json")
        info = resp.json()["info"]
        assert info["title"] == "UMOA Banking Intelligence API"
        assert info["version"] == "0.1.0"


# ============================================================
# Migration & Seed Tests (offline)
# ============================================================

class TestMigrations:
    """Verify new migration files are correctly structured."""

    def test_migration_0003_exists(self):
        import importlib
        m = importlib.import_module("migrations.versions.0003_seed_countries_and_constraints")
        assert m.revision == "0003_seed_countries_and_constraints"
        assert m.down_revision == "0002_seed_metric_catalogue"
        assert hasattr(m, "upgrade")
        assert hasattr(m, "downgrade")

    def test_migration_0004_exists(self):
        import importlib
        m = importlib.import_module("migrations.versions.0004_seed_official_sources")
        assert m.revision == "0004_seed_official_sources"
        assert m.down_revision == "0003_seed_countries_and_constraints"
        assert hasattr(m, "upgrade")
        assert hasattr(m, "downgrade")

    def test_migration_chain_is_linear(self):
        import importlib
        m1 = importlib.import_module("migrations.versions.0001_initial_schema")
        m2 = importlib.import_module("migrations.versions.0002_seed_metric_catalogue")
        m3 = importlib.import_module("migrations.versions.0003_seed_countries_and_constraints")
        m4 = importlib.import_module("migrations.versions.0004_seed_official_sources")
        assert m1.down_revision is None
        assert m2.down_revision == "0001_initial_schema"
        assert m3.down_revision == "0002_seed_metric_catalogue"
        assert m4.down_revision == "0003_seed_countries_and_constraints"

    def test_migration_0003_has_8_countries(self):
        import importlib
        m = importlib.import_module("migrations.versions.0003_seed_countries_and_constraints")
        assert len(m.countries) == 8
        codes = {c["code"] for c in m.countries}
        assert codes == {"BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"}

    def test_migration_0004_has_2_sources(self):
        import importlib
        m = importlib.import_module("migrations.versions.0004_seed_official_sources")
        assert len(m.sources) == 2
        short_names = {s["short_name"] for s in m.sources}
        assert short_names == {"BCEAO", "CB-UMOA"}
