"""
UMOA Banking Intelligence — Financial Table Data Models

Dataclasses for representing extracted tabular geometry, period columns,
units/currencies, parsed values, and extracted financial metric points.
"""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TableCell:
    """Represents a single cell within an extracted table."""

    row_index: int
    col_index: int
    raw_text: str
    bbox: tuple[float, float, float, float] | None = None  # (x0, y0, x1, y1)


@dataclass
class TableRow:
    """Represents a row in an extracted table."""

    row_index: int
    cells: list[TableCell] = field(default_factory=list)
    is_header: bool = False
    raw_line_text: str = ""

    def get_cell(self, col_index: int) -> TableCell | None:
        """Get cell at specific column index."""
        for c in self.cells:
            if c.col_index == col_index:
                return c
        return None

    @property
    def cell_texts(self) -> list[str]:
        """Return list of text content across cells in order."""
        return [c.raw_text.strip() for c in self.cells]


@dataclass
class FinancialTable:
    """Represents an extracted financial table from a PDF page."""

    page_number: int  # 1-indexed
    title: str | None = None
    rows: list[TableRow] = field(default_factory=list)
    headers: list[str] = field(default_factory=list)
    bbox: tuple[float, float, float, float] | None = None
    table_type: str | None = None  # balance_sheet | income_statement | cash_flow | other

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def column_count(self) -> int:
        if self.headers:
            return len(self.headers)
        if self.rows:
            return max(len(r.cells) for r in self.rows)
        return 0

    def get_cell(self, row_index: int, col_index: int) -> TableCell | None:
        for r in self.rows:
            if r.row_index == row_index:
                return r.get_cell(col_index)
        return None


@dataclass
class PeriodColumn:
    """Represents an identified financial period column in a table."""

    column_index: int
    period_year: int
    period_type: str = "annual"  # annual | semi_annual | quarterly
    period_label: str | None = None
    evidence: str = ""


@dataclass
class UnitInfo:
    """Currency and scale information detected from document or table context."""

    currency: str | None = None  # e.g. XOF, EUR, USD
    scale: int = 1  # 1, 1_000, 1_000_000, 1_000_000_000
    unit_label: str | None = None  # e.g. "millions", "milliers", "unites"
    evidence: str = ""


@dataclass
class ParsedFinancialValue:
    """Result of parsing a raw text string representing an accounting number."""

    original_value: str
    parsed_numeric_value: float | None = None
    is_ambiguous: bool = False
    ambiguity_reason: str | None = None


@dataclass
class ExtractedMetricPoint:
    """
    A single extracted financial metric point with complete provenance.

    Follows the database model FinancialData fields and V1 validation invariants.
    """

    metric_code: str
    document_id: str
    page_number: int
    period_year: int
    value_original: str
    institution_id: str | None = None
    source_id: str | None = None
    period_type: str = "annual"
    period_label: str | None = None
    unit_original: str | None = None
    currency_original: str | None = None
    value_normalized: float | None = None
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    extraction_method: str = "pdf_table"  # pdf_table | pdf_text
    confidence_score: float = 0.0  # 0.0 - 1.0
    confidence_level: str = "low_confidence"  # high_confidence | medium_confidence | low_confidence
    status: str = "extracted"  # extracted | needs_review
    matched_label: str = ""
    table_context: str | None = None
    notes: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
