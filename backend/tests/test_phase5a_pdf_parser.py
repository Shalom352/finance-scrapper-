"""
UMOA Banking Intelligence — Phase 5A PDF Parser & Classification Tests

Comprehensive test suite covering:
  - Valid PDF opening, page counting, and text extraction
  - Page-by-page preservation and 1-indexed page numbers
  - Empty PDF and empty page detection
  - Corrupted PDF handling (InvalidPDFError)
  - Scanned PDF detection (possibly_scanned vs text_based)
  - PageAnalyzer scoring for Bilan, Compte de résultat, Flux de trésorerie, Annexes
  - DocumentClassifier conservative classification (annual_report, financial_statements, unknown)
  - Technical text normalization (accents preservation, financial digits, signs +, -, %, parentheses)
  - Provenance tracking (document_id -> page_number -> content)
  - Pipeline database status update (pending -> extracted / failed)
  - CLI parse command execution
"""
import gc
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pymupdf
import pytest

from app.models.document import Document
from scraping.parsing.classifier import DocumentClassifier
from scraping.parsing.exceptions import (
    InvalidPDFError,
)
from scraping.parsing.models import ParsedPage
from scraping.parsing.page_analyzer import PageAnalyzer
from scraping.parsing.pdf_parser import PDFParser, clean_text
from scraping.pipeline import ScrapingPipeline
from scraping.storage.manager import StorageManager

# ============================================================
# Helpers to generate synthetic test PDFs in memory
# ============================================================

def create_synthetic_pdf(
    pages_text: list[str],
    add_image_page: bool = False,
) -> bytes:
    """Generate a valid PDF in memory using PyMuPDF."""
    doc = pymupdf.open()
    for text in pages_text:
        page = doc.new_page()
        if text:
            page.insert_text((50, 72), text)

    if add_image_page:
        # Create an image-only page (pixmap inserted as image)
        page = doc.new_page()
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 100, 100), 1)
        pix.clear_with(255)  # white image
        page.insert_image(pymupdf.Rect(50, 50, 200, 200), pixmap=pix)

    pdf_bytes = doc.tobytes()
    doc.close()
    return pdf_bytes


# ============================================================
# 1. Technical Normalization Tests
# ============================================================

class TestTextNormalization:
    """Test clean_text technical normalization rules."""

    def test_clean_text_preserves_accents_and_french_text(self):
        raw = "États financiers au 31 décembre : Créances douteuses et Trésorerie nette.\r\n"
        cleaned = clean_text(raw)
        assert "États financiers" in cleaned
        assert "décembre" in cleaned
        assert "Créances" in cleaned
        assert "Trésorerie" in cleaned
        assert "\r" not in cleaned

    def test_clean_text_preserves_financial_numbers_and_signs(self):
        raw = "Bilan : 1 250 000 XOF | Marge : +12,5 % | Perte : -450 000 | Provisions : (85 000)\n"
        cleaned = clean_text(raw)
        assert "1 250 000" in cleaned
        assert "+12,5 %" in cleaned
        assert "-450 000" in cleaned
        assert "(85 000)" in cleaned

    def test_clean_text_strips_hostile_control_chars_preserves_tabs(self):
        raw = "Actif\tPassif\x00\x07\x1b\nTotal\t1 000 000\n"
        cleaned = clean_text(raw)
        assert "\t" in cleaned
        assert "\x00" not in cleaned
        assert "\x07" not in cleaned
        assert "\x1b" not in cleaned


# ============================================================
# 2. PDF Parser Core Tests
# ============================================================

