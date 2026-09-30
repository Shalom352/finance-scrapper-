"""
UMOA Banking Intelligence — Phase 5C Reconciliation & Validation Workflow Tests

Validates:
  - InstitutionNameNormalizer: accents, corporate suffixes, abbreviations, country hint extraction
  - InstitutionMatcher & ConfidenceScorer: exact, commercial, network aliases, cross-border protection, ambiguity
  - Validation Workflow: extracted -> needs_review -> reviewed -> verified / rejected
  - Enforcement of V1 invariants: forbidden direct extracted -> verified jump, verified_by required
  - API Endpoints: /review, /verify, /reject, /bulk-review, /quality-summary
  - Pipeline integration with InstitutionResolver
"""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.document import Document
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.metric_definition import MetricDefinition
from app.models.source import Source
from app.services.financial_data import (
    bulk_review_financial_data,
    get_financial_data_quality_summary,
    reject_financial_data,
    review_financial_data,
    verify_financial_data,
)
from scraping.reconciliation.confidence import ConfidenceScorer
from scraping.reconciliation.matcher import InstitutionMatcher
from scraping.reconciliation.models import InstitutionEntity
from scraping.reconciliation.normalizer import InstitutionNameNormalizer
from scraping.reconciliation.resolver import InstitutionResolver

# ==============================================================================
# 1. INSTITUTION NAME NORMALIZER TESTS
# ==============================================================================

def test_normalizer_removes_accents_and_legal_forms():
    """Legal suffixes like S.A., SARL, SAS should be removed while keeping core names."""
    normalizer = InstitutionNameNormalizer()

    assert normalizer.normalize("SOCIÉTÉ GÉNÉRALE DE BANQUES EN CÔTE D'IVOIRE S.A.") == "SOCIETE GENERALE DE BANQUES EN COTE D IVOIRE"
    assert normalizer.normalize("Banque Atlantique Côte d'Ivoire SA") == "BANQUE ATLANTIQUE COTE D IVOIRE"
    assert normalizer.normalize("Ecobank Sénégal S.A.R.L.") == "ECOBANK SENEGAL"
    assert normalizer.normalize("Coris Bank International Succursale de l'UMOA") == "CORIS BANK INTERNATIONAL"


def test_normalizer_expands_abbreviations():
    """Standard abbreviations like Ste, Bqe, Intl must be expanded."""
    normalizer = InstitutionNameNormalizer()

    assert normalizer.normalize("Ste Ivoirienne de Bqe") == "SOCIETE IVOIRIENNE DE BANQUE"
    assert normalizer.normalize("Bqe Intl pour le Commerce") == "BANQUE INTERNATIONAL POUR LE COMMERCE"


def test_normalizer_extracts_country_hints():
    """Detect country hints for UMOA member states."""
    normalizer = InstitutionNameNormalizer()

    _, c_ci = normalizer.extract_country_hint("Société Générale Côte d'Ivoire")
    assert c_ci == "CI"

    _, c_sn = normalizer.extract_country_hint("Ecobank Sénégal")
    assert c_sn == "SN"

    _, c_bf = normalizer.extract_country_hint("Coris Bank Burkina Faso")
    assert c_bf == "BF"

    _, c_bj = normalizer.extract_country_hint("BOA Bénin")
    assert c_bj == "BJ"

    _, c_tg = normalizer.extract_country_hint("Orabank Togo")
    assert c_tg == "TG"

    _, c_none = normalizer.extract_country_hint("Banque Générale Internationale")
    assert c_none is None


def test_normalizer_preserves_discriminating_tokens():
    """Qualifiers such as LEASING, FINANCE, CREDIT must never be removed."""
    normalizer = InstitutionNameNormalizer()

    res = normalizer.normalize("Alios Finance Côte d'Ivoire")
    assert "FINANCE" in res
    assert "COTE D IVOIRE" in res

    res2 = normalizer.normalize("Société Générale Leasing")
    assert "LEASING" in res2


# ==============================================================================
# 2. MATCHER & CONFIDENCE SCORER TESTS
# ==============================================================================

