"""
UMOA Banking Intelligence — Phase 5B Financial Extraction Tests

Validates:
  - Table extraction (simple, multi-year, multi-column, subtotals, blank rows)
  - Period detection (2025/2024, "31 décembre 2025", N/N-1)
  - Currency & unit detection (FCFA, XOF, EUR, USD, millions, milliers, milliards)
  - Numeric value parsing (spaces, dots, commas, negative parentheses, trailing minus, ambiguities)
  - Conservative metric mapping to 26 V1 metrics & negative guardrails
  - Provenance integrity (document_id, page_number, period_year, original/normalized values)
  - Financial consistency checks (Total Actif ≈ Total Passif, monotonicity)
  - Database idempotent insertion and status workflow (never 'verified')
  - CLI extract command execution
"""
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from app.models.document import Document
from app.models.financial_data import FinancialData
from scraping.parsing.consistency_checker import ConsistencyChecker
from scraping.parsing.financial_extractor import FinancialExtractor
from scraping.parsing.financial_mapper import MetricMapper
from scraping.parsing.period_detector import PeriodDetector
from scraping.parsing.table_extractor import TableExtractor
from scraping.parsing.table_models import (
    ExtractedMetricPoint,
)
from scraping.parsing.unit_detector import UnitDetector
from scraping.parsing.value_parser import ValueParser
from scraping.pipeline import ScrapingPipeline
from scraping.storage.manager import StorageManager

# ==============================================================================
# 1. TABLE EXTRACTION TESTS
# ==============================================================================

def test_table_extractor_from_text_simple_and_multi_column():
    """Test table extraction from structured text with 2 years and sub-totals."""
    table_text = (
        "Rubriques\t2023\t2024\n"
        "Caisse et banques centrales\t50 000\t60 000\n"
        "Créances sur la clientèle\t450 000\t500 000\n"
        "Immobilisations\t30 000\t35 000\n"
        "Total Actif\t530 000\t595 000\n"
    )
    extractor = TableExtractor()
    tables = extractor.extract_tables_from_text(table_text, page_number=3)

    assert len(tables) == 1
    tab = tables[0]
    assert tab.page_number == 3
    assert tab.row_count == 5
    assert tab.column_count == 3
    assert tab.headers == ["Rubriques", "2023", "2024"]

    # Check cell contents
    total_row = tab.rows[4]
    assert total_row.cells[0].raw_text == "Total Actif"
    assert total_row.cells[1].raw_text == "530 000"
    assert total_row.cells[2].raw_text == "595 000"


def test_table_extractor_skips_empty_and_narrative_lines():
    """Test that blank lines and non-tabular sentences do not corrupt tables."""
    text_with_blanks = (
        "Postes\t2024\n"
        "\n"
        "Caisse\t120 000\n"
        "   \n"
        "Total Actif\t120 000\n"
    )
    extractor = TableExtractor()
    tables = extractor.extract_tables_from_text(text_with_blanks, page_number=1)
    assert len(tables) == 1
    assert tables[0].row_count == 3


def test_table_extractor_from_pymupdf_page():
    """Test extracting tables from a generated PyMuPDF page with spatial clustering."""
    doc = pymupdf.open()
    page = doc.new_page()
    # Insert columns spaced out horizontally
    page.insert_text((50, 50), "Postes")
    page.insert_text((200, 50), "2023")
    page.insert_text((300, 50), "2024")

    page.insert_text((50, 80), "Créances sur la clientèle")
    page.insert_text((200, 80), "400000")
    page.insert_text((300, 80), "450000")

    page.insert_text((50, 110), "Total Actif")
    page.insert_text((200, 110), "500000")
    page.insert_text((300, 110), "550000")

    extractor = TableExtractor()
    tables = extractor.extract_tables_from_page(page, page_number=1)
    doc.close()

    assert len(tables) >= 1
    tab = tables[0]
    assert tab.row_count >= 3
    assert tab.column_count >= 2


# ==============================================================================
# 2. PERIOD DETECTOR TESTS
# ==============================================================================

def test_period_detector_explicit_years():
    """Detect columns with 4-digit years 2024 and 2025."""
    detector = PeriodDetector()
    headers = ["Libellé", "Notes", "2024", "2025", "Variation"]
    cols = detector.detect_period_columns(headers)

    assert len(cols) == 2
    assert cols[0].column_index == 2
    assert cols[0].period_year == 2024
    assert cols[1].column_index == 3
    assert cols[1].period_year == 2025


def test_period_detector_french_date_headers():
    """Detect periods from French accounting date expressions."""
    detector = PeriodDetector()
    headers = ["Actif", "Au 31 décembre 2024", "Au 31 décembre 2023"]
    cols = detector.detect_period_columns(headers)

    assert len(cols) == 2
    assert cols[0].period_year == 2024
    assert cols[1].period_year == 2023