class TestPDFParserCore:
    """Test PDFParser opening, page extraction, and error handling."""

    @pytest.mark.asyncio
    async def test_parse_valid_multipage_pdf(self):
        parser = PDFParser()
        pages_content = [
            "BCEAO - Rapport Annuel 2023\nPage de garde",
            "Bilan au 31 décembre 2023\nTotal actif : 15 000 000 millions XOF\nTotal passif : 15 000 000 millions XOF",
            "Compte de résultat\nProduit net bancaire : 850 000 millions XOF\nRésultat net : 120 000 millions XOF",
        ]
        pdf_bytes = create_synthetic_pdf(pages_content)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            parsed = await parser.parse(tmp_path, document_id="doc-uuid-123")
            assert parsed.page_count == 3
            assert parsed.document_id == "doc-uuid-123"
            assert parsed.scan_status == "text_based"
            assert parsed.total_char_count > 100
            assert len(parsed.pages) == 3

            # Verify 1-indexed page numbering and provenance
            p1 = parsed.get_page(1)
            assert p1 is not None
            assert p1.page_number == 1
            assert "Rapport Annuel 2023" in p1.text
            assert p1.is_empty is False

            p2 = parsed.get_page(2)
            assert p2 is not None
            assert "Total actif" in p2.text

            p3 = parsed.get_page(3)
            assert p3 is not None
            assert "Produit net bancaire" in p3.text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_nonexistent_file_raises_invalid_pdf_error(self):
        parser = PDFParser()
        with pytest.raises(InvalidPDFError) as exc_info:
            await parser.parse("nonexistent_file_path.pdf")
        assert "does not exist" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_parse_corrupted_file_raises_invalid_pdf_error(self):
        parser = PDFParser()
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(b"NOT A REAL PDF FILE CORRUPTED CONTENT")
            tmp_path = tmp.name

        try:
            with pytest.raises(InvalidPDFError) as exc_info:
                await parser.parse(tmp_path)
            assert "Corrupted or invalid PDF" in str(exc_info.value)
        finally:
            gc.collect()
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_empty_page_detection(self):
        parser = PDFParser()
        # Page 1 has text, Page 2 is completely empty
        pdf_bytes = create_synthetic_pdf(["Page 1 with text", ""])

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            parsed = await parser.parse(tmp_path)
            assert parsed.page_count == 2
            p1 = parsed.get_page(1)
            p2 = parsed.get_page(2)
            assert p1 is not None and p1.is_empty is False
            assert p2 is not None and p2.is_empty is True
            assert p2.char_count == 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    @pytest.mark.asyncio
    async def test_parse_scanned_pdf_detection(self):
        parser = PDFParser()
        # Create an image-only page with no text
        pdf_bytes = create_synthetic_pdf([], add_image_page=True)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            parsed = await parser.parse(tmp_path)
            assert parsed.page_count == 1
            assert parsed.scan_status == "possibly_scanned"
            assert parsed.pages[0].has_images is True
            assert parsed.pages[0].char_count == 0
        finally:
            Path(tmp_path).unlink(missing_ok=True)


# ============================================================
# 3. Page Analyzer Tests (Financial Statement Detection)
# ============================================================