@pytest.fixture
def sample_institutions() -> list[InstitutionEntity]:
    return [
        InstitutionEntity(
            id="inst-sgci",
            name_official="Société Générale de Banques en Côte d'Ivoire",
            name_commercial="Société Générale Côte d'Ivoire",
            country_code="CI",
        ),
        InstitutionEntity(
            id="inst-sgbs",
            name_official="Société Générale de Banques au Sénégal",
            name_commercial="Société Générale Sénégal",
            country_code="SN",
        ),
        InstitutionEntity(
            id="inst-baci",
            name_official="Banque Atlantique Côte d'Ivoire",
            name_commercial="Banque Atlantique CI",
            country_code="CI",
        ),
        InstitutionEntity(
            id="inst-basn",
            name_official="Banque Atlantique Sénégal",
            name_commercial="Banque Atlantique SN",
            country_code="SN",
        ),
        InstitutionEntity(
            id="inst-ecob-tg",
            name_official="Ecobank Togo S.A.",
            name_commercial="Ecobank Togo",
            country_code="TG",
        ),
        InstitutionEntity(
            id="inst-ecob-ci",
            name_official="Ecobank Côte d'Ivoire S.A.",
            name_commercial="Ecobank CI",
            country_code="CI",
        ),
    ]


def test_matcher_exact_official_and_commercial(sample_institutions):
    """Exact official or commercial name matches with 0.98 - 1.0 score."""
    matcher = InstitutionMatcher(sample_institutions)

    candidates = matcher.match("Société Générale de Banques en Côte d'Ivoire S.A.")
    assert len(candidates) >= 1
    assert candidates[0].institution_id == "inst-sgci"
    assert candidates[0].score == 1.0

    candidates_comm = matcher.match("Société Générale Côte d'Ivoire")
    assert len(candidates_comm) >= 1
    assert candidates_comm[0].institution_id == "inst-sgci"
    assert candidates_comm[0].score >= 0.98


def test_matcher_known_network_alias(sample_institutions):
    """SGCI matches Société Générale in CI with high confidence."""
    matcher = InstitutionMatcher(sample_institutions)

    candidates = matcher.match("SGCI")
    assert len(candidates) >= 1
    assert candidates[0].institution_id == "inst-sgci"
    assert candidates[0].score == 0.95
    assert candidates[0].country_code == "CI"


def test_matcher_cross_border_protection(sample_institutions):
    """Rule: NEVER match across countries. SGCI must never match SGBS in SN."""
    matcher = InstitutionMatcher(sample_institutions)
    scorer = ConfidenceScorer()

    # Searching with expected country SN for a CI bank must reject CI candidate
    candidates = matcher.match("Société Générale Côte d'Ivoire", country_hint="SN")
    best, level, status, notes = scorer.evaluate(candidates, expected_country_code="SN")

    assert best is None
    assert status == "no_match"
    assert "country mismatch" in notes


def test_matcher_detects_ambiguity_without_country(sample_institutions):
    """'Banque Atlantique' without country hint when present in CI and SN must be ambiguous."""
    resolver = InstitutionResolver(matcher=InstitutionMatcher(sample_institutions))

    res = resolver.resolve("Banque Atlantique")
    assert res.status == "ambiguous"
    assert res.institution_id is None  # Never guess automatically!
    assert res.confidence_level == "low_confidence"
    assert "Ambiguous" in (res.notes or "")


def test_matcher_resolves_when_country_hint_provided(sample_institutions):
    """'Banque Atlantique' with country hint 'CI' must resolve cleanly to BACI."""
    resolver = InstitutionResolver(matcher=InstitutionMatcher(sample_institutions))

    res = resolver.resolve("Banque Atlantique", country_hint="CI")
    assert res.status == "matched"
    assert res.institution_id == "inst-baci"
    assert res.country_code == "CI"
    assert res.confidence_level == "high_confidence"


# ==============================================================================
# 3. VALIDATION WORKFLOW SERVICE TESTS
# ==============================================================================

