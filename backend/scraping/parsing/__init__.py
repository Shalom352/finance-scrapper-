"""
UMOA Banking Intelligence — PDF Parsing & Document Classification

Provides:
  - BaseParser: abstract interface for document parsers
  - PDFParser: PyMuPDF-based text and layout extractor
  - PageAnalyzer: keyword-based financial statement page candidate detector
  - DocumentClassifier: conservative document type classifier
  - Models: ParsedDocument, ParsedPage, PageAnalysis
  - Exceptions: PDFParsingError, InvalidPDFError, EmptyPDFError, UnsupportedPDFError
"""
from scraping.parsing.base import BaseParser
from scraping.parsing.classifier import DocumentClassifier
from scraping.parsing.consistency_checker import ConsistencyChecker
from scraping.parsing.exceptions import (
    EmptyPDFError,
    InvalidPDFError,
    PDFParsingError,
    PDFReadError,
    UnsupportedPDFError,
)
from scraping.parsing.financial_extractor import FinancialExtractor
from scraping.parsing.financial_mapper import MetricMapper, MetricMatch
from scraping.parsing.models import PageAnalysis, ParsedDocument, ParsedPage
from scraping.parsing.page_analyzer import PageAnalyzer
from scraping.parsing.pdf_parser import PDFParser, clean_text
from scraping.parsing.period_detector import PeriodDetector
from scraping.parsing.table_extractor import TableExtractor
from scraping.parsing.table_models import (
    ExtractedMetricPoint,
    FinancialTable,
    ParsedFinancialValue,
    PeriodColumn,
    TableCell,
    TableRow,
    UnitInfo,
)
from scraping.parsing.unit_detector import UnitDetector
from scraping.parsing.value_parser import ValueParser

__all__ = [
    "BaseParser",
    "PDFParser",
    "PageAnalyzer",
    "DocumentClassifier",
    "ParsedDocument",
    "ParsedPage",
    "PageAnalysis",
    "PDFParsingError",
    "InvalidPDFError",
    "PDFReadError",
    "UnsupportedPDFError",
    "EmptyPDFError",
    "clean_text",
    "TableCell",
    "TableRow",
    "FinancialTable",
    "PeriodColumn",
    "UnitInfo",
    "ParsedFinancialValue",
    "ExtractedMetricPoint",
    "TableExtractor",
    "PeriodDetector",
    "UnitDetector",
    "ValueParser",
    "MetricMapper",
    "MetricMatch",
    "ConsistencyChecker",
    "FinancialExtractor",
]