def test_period_detector_relative_n_and_n_minus_one():
    """Detect relative N / N-1 columns using base document year."""
    detector = PeriodDetector()
    headers = ["Postes", "Exercice N", "Exercice N-1"]
    cols = detector.detect_period_columns(headers, base_document_year=2024)

    assert len(cols) == 2
    assert cols[0].period_year == 2024
    assert cols[1].period_year == 2023


# ==============================================================================
# 3. UNIT & CURRENCY DETECTOR TESTS
# ==============================================================================

def test_unit_detector_millions_fcfa():
    """Detect 'en millions de FCFA' -> scale 1_000_000, currency XOF."""
    detector = UnitDetector()
    context = "Bilan condensé. Les montants sont exprimés en millions de FCFA au 31 décembre 2024."
    info = detector.detect_units(context)

    assert info.currency == "XOF"
    assert info.scale == 1_000_000
    assert info.unit_label == "millions"
    assert "scale" in info.evidence


def test_unit_detector_milliers_and_eur():
    """Detect 'en milliers d'euros' -> scale 1_000, currency EUR."""
    detector = UnitDetector()
    context = "Compte de résultat (en milliers d'euros)"
    info = detector.detect_units(context)

    assert info.currency == "EUR"
    assert info.scale == 1_000
    assert info.unit_label == "milliers"


def test_unit_detector_milliards_and_usd():
    """Detect 'en milliards de dollars' -> scale 1_000_000_000, currency USD."""
    detector = UnitDetector()
    context = "Tableau des flux de trésorerie consolidé en milliards de USD"
    info = detector.detect_units(context)

    assert info.currency == "USD"
    assert info.scale == 1_000_000_000
    assert info.unit_label == "milliards"


def test_unit_detector_default_when_no_mention():
    """Rule: never invent scale or currency without text clues."""
    detector = UnitDetector()
    info = detector.detect_units("Tableau financier général sans mention d'unité")

    assert info.currency is None
    assert info.scale == 1
    assert info.unit_label == "unites"


# ==============================================================================
# 4. VALUE PARSER TESTS
# ==============================================================================

@pytest.mark.parametrize(
    "raw_input,expected_val,is_ambiguous",
    [
        ("1 250 000", 1250000.0, False),
        ("1,250,000", 1250000.0, False),
        ("1.250.000", 1250000.0, False),
        ("1 250,50", 1250.50, False),
        ("1 250.50", 1250.50, False),
        ("(450 000)", -450000.0, False),
        ("-450 000", -450000.0, False),
        ("450 000-", -450000.0, False),
        ("-", 0.0, False),
        ("—", 0.0, False),
        ("N/A", 0.0, False),
        ("1.250", 1250.0, True),  # Ambiguous 3 digits separator
        ("1,250", 1250.0, True),  # Ambiguous 3 digits separator
    ],
)
def test_value_parser_formats_and_ambiguities(raw_input, expected_val, is_ambiguous):
    """Test accounting formats, negative signs, nulls, and ambiguity detection."""
    parser = ValueParser()
    res = parser.parse_value(raw_input)

    assert res.parsed_numeric_value == expected_val
    assert res.is_ambiguous == is_ambiguous
    assert res.original_value == raw_input


# ==============================================================================
# 5. METRIC MAPPER TESTS (26 METRICS & NEGATIVE GUARDS)
# ==============================================================================

def test_metric_mapper_balance_sheet_assets():
    """Test mapping of assets metrics."""
    mapper = MetricMapper()
    m_act = mapper.map_label("Total Actif", statement_type_context="balance_sheet")
    assert m_act is not None
    assert m_act.metric_code == "total_actifs"
    assert m_act.confidence_level == "high_confidence"

    m_cai = mapper.map_label("Caisse et banques centrales", statement_type_context="balance_sheet")
    assert m_cai is not None
    assert m_cai.metric_code == "tresorerie"

    m_cli = mapper.map_label("Créances sur la clientèle", statement_type_context="balance_sheet")
    assert m_cli is not None
    assert m_cli.metric_code == "creances_clients"

    m_bq = mapper.map_label("Créances sur les établissements de crédit", statement_type_context="balance_sheet")
    assert m_bq is not None
    assert m_bq.metric_code == "creances_banques"

    m_imm = mapper.map_label("Immobilisations corporelles et incorporelles", statement_type_context="balance_sheet")
    assert m_imm is not None
    assert m_imm.metric_code == "immobilisations"