def make_mock_financial_data(
    data_id: str = "data-1",
    status: str = "extracted",
    value_normalized: Decimal | None = Decimal("1000000.00"),
    notes: str = "Extracted automatically",
) -> MagicMock:
    row = MagicMock(spec=FinancialData)
    row.id = data_id
    row.institution_id = "inst-1"
    row.source_id = "src-1"
    row.document_id = "doc-1"
    row.metric_code = "TOTAL_ASSETS"
    row.scope = "individual"
    row.period_type = "annual"
    row.period_year = 2023
    row.period_label = "2023"
    row.value_original = "1000000"
    row.unit_original = "thousands"
    row.currency_original = "XOF"
    row.value_normalized = value_normalized
    row.unit_normalized = "absolute"
    row.currency_normalized = "XOF"
    row.page_number = 1
    row.extraction_method = "table"
    row.confidence_score = Decimal("0.95")
    row.status = status
    row.notes = notes
    row.extracted_at = datetime.now(UTC)
    row.verified_at = None
    row.verified_by = None
    row.created_at = datetime.now(UTC)
    row.updated_at = datetime.now(UTC)

    inst = MagicMock(spec=Institution)
    inst.id = "inst-1"
    inst.name_official = "Banque Test"
    inst.name_commercial = "BT"
    inst.institution_type = "commercial_bank"
    inst.country_id = "c-ci"
    inst.country = None
    inst.banking_group = None
    inst.status = "active"
    row.institution = inst

    src = MagicMock(spec=Source)
    src.id = "src-1"
    src.name = "Banque Centrale"
    src.short_name = "BCEAO"
    src.source_type = "central_bank"
    src.priority = 1
    src.country_code = "UMOA"
    src.is_active = True
    row.source = src

    doc = MagicMock(spec=Document)
    doc.id = "doc-1"
    doc.title = "Rapport 2023"
    doc.document_type = "annual_report"
    doc.institution_id = "inst-1"
    doc.source_id = "src-1"
    doc.url = "https://example.com/doc.pdf"
    doc.period_year = 2023
    doc.period_type = "annual"
    doc.language = "fr"
    doc.download_status = "downloaded"
    doc.extraction_status = "extracted"
    row.document = doc

    metric = MagicMock(spec=MetricDefinition)
    metric.id = "met-1"
    metric.code = "TOTAL_ASSETS"
    metric.label_fr = "Total Bilan"
    metric.label_en = "Total Assets"
    metric.statement_type = "balance_sheet"
    metric.category = "balance_sheet_assets"
    metric.value_type = "currency"
    metric.currency_type = "monetary"
    metric.is_calculated = False
    metric.is_active = True
    metric.is_debt_related = False
    metric.display_order = 1
    row.metric = metric

    return row


@pytest.mark.asyncio
async def test_workflow_review_and_verify_success():
    """Valid workflow: extracted -> reviewed -> verified with verified_by."""
    mock_row = make_mock_financial_data("data-1", "extracted", Decimal("1000000.00"), "Extracted automatically")

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add is synchronous (audit event)
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = mock_row
    db.execute.return_value = exec_res

    # 1. Review step
    await review_financial_data(db, "data-1", reviewer_notes="Examined and approved")
    assert mock_row.status == "reviewed"
    assert "Review: Examined and approved" in mock_row.notes

    # 2. Verify step (from reviewed status)
    await verify_financial_data(db, "data-1", verified_by="analyst_test@umoa.org", verification_notes="Source checked")
    assert mock_row.status == "verified"
    assert mock_row.verified_by == "analyst_test@umoa.org"
    assert mock_row.verified_at is not None
    events = [c.args[0] for c in db.add.call_args_list]
    assert [(e.action, e.previous_status, e.new_status) for e in events] == [
        ("review", "extracted", "reviewed"), ("verify", "reviewed", "verified")]
    assert events[1].actor == "analyst_test@umoa.org"


@pytest.mark.asyncio
async def test_workflow_forbidden_direct_extracted_to_verified_jump():
    """Invariant: Jumping directly from 'extracted' to 'verified' is forbidden."""
    mock_row = make_mock_financial_data("data-2", "extracted", Decimal("500000.00"))

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add is synchronous (audit event)
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = mock_row
    db.execute.return_value = exec_res

    with pytest.raises(ValueError, match="Direct verification from status 'extracted' is forbidden"):
        await verify_financial_data(db, "data-2", verified_by="analyst_1")


