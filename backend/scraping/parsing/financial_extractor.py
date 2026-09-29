"""
UMOA Banking Intelligence — Financial Extractor

Orchestrates table extraction, period detection, unit detection, value parsing,
and conservative metric mapping across candidate pages of a document.
"""
from pathlib import Path

import pymupdf

from app.core.logging import get_logger
from scraping.parsing.consistency_checker import ConsistencyChecker
from scraping.parsing.financial_mapper import MetricMapper
from scraping.parsing.models import ParsedDocument
from scraping.parsing.period_detector import PeriodDetector
from scraping.parsing.table_extractor import TableExtractor
from scraping.parsing.table_models import (
    ExtractedMetricPoint,
    FinancialTable,
)
from scraping.parsing.unit_detector import UnitDetector
from scraping.parsing.value_parser import ValueParser

logger = get_logger(__name__)


class FinancialExtractor:
    """Orchestrator for extracting 26 financial metrics from PDF documents."""

    def __init__(
        self,
        table_extractor: TableExtractor | None = None,
        period_detector: PeriodDetector | None = None,
        unit_detector: UnitDetector | None = None,
        value_parser: ValueParser | None = None,
        metric_mapper: MetricMapper | None = None,
        consistency_checker: ConsistencyChecker | None = None,
    ) -> None:
        self.table_extractor = table_extractor or TableExtractor()
        self.period_detector = period_detector or PeriodDetector()
        self.unit_detector = unit_detector or UnitDetector()
        self.value_parser = value_parser or ValueParser()
        self.metric_mapper = metric_mapper or MetricMapper()
        self.consistency_checker = consistency_checker or ConsistencyChecker()

    def extract_from_tables(
        self,
        tables: list[FinancialTable],
        document_id: str,
        page_texts: dict[int, str] | None = None,
        institution_id: str | None = None,
        source_id: str | None = None,
        base_document_year: int | None = None,
    ) -> list[ExtractedMetricPoint]:
        """
        Extract financial metric points from a list of pre-extracted FinancialTable objects.
        """
        all_points: list[ExtractedMetricPoint] = []
        page_texts = page_texts or {}

        for table in tables:
            page_text = page_texts.get(table.page_number, "")
            unit_info = self.unit_detector.detect_units(
                text_context=page_text,
                table_title=table.title,
                header_texts=table.headers,
            )

            period_cols = self.period_detector.detect_period_columns(
                headers=table.headers,
                base_document_year=base_document_year,
            )

            if not period_cols:
                logger.debug("no_period_columns_in_table", page_number=table.page_number)
                continue

            for row in table.rows:
                if row.is_header or len(row.cells) < 2:
                    continue

                raw_label = row.cells[0].raw_text.strip()
                if not raw_label:
                    continue

                metric_match = self.metric_mapper.map_label(
                    raw_label=raw_label,
                    statement_type_context=table.table_type,
                )

                if not metric_match:
                    continue

                for p_col in period_cols:
                    val_cell = row.get_cell(p_col.column_index)
                    if not val_cell or not val_cell.raw_text.strip():
                        continue

                    parsed_val = self.value_parser.parse_value(val_cell.raw_text)
                    if parsed_val.parsed_numeric_value is None:
                        continue

                    # Calculate normalized value using detected scale
                    norm_val = parsed_val.parsed_numeric_value * unit_info.scale

                    # Determine validation status
                    status = "extracted"
                    notes_parts = [f"Mapped from '{raw_label}' ({metric_match.reason})"]
                    if unit_info.evidence:
                        notes_parts.append(f"Units: {unit_info.evidence}")

                    if parsed_val.is_ambiguous or metric_match.confidence_level == "low_confidence":
                        status = "needs_review"
                        if parsed_val.ambiguity_reason:
                            notes_parts.append(f"Ambiguity: {parsed_val.ambiguity_reason}")

                    point = ExtractedMetricPoint(
                        metric_code=metric_match.metric_code,
                        document_id=document_id,
                        page_number=table.page_number,
                        period_year=p_col.period_year,
                        period_type=p_col.period_type,
                        period_label=p_col.period_label,
                        value_original=parsed_val.original_value,
                        unit_original=unit_info.unit_label,
                        currency_original=unit_info.currency,
                        value_normalized=norm_val,
                        unit_normalized=unit_info.currency or unit_info.unit_label,
                        currency_normalized=unit_info.currency,
                        institution_id=institution_id,
                        source_id=source_id,
                        extraction_method="pdf_table",
                        confidence_score=metric_match.confidence_score,
                        confidence_level=metric_match.confidence_level,
                        status=status,
                        matched_label=raw_label,
                        table_context=table.title or f"Page {table.page_number} Table",
                        notes=" | ".join(notes_parts),
                    )
                    all_points.append(point)

        # Run consistency checks on extracted points
        if all_points:
            self.consistency_checker.check_extracted_points(all_points)

        return all_points

    async def extract_from_parsed_document(
        self,
        parsed_doc: ParsedDocument,
        pdf_path: str | Path,
        institution_id: str | None = None,
        source_id: str | None = None,
        base_document_year: int | None = None,
    ) -> list[ExtractedMetricPoint]:
        """
        Extract financial metric points from a ParsedDocument and its underlying PDF.
        """
        path = Path(pdf_path)
        if not path.is_file():
            return []

        doc_bytes = path.read_bytes()
        doc = pymupdf.open(stream=doc_bytes, filetype="pdf")

        try:
            # Determine pages to inspect: candidate pages first, else all
            candidate_pages: set[int] = set()
            for st_type, p_list in parsed_doc.financial_statement_candidates.items():
                candidate_pages.update(p_list)

            target_page_numbers = sorted(candidate_pages) if candidate_pages else list(range(1, doc.page_count + 1))

            tables: list[FinancialTable] = []
            page_texts: dict[int, str] = {}

            for p_num in target_page_numbers:
                if 1 <= p_num <= doc.page_count:
                    page = doc[p_num - 1]
                    page_obj = parsed_doc.get_page(p_num)
                    page_text = page_obj.text if page_obj else page.get_text("text")
                    page_texts[p_num] = page_text

                    # Identify detected statement type if any
                    analysis = parsed_doc.get_page_analysis(p_num)
                    st_type = analysis.detected_statement_type if analysis else None

                    extracted_tabs = self.table_extractor.extract_tables_from_page(page, page_number=p_num)
                    for t in extracted_tabs:
                        t.table_type = st_type
                        tables.append(t)

            return self.extract_from_tables(
                tables=tables,
                document_id=parsed_doc.document_id or "",
                page_texts=page_texts,
                institution_id=institution_id,
                source_id=source_id,
                base_document_year=base_document_year,
            )
        finally:
            doc.close()