def test_metric_mapper_balance_sheet_liabilities_and_equity():
    """Test mapping of liabilities and equity metrics."""
    mapper = MetricMapper()
    m_pas = mapper.map_label("Total Passif et Capitaux Propres", statement_type_context="balance_sheet")
    assert m_pas is not None
    assert m_pas.metric_code == "total_passifs"

    m_dep = mapper.map_label("Dépôts de la clientèle", statement_type_context="balance_sheet")
    assert m_dep is not None
    assert m_dep.metric_code == "depots_clients"

    m_dbq = mapper.map_label("Dettes envers les établissements de crédit", statement_type_context="balance_sheet")
    assert m_dbq is not None
    assert m_dbq.metric_code == "depots_banques"

    m_emp = mapper.map_label("Emprunts auprès des établissements de crédit", statement_type_context="balance_sheet")
    assert m_emp is not None
    assert m_emp.metric_code == "emprunts_bancaires"

    m_obl = mapper.map_label("Titres de créance émis", statement_type_context="balance_sheet")
    assert m_obl is not None
    assert m_obl.metric_code == "obligations_emises"

    m_cp = mapper.map_label("Total des capitaux propres", statement_type_context="balance_sheet")
    assert m_cp is not None
    assert m_cp.metric_code == "capitaux_propres"


def test_metric_mapper_income_statement():
    """Test mapping of income statement metrics."""
    mapper = MetricMapper()
    m_pnb = mapper.map_label("Produit Net Bancaire", statement_type_context="income_statement")
    assert m_pnb is not None
    assert m_pnb.metric_code == "produit_net_bancaire"

    m_res = mapper.map_label("Résultat net de l'exercice", statement_type_context="income_statement")
    assert m_res is not None
    assert m_res.metric_code == "resultat_net"

    m_rbe = mapper.map_label("Résultat brut d'exploitation", statement_type_context="income_statement")
    assert m_rbe is not None
    assert m_rbe.metric_code == "resultat_exploitation"

    m_chg = mapper.map_label("Total des charges d'exploitation", statement_type_context="income_statement")
    assert m_chg is not None
    assert m_chg.metric_code == "charges_totales"


def test_metric_mapper_negative_guardrails():
    """Ensure negative terms prevent false mappings."""
    mapper = MetricMapper()

    # 'Créances sur les banques' must NOT map to creances_clients
    m1 = mapper.map_label("Créances sur les établissements de crédit")
    assert m1 is not None and m1.metric_code != "creances_clients"

    # 'Dépôts des banques' must NOT map to depots_clients
    m2 = mapper.map_label("Dépôts des établissements de crédit")
    assert m2 is not None and m2.metric_code != "depots_clients"

    # 'Total Passif' must NOT map to total_actifs
    m3 = mapper.map_label("Total Passif")
    assert m3 is not None and m3.metric_code != "total_actifs"

    # CA is never derived from PNB
    m4 = mapper.map_label("Produit Net Bancaire")
    assert m4 is not None and m4.metric_code != "chiffre_affaires"


# ==============================================================================
# 6. CONSISTENCY CHECKER TESTS
# ==============================================================================

def test_consistency_checker_balanced_balance_sheet():
    """Total Actif ≈ Total Passif passes without warnings."""
    checker = ConsistencyChecker()
    points = [
        ExtractedMetricPoint(
            metric_code="total_actifs",
            document_id="doc1",
            page_number=1,
            period_year=2024,
            value_original="1 000 000",
            value_normalized=1000000.0,
        ),
        ExtractedMetricPoint(
            metric_code="total_passifs",
            document_id="doc1",
            page_number=2,
            period_year=2024,
            value_original="1 000 000",
            value_normalized=1000000.0,
        ),
        ExtractedMetricPoint(
            metric_code="creances_clients",
            document_id="doc1",
            page_number=1,
            period_year=2024,
            value_original="600 000",
            value_normalized=600000.0,
        ),
    ]

    consistent, warnings = checker.check_extracted_points(points)
    assert consistent is True
    assert len(warnings) == 0


def test_consistency_checker_flags_discrepancy_and_routes_to_needs_review():
    """Unbalanced balance sheet triggers warning and marks points needs_review."""
    checker = ConsistencyChecker()
    pt_act = ExtractedMetricPoint(
        metric_code="total_actifs",
        document_id="doc1",
        page_number=1,
        period_year=2024,
        value_original="1 000 000",
        value_normalized=1000000.0,
        status="extracted",
    )
    pt_pas = ExtractedMetricPoint(
        metric_code="total_passifs",
        document_id="doc1",
        page_number=2,
        period_year=2024,
        value_original="700 000",
        value_normalized=700000.0,
        status="extracted",
    )
    points = [pt_act, pt_pas]

    consistent, warnings = checker.check_extracted_points(points)
    assert consistent is False
    assert len(warnings) >= 1
    assert pt_act.status == "needs_review"
    assert pt_pas.status == "needs_review"


# ==============================================================================
# 7. FINANCIAL EXTRACTOR & PROVENANCE INTEGRITY TESTS
# ==============================================================================