@pytest.mark.asyncio
async def test_workflow_reject_requires_reason():
    """Transition to rejected requires a non-empty reason."""
    mock_row = make_mock_financial_data("data-3", "needs_review", Decimal("500000.00"), "")

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add is synchronous (audit event)
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = mock_row
    db.execute.return_value = exec_res

    # Empty reason fails
    with pytest.raises(ValueError, match="Rejection reason is mandatory"):
        await reject_financial_data(db, "data-3", reason="   ")

    # Valid reason succeeds
    await reject_financial_data(db, "data-3", reason="Illegible scan in source document")
    assert mock_row.status == "rejected"
    assert "Rejection: Illegible scan" in mock_row.notes
    (event,) = (c.args[0] for c in db.add.call_args_list)
    assert (event.action, event.previous_status, event.reason) == (
        "reject", "needs_review", "Illegible scan in source document")


@pytest.mark.asyncio
async def test_workflow_bulk_review():
    """Bulk review updates candidate rows with value_normalized."""
    r1 = MagicMock(spec=FinancialData, id="d1", status="extracted", value_normalized=Decimal("10"), notes="")
    r2 = MagicMock(spec=FinancialData, id="d2", status="needs_review", value_normalized=Decimal("20"), notes="")

    db = AsyncMock()
    db.add = MagicMock()  # AsyncSession.add is synchronous (audit event)
    # Mock finding r1 then r2
    res1 = MagicMock()
    res1.scalar_one_or_none.return_value = r1
    res2 = MagicMock()
    res2.scalar_one_or_none.return_value = r2
    db.execute.side_effect = [res1, res2]

    updated = await bulk_review_financial_data(db, ["d1", "d2"], reviewer_notes="Batch review OK")
    assert updated == ["d1", "d2"]
    assert r1.status == "reviewed"
    assert r2.status == "reviewed"


@pytest.mark.asyncio
async def test_workflow_quality_summary():
    """Data quality summary computes status distribution and rates."""
    db = AsyncMock()

    status_mock = MagicMock()
    status_mock.all.return_value = [("extracted", 80), ("needs_review", 15), ("reviewed", 5)]

    inst_mock = MagicMock()
    inst_mock.scalar_one.return_value = 12

    metric_mock = MagicMock()
    metric_mock.scalar_one.return_value = 8

    db.execute.side_effect = [status_mock, inst_mock, metric_mock]

    summary = await get_financial_data_quality_summary(db)
    assert summary.total_points == 100
    assert summary.extracted_count == 80
    assert summary.needs_review_count == 15
    assert summary.reviewed_count == 5
    assert summary.verified_count == 0
    assert summary.verification_rate == 0.0
    assert summary.needs_review_rate == 0.15
    assert summary.distinct_institutions_count == 12
    assert summary.distinct_metrics_count == 8


# ==============================================================================
# 4. API ENDPOINTS TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_api_quality_summary_endpoint():
    """GET /api/v1/financial-data/quality-summary returns summary schema."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Override db dependency with mock
        mock_db = AsyncMock()
        status_mock = MagicMock()
        status_mock.all.return_value = [("extracted", 10)]
        mock_inst = MagicMock()
        mock_inst.scalar_one.return_value = 2
        mock_met = MagicMock()
        mock_met.scalar_one.return_value = 4
        mock_db.execute.side_effect = [status_mock, mock_inst, mock_met]

        from app.db.session import get_db_session
        app.dependency_overrides[get_db_session] = lambda: mock_db

        try:
            resp = await client.get("/api/v1/financial-data/quality-summary")
            assert resp.status_code == 200
            data = resp.json()
            assert data["total_points"] == 10
            assert data["extracted_count"] == 10
            assert "verification_rate" in data
        finally:
            app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_verify_endpoint_rejects_extracted_status():
    """POST /api/v1/financial-data/{id}/verify returns 400 when direct jump attempted."""
    mock_row = make_mock_financial_data("d-test", "extracted", Decimal("100"))
    mock_db = AsyncMock()
    exec_res = MagicMock()
    exec_res.scalar_one_or_none.return_value = mock_row
    mock_db.execute.return_value = exec_res

    from app.db.session import get_db_session
    app.dependency_overrides[get_db_session] = lambda: mock_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        try:
            resp = await client.post(
                "/api/v1/financial-data/d-test/verify",
                json={"verified_by": "analyst_1"},
            )
            assert resp.status_code == 400
            data = resp.json()
            error_msg = data.get("error", {}).get("message") or data.get("detail", "")
            assert "forbidden" in error_msg.lower()
        finally:
            app.dependency_overrides.clear()
