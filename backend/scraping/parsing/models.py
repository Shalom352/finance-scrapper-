"""
UMOA Banking Intelligence — Parsing Data Models

Dataclasses capturing page-by-page text, structural analysis, and document classifications.
Ensures rigorous provenance (document_id -> page_number -> content).
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ParsedPage:
    """Represents a single parsed page from a document."""

    page_number: int  # 1-indexed
    text: str
    char_count: int
    word_count: int
    is_empty: bool = False
    has_images: bool = False
    image_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PageAnalysis:
    """Structural and semantic keyword analysis for a single page."""

    page_number: int  # 1-indexed
    categories: dict[str, float] = field(default_factory=dict)
    matched_terms: list[str] = field(default_factory=list)
    is_financial_statement_candidate: bool = False
    detected_statement_type: str | None = None  # balance_sheet | income_statement | cash_flow | notes


@dataclass
class ParsedDocument:
    """Full parsing result of a document with pages, analysis, and classification."""

    file_path: str
    page_count: int
    document_id: str | None = None
    scan_status: str = "text_based"  # text_based | possibly_scanned | empty
    total_char_count: int = 0
    pages: list[ParsedPage] = field(default_factory=list)
    page_analyses: list[PageAnalysis] = field(default_factory=list)
    document_classification: str = "unknown"  # annual_report | financial_statements | regulatory_report | statistical_bulletin | other | unknown
    classification_confidence: float = 0.0
    financial_statement_candidates: dict[str, list[int]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def get_page(self, page_number: int) -> ParsedPage | None:
        """Retrieve a specific page by 1-indexed page number."""
        for p in self.pages:
            if p.page_number == page_number:
                return p
        return None

    def get_page_analysis(self, page_number: int) -> PageAnalysis | None:
        """Retrieve analysis for a specific page by 1-indexed page number."""
        for a in self.page_analyses:
            if a.page_number == page_number:
                return a
        return None