class TestPageAnalyzer:
    """Test deterministic keyword scoring for Bilan, Résultat, Trésorerie, Annexes."""

    def test_analyze_page_detects_balance_sheet(self):
        analyzer = PageAnalyzer()
        text = """
        BILAN AU 31 DÉCEMBRE 2023
        ACTIF IMMOBILISÉ
        Créances sur la clientèle : 4 500 000
        Actif circulant : 1 200 000
        TOTAL DE L'ACTIF : 5 700 000
        PASSIF
        Capitaux propres : 2 000 000
        Dépôts de la clientèle : 3 700 000
        TOTAL DU PASSIF : 5 700 000
        """
        analysis = analyzer.analyze_page(page_number=42, text=text)

        assert analysis.page_number == 42
        assert analysis.categories["balance_sheet"] >= 0.70
        assert analysis.is_financial_statement_candidate is True
        assert analysis.detected_statement_type == "balance_sheet"
        assert "bilan" in analysis.matched_terms
        assert "total actif" in analysis.matched_terms or "total de l'actif" in analysis.matched_terms

    def test_analyze_page_detects_income_statement(self):
        analyzer = PageAnalyzer()
        text = """
        COMPTE DE RÉSULTAT
        Produits d'exploitation bancaire
        Charges d'exploitation bancaire
        PRODUIT NET BANCAIRE : 1 450 000
        Charges générales d'exploitation : -650 000
        Dotations aux amortissements : -120 000
        Coût du risque : -80 000
        RÉSULTAT D'EXPLOITATION : 600 000
        RÉSULTAT NET DE L'EXERCICE : 480 000
        """
        analysis = analyzer.analyze_page(page_number=43, text=text)

        assert analysis.categories["income_statement"] >= 0.70
        assert analysis.is_financial_statement_candidate is True
        assert analysis.detected_statement_type == "income_statement"
        assert "compte de resultat" in analysis.matched_terms
        assert "produit net bancaire" in analysis.matched_terms

    def test_analyze_page_detects_cash_flow(self):
        analyzer = PageAnalyzer()
        text = """
        TABLEAU DES FLUX DE TRÉSORERIE
        Flux de trésorerie provenant des activités d'exploitation : 350 000
        Flux de trésorerie affectés aux activités d'investissement : -120 000
        Flux de trésorerie affectés aux activités de financement : -80 000
        Variation nette de la trésorerie : 150 000
        Trésorerie à l'ouverture : 400 000
        Trésorerie à la clôture : 550 000
        """
        analysis = analyzer.analyze_page(page_number=44, text=text)

        assert analysis.categories["cash_flow"] >= 0.70
        assert analysis.is_financial_statement_candidate is True
        assert analysis.detected_statement_type == "cash_flow"
        assert "tableau des flux de tresorerie" in analysis.matched_terms

    def test_analyze_page_detects_notes_annexes(self):
        analyzer = PageAnalyzer()
        text = """
        NOTES AUX ÉTATS FINANCIERS
        Note 1 : Principes et méthodes comptables
        Informations complémentaires relatives aux règles d'évaluation.
        Engagements hors bilan et garanties données.
        """
        analysis = analyzer.analyze_page(page_number=45, text=text)

        assert analysis.categories["notes"] >= 0.50
        assert analysis.is_financial_statement_candidate is True
        assert analysis.detected_statement_type == "notes"

    def test_analyze_page_non_financial_text_gives_zero_scores(self):
        analyzer = PageAnalyzer()
        text = "Allocution de Monsieur le Gouverneur lors de la conférence de presse annuelle à Dakar."
        analysis = analyzer.analyze_page(page_number=1, text=text)

        assert analysis.is_financial_statement_candidate is False
        assert analysis.detected_statement_type is None
        assert all(score < 0.20 for score in analysis.categories.values())


# ============================================================
# 4. Document Classifier Tests
# ============================================================