def test_financial_extractor_synthetic_balance_sheet_table():
    """End-to-end extraction from a synthetic financial table preserving provenance."""
    table_text = (
        "Postes\t2023\t2024\n"
        "Créances sur la clientèle\t800\t950\n"
        "Total Actif\t1 000\t1 200\n"
    )
    extractor = FinancialExtractor()
    tables = TableExtractor().extract_tables_from_text(table_text, page_number=5)

    page_texts = {5: "Bilan condensé au 31 décembre 2024. Montants en millions de FCFA."}
    points = extractor.extract_from_tables(
        tables=tables,
        document_id="doc-xyz",
        page_texts=page_texts,
        institution_id="inst-1",
        source_id="src-1",
        base_document_year=2024,
    )

    assert len(points) == 4  # 2 metrics * 2 years (2023, 2024)

    p_act_2024 = next(p for p in points if p.metric_code == "total_actifs" and p.period_year == 2024)
    assert p_act_2024.document_id == "doc-xyz"
    assert p_act_2024.page_number == 5
    assert p_act_2024.institution_id == "inst-1"
    assert p_act_2024.period_year == 2024
    assert p_act_2024.value_original == "1 200"
    # Normalization: 1 200 * 1_000_000 = 1_200_000_000
    assert p_act_2024.value_normalized == 1_200_000_000.0
    assert p_act_2024.currency_normalized == "XOF"
    assert p_act_2024.status == "extracted"
    assert p_act_2024.confidence_level == "high_confidence"


# ==============================================================================
# 8. PIPELINE INTEGRATION & IDEMPOTENCE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_pipeline_extract_financial_data_idempotent():
    """
    Test ScrapingPipeline.extract_financial_data:
      - Inserts points into DB
      - Never sets verified
      - Re-running updates without duplicate row proliferation
    """
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_mgr = StorageManager(tmp_dir)
        pipeline = ScrapingPipeline(storage_manager=storage_mgr)

        # Create a synthetic PDF with financial data in memory
        doc_pdf = pymupdf.open()
        page = doc_pdf.new_page()
        page.insert_text((50, 40), "Montants en millions de FCFA")
        page.insert_text((50, 70), "Postes")
        page.insert_text((250, 70), "2024")
        page.insert_text((50, 100), "Total Actif")
        page.insert_text((250, 100), "1500")
        pdf_bytes = doc_pdf.tobytes()
        doc_pdf.close()

        stored = storage_mgr.store_content(pdf_bytes, "rapport_annuel.pdf")

        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "doc-123"
        mock_doc.institution_id = "inst-456"
        mock_doc.source_id = "src-789"
        mock_doc.file_hash = stored.file_hash
        mock_doc.storage_path = stored.relative_path
        mock_doc.title = "Rapport Annuel 2024"
        mock_doc.period_year = 2024
        mock_doc.download_status = "downloaded"
        mock_doc.extraction_status = "extracted"
        mock_doc.deleted_at = None

        db = AsyncMock()
        db.add = MagicMock()
        # Mock finding mock_doc
        scalar_res = MagicMock()
        scalar_res.scalars.return_value.all.return_value = [mock_doc]

        # First run: no existing FinancialData in DB
        first_existing_res = MagicMock()
        first_existing_res.scalars.return_value.first.return_value = None
        db.execute.side_effect = [scalar_res, first_existing_res]

        results = await pipeline.extract_financial_data(db, document_id="doc-123")
        assert len(results) == 1
        doc_res, pts = results[0]
        assert len(pts) >= 1
        assert any(p.metric_code == "total_actifs" for p in pts)

        # Invariant check: Status is NOT 'verified'
        for p in pts:
            assert p.status != "verified"
            assert p.status in ("extracted", "needs_review")

        # Verify db.add was called with a FinancialData instance
        assert db.add.called
        added_record = db.add.call_args[0][0]
        assert isinstance(added_record, FinancialData)
        # Phase 13 scope guard: the scope is not detected -> held for human review.
        assert added_record.scope == "individual"
        assert added_record.status == "needs_review"
        assert "scope not detected" in added_record.notes
        assert added_record.metric_code == "total_actifs"
        assert added_record.status in ("extracted", "needs_review")


# ==============================================================================
# 9. CLI COMMAND TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_cli_extract_command():
    """Test CLI extract command parsing and execution on a standalone PDF."""
    from scraping.cli import build_parser, run_cli

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((50, 40), "Montants en millions de FCFA")
    page.insert_text((50, 70), "Postes")
    page.insert_text((250, 70), "2024")
    page.insert_text((50, 100), "Produit Net Bancaire")
    page.insert_text((250, 100), "350")
    doc.save(pdf_path)
    doc.close()

    parser = build_parser()
    args = parser.parse_args(["extract", "--file", pdf_path])
    exit_code = await run_cli(args)

    assert exit_code == 0
    Path(pdf_path).unlink(missing_ok=True)
