"""
Phase 8C — Analytics service ↔ ORM contract tests.

The Phase 7 API tests mock AnalyticsService entirely, so they never exercised
the real queries. These tests run the real service against a fake AsyncSession
and would have caught:
  - references to ORM attributes that do not exist (Country.iso_code_2,
    Institution.name), which crash every analytics endpoint on a real database;
  - the comparator picking an arbitrary row (`.first()`) — including rejected or
    non-annual observations — instead of the authoritative value.
"""
import ast
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.analytics.analytics_service import AnalyticsService

SERVICE_PATH = Path(__file__).resolve().parents[1] / "scraping" / "analytics" / "analytics_service.py"
MODELS = {"Country": Country, "Institution": Institution, "FinancialData": FinancialData}


def test_service_only_references_existing_orm_attributes():
    """Every `Country.x`, `Institution.x`, `FinancialData.x` used by the service exists on the model."""
    tree = ast.parse(SERVICE_PATH.read_text(encoding="utf-8"))
    missing = [
        f"{node.value.id}.{node.attr}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id in MODELS
        and not hasattr(MODELS[node.value.id], node.attr)
    ]
    assert missing == []


def test_service_uses_existing_instance_attributes():
    """Instance attributes read on institutions/countries exist on the mapped columns."""
    source = SERVICE_PATH.read_text(encoding="utf-8")
    assert "iso_code_2" not in source
    assert ".name_official" in source
    for attr in ("name_official", "country"):
        assert hasattr(Institution, attr)
    assert hasattr(Country, "code")


# ---------------------------------------------------------------------------
# Fake session
# ---------------------------------------------------------------------------


class FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one_or_none(self):
        return self._rows[0] if self._rows else None


@dataclass
class FakeSession:
    rows: list = field(default_factory=list)
    statements: list = field(default_factory=list)

    async def execute(self, stmt):
        self.statements.append(stmt)
        compiled = stmt.compile()
        params = compiled.params
        sql = str(compiled)
        if "FROM financial_data" not in sql:
            return FakeResult([])
        matching = [
            r
            for r in self.rows
            if all(
                getattr(r, col) == val
                for col, val in (
                    ("institution_id", params.get("institution_id_1")),
                    ("metric_code", params.get("metric_code_1")),
                    ("period_year", params.get("period_year_1")),
                    ("period_type", params.get("period_type_1")),
                )
                if val is not None
            )
        ]
        return FakeResult(matching)


def row(inst, value, status="extracted", period_type="annual", year=2023, metric="total_actifs"):
    return SimpleNamespace(
        id=f"{inst}-{value}-{status}-{period_type}",
        institution_id=inst,
        metric_code=metric,
        source_id="src",
        source=SimpleNamespace(name="Source", source_type="bank", priority=1),
        document_id="doc",
        document=SimpleNamespace(title="Doc"),
        period_year=year,
        period_type=period_type,
        period_label=None,
        value_original=str(value),
        unit_original=None,
        currency_original="XOF",
        value_normalized=Decimal(str(value)),
        unit_normalized="unit",
        currency_normalized="XOF",
        page_number=1,
        status=status,
        extraction_method="pdf_table",
        confidence_score=Decimal("0.9"),
        verified_by=None,
    )


async def compare(rows):
    session = FakeSession(rows=rows)
    result = await AnalyticsService().compare_entities(
        session,
        comparison_type="institution_vs_institution",
        entity_a="A",
        entity_b="B",
        metric_or_ratio="total_actifs",
        year=2023,
    )
    return result, session


@pytest.mark.asyncio
async def test_compare_metric_excludes_rejected_observations():
    result, _ = await compare([row("A", 999, status="rejected"), row("A", 100), row("B", 50)])
    assert result.value_a == pytest.approx(100)
    assert result.value_b == pytest.approx(50)


@pytest.mark.asyncio
async def test_compare_metric_prefers_verified_value():
    result, _ = await compare([row("A", 100), row("A", 120, status="verified"), row("B", 50)])
    assert result.value_a == pytest.approx(120)


@pytest.mark.asyncio
async def test_compare_metric_unresolved_conflict_is_missing_not_arbitrary():
    result, _ = await compare([row("A", 100), row("A", 130), row("B", 50)])
    assert result.value_a is None
    assert result.value_b == pytest.approx(50)


@pytest.mark.asyncio
async def test_compare_metric_ignores_non_annual_observations():
    result, session = await compare([row("A", 700, period_type="semi_annual"), row("B", 50)])
    assert result.value_a is None
    sql = " ".join(str(s.compile()) for s in session.statements)
    assert "financial_data.period_type" in sql


@pytest.mark.asyncio
async def test_aggregations_query_builds_against_real_models():
    """get_aggregations must not crash on attribute access (was Country.iso_code_2)."""
    session = FakeSession()
    result = await AnalyticsService().get_aggregations(session, year=2023, metric_code="total_actifs", country_code="CI")
    assert result == []
    assert "countries.code" in str(session.statements[0].compile())


@pytest.mark.asyncio
async def test_ratios_and_growth_country_filter_builds_against_real_models():
    session = FakeSession()
    service = AnalyticsService()
    # Institution lookup returns nothing, so only the institution query runs; it must build cleanly.
    assert await service.get_ratios(session, country_code="SN", year=2023) == ([], 0)
    assert await service.get_growth(session, country_code="SN", year=2023) == ([], 0)
    assert all("countries.code" in str(s.compile()) for s in session.statements)