class TestDocumentClassifier:
    """Test conservative document type classification."""

    def test_classify_annual_report(self):
        classifier = DocumentClassifier()
        analyzer = PageAnalyzer()

        p1_text = "Banque Centrale des États de l'Afrique de l'Ouest\nRAPPORT ANNUEL 2023\nExercice clos le 31 décembre 2023"
        p2_text = "Sommaire\n1. Contexte macroéconomique\n2. États financiers\n3. Bilan et Compte de résultat"

        p1 = ParsedPage(page_number=1, text=p1_text, char_count=len(p1_text), word_count=len(p1_text.split()))
        p2 = ParsedPage(page_number=2, text=p2_text, char_count=len(p2_text), word_count=len(p2_text.split()))

        a1 = analyzer.analyze_page(1, p1_text)
        a2 = analyzer.analyze_page(2, p2_text)

        doc_type, conf = classifier.classify([p1, p2], [a1, a2], document_title="Rapport Annuel BCEAO 2023")

        assert doc_type == "annual_report"
        assert conf >= 0.70

    def test_classify_regulatory_report(self):
        classifier = DocumentClassifier()
        analyzer = PageAnalyzer()

        p1_text = "Commission Bancaire de l'UMOA\nLa Situation Bancaire dans l'UMOA\nSupervision bancaire et surveillance du système"
        p1 = ParsedPage(page_number=1, text=p1_text, char_count=len(p1_text), word_count=len(p1_text.split()))
        a1 = analyzer.analyze_page(1, p1_text)

        doc_type, conf = classifier.classify([p1], [a1], document_title="Situation Bancaire 2022")

        assert doc_type == "regulatory_report"
        assert conf >= 0.70

    def test_classify_statistical_bulletin(self):
        classifier = DocumentClassifier()
        analyzer = PageAnalyzer()

        p1_text = "BCEAO - Bulletin des statistiques monétaires et financières\nSéries statistiques mensuelles"
        p1 = ParsedPage(page_number=1, text=p1_text, char_count=len(p1_text), word_count=len(p1_text.split()))
        a1 = analyzer.analyze_page(1, p1_text)

        doc_type, conf = classifier.classify([p1], [a1], document_title="Bulletin des statistiques")

        assert doc_type == "statistical_bulletin"
        assert conf >= 0.70

    def test_classify_ambiguous_content_returns_unknown(self):
        classifier = DocumentClassifier()
        analyzer = PageAnalyzer()

        p1_text = "Texte générique sans indicateur spécifique de rapport financier."
        p1 = ParsedPage(page_number=1, text=p1_text, char_count=len(p1_text), word_count=len(p1_text.split()))
        a1 = analyzer.analyze_page(1, p1_text)

        doc_type, conf = classifier.classify([p1], [a1], document_title="Document quelconque")

        # Must return unknown instead of inventing a classification
        assert doc_type == "unknown"
        assert conf == 0.0


# ============================================================
# 5. Pipeline DB Integration Tests
# ============================================================

class TestPipelineParsingIntegration:
    """Test parse_downloaded_documents database status transitions."""

    @pytest.mark.asyncio
    async def test_parse_downloaded_documents_updates_db_status(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = StorageManager(storage_root=tmpdir)
            pipeline = ScrapingPipeline(storage_manager=storage)

            # Store a synthetic PDF in the storage
            pdf_bytes = create_synthetic_pdf([
                "Rapport Annuel 2023\nPage de garde",
                "BILAN\nTotal actif : 1 000 000\nTotal passif : 1 000 000",
            ])
            st_res = storage.store_content(pdf_bytes, "test.pdf")

            # Mock Document model row
            doc = Document(
                title="Rapport Annuel 2023",
                document_type="annual_report",
                source_id="src-1",
                download_status="downloaded",
                extraction_status="pending",
                file_hash=st_res.file_hash,
                file_size=st_res.file_size,
                storage_path=st_res.relative_path,
            )
            doc.id = "doc-parsing-1"

            mock_db = AsyncMock()
            res_query = MagicMock()
            res_query.scalars.return_value.all.return_value = [doc]
            mock_db.execute.return_value = res_query

            results = await pipeline.parse_downloaded_documents(mock_db, document_id="doc-parsing-1")

            assert len(results) == 1
            updated_doc, parsed_doc = results[0]

            assert updated_doc.extraction_status == "extracted"
            assert updated_doc.page_count == 2
            assert updated_doc.extracted_at is not None
            assert updated_doc.error_message is None
            assert parsed_doc is not None
            assert parsed_doc.page_count == 2
            assert mock_db.commit.called


# ============================================================
# 6. CLI Parse Command Tests
# ============================================================

class TestCLIParseCommand:
    """Test python -m scraping parse CLI arguments and execution."""

    @pytest.mark.asyncio
    async def test_cli_parse_file_execution(self):
        from scraping.cli import build_parser, run_cli

        pdf_bytes = create_synthetic_pdf(["Test Document Page 1", "BILAN\nTotal actif : 500 000"])
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            parser = build_parser()
            args = parser.parse_args(["parse", "--file", tmp_path])
            assert args.command == "parse"
            assert args.file == tmp_path

            exit_code = await run_cli(args)
            assert exit_code == 0
        finally:
            gc.collect()
            Path(tmp_path).unlink(missing_ok=True)
