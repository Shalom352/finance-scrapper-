"""
UMOA Banking Intelligence — Financial Table Extractor

Extracts structured tables from PDF pages using PyMuPDF (fitz).
Combines visual grid detection (find_tables) and spatial word clustering
for borderless, whitespace-aligned banking financial tables.
Preserves spatial bounding box geometry (x0, y0, x1, y1).
"""
import re
from typing import Any

from scraping.parsing.table_models import (
    FinancialTable,
    TableCell,
    TableRow,
)


class TableExtractor:
    """Extracts financial tables from PyMuPDF Page objects or structured tabular text."""

    def __init__(self, y_tolerance: float = 4.0, col_gap_threshold: float = 12.0) -> None:
        self.y_tolerance = y_tolerance
        self.col_gap_threshold = col_gap_threshold

    def extract_tables_from_page(self, page: Any, page_number: int) -> list[FinancialTable]:
        """
        Extract financial tables from a PyMuPDF Page object.

        First attempts PyMuPDF's built-in find_tables() for bordered tables.
        If no tables found or tables are incomplete, uses spatial word clustering.
        """
        tables: list[FinancialTable] = []

        # 1. Attempt PyMuPDF find_tables()
        if hasattr(page, "find_tables"):
            try:
                tabs = page.find_tables()
                for tab in tabs.tables:
                    extracted_data = tab.extract()
                    if extracted_data and len(extracted_data) >= 2:
                        ft = self._convert_pymupdf_table(extracted_data, page_number, tab.bbox)
                        if ft and ft.row_count >= 2 and ft.column_count >= 2:
                            tables.append(ft)
            except Exception:
                pass

        # 2. If no bordered table found, use spatial layout clustering from word coordinates
        if not tables and hasattr(page, "get_text"):
            words = page.get_text("words")
            if words:
                spatial_table = self._extract_spatial_table(words, page_number)
                if spatial_table and spatial_table.row_count >= 2 and spatial_table.column_count >= 2:
                    tables.append(spatial_table)

        return tables

    def extract_tables_from_text(self, text: str, page_number: int = 1) -> list[FinancialTable]:
        """
        Extract tabular structures from cleaned text containing tabs or columnar spaces.
        Used for synthetic test fixtures and textual fallbacks.
        """
        if not text:
            return []

        lines = [line.strip() for line in text.split("\n") if line.strip()]
        if len(lines) < 2:
            return []

        # Detect separator: tab or 2+ consecutive spaces
        table_rows: list[TableRow] = []
        max_cols = 0

        for r_idx, line in enumerate(lines):
            if "\t" in line:
                raw_cells = [c.strip() for c in line.split("\t")]
            else:
                raw_cells = [c.strip() for c in re.split(r"\s{2,}", line) if c.strip()]

            if len(raw_cells) >= 2:
                max_cols = max(max_cols, len(raw_cells))
                cells = [
                    TableCell(row_index=r_idx, col_index=c_idx, raw_text=c_text)
                    for c_idx, c_text in enumerate(raw_cells)
                ]
                table_rows.append(
                    TableRow(
                        row_index=r_idx,
                        cells=cells,
                        is_header=(r_idx == 0),
                        raw_line_text=line,
                    )
                )

        if len(table_rows) >= 2 and max_cols >= 2:
            headers = [c.raw_text for c in table_rows[0].cells]
            return [
                FinancialTable(
                    page_number=page_number,
                    rows=table_rows,
                    headers=headers,
                )
            ]

        return []

    def _convert_pymupdf_table(
        self,
        extracted_grid: list[list[str | None]],
        page_number: int,
        bbox: tuple[float, float, float, float] | None,
    ) -> FinancialTable | None:
        """Convert PyMuPDF extracted list-of-lists into a FinancialTable."""
        rows: list[TableRow] = []
        for r_idx, raw_row in enumerate(extracted_grid):
            cells: list[TableCell] = []
            for c_idx, raw_cell in enumerate(raw_row):
                cell_text = (raw_cell or "").strip()
                cells.append(
                    TableCell(
                        row_index=r_idx,
                        col_index=c_idx,
                        raw_text=cell_text,
                    )
                )
            rows.append(
                TableRow(
                    row_index=r_idx,
                    cells=cells,
                    is_header=(r_idx == 0),
                    raw_line_text=" ".join(c.raw_text for c in cells if c.raw_text),
                )
            )

        if not rows:
            return None

        headers = [c.raw_text for c in rows[0].cells]
        return FinancialTable(
            page_number=page_number,
            rows=rows,
            headers=headers,
            bbox=bbox,
        )

    def _extract_spatial_table(
        self,
        words: list[tuple[float, float, float, float, str, int, int, int]],
        page_number: int,
    ) -> FinancialTable | None:
        """
        Group words by vertical lines and horizontal gaps to reconstruct borderless tables.
        words tuple: (x0, y0, x1, y1, "word", block_no, line_no, word_no)
        """
        # Sort words primarily by top-to-bottom (y0), secondarily left-to-right (x0)
        sorted_words = sorted(words, key=lambda w: (round(w[1] / self.y_tolerance) * self.y_tolerance, w[0]))

        # Group words by line (similar y0 within y_tolerance)
        lines: list[list[tuple[float, float, float, float, str]]] = []
        current_line: list[tuple[float, float, float, float, str]] = []
        current_y = None

        for w in sorted_words:
            x0, y0, x1, y1, text = w[0], w[1], w[2], w[3], w[4]
            if current_y is None:
                current_y = y0
                current_line.append((x0, y0, x1, y1, text))
            elif abs(y0 - current_y) <= self.y_tolerance:
                current_line.append((x0, y0, x1, y1, text))
            else:
                if current_line:
                    lines.append(current_line)
                current_line = [(x0, y0, x1, y1, text)]
                current_y = y0

        if current_line:
            lines.append(current_line)

        # For each line, group words into column cells based on horizontal gap
        table_rows: list[TableRow] = []
        all_x_coords: list[float] = []

        for r_idx, line in enumerate(lines):
            # Sort words in line by x0
            line_words = sorted(line, key=lambda w: w[0])
            cells: list[TableCell] = []
            cur_cell_words: list[str] = []
            cur_bbox: list[float] | None = None

            for w in line_words:
                wx0, wy0, wx1, wy1, wtext = w
                if not cur_cell_words:
                    cur_cell_words = [wtext]
                    cur_bbox = [wx0, wy0, wx1, wy1]
                else:
                    gap = wx0 - cur_bbox[2]  # distance from previous word right edge
                    if gap > self.col_gap_threshold:
                        # Finalize previous cell
                        c_idx = len(cells)
                        cells.append(
                            TableCell(
                                row_index=r_idx,
                                col_index=c_idx,
                                raw_text=" ".join(cur_cell_words),
                                bbox=(cur_bbox[0], cur_bbox[1], cur_bbox[2], cur_bbox[3]),
                            )
                        )
                        all_x_coords.append(cur_bbox[0])
                        cur_cell_words = [wtext]
                        cur_bbox = [wx0, wy0, wx1, wy1]
                    else:
                        cur_cell_words.append(wtext)
                        cur_bbox[2] = max(cur_bbox[2], wx1)
                        cur_bbox[3] = max(cur_bbox[3], wy1)

            if cur_cell_words and cur_bbox:
                c_idx = len(cells)
                cells.append(
                    TableCell(
                        row_index=r_idx,
                        col_index=c_idx,
                        raw_text=" ".join(cur_cell_words),
                        bbox=(cur_bbox[0], cur_bbox[1], cur_bbox[2], cur_bbox[3]),
                    )
                )
                all_x_coords.append(cur_bbox[0])

            # Keep line if it has at least 2 distinct cells
            if len(cells) >= 2:
                table_rows.append(
                    TableRow(
                        row_index=len(table_rows),
                        cells=cells,
                        is_header=(len(table_rows) == 0),
                        raw_line_text=" ".join(c.raw_text for c in cells),
                    )
                )

        if len(table_rows) >= 2:
            headers = [c.raw_text for c in table_rows[0].cells]
            return FinancialTable(
                page_number=page_number,
                rows=table_rows,
                headers=headers,
            )

        return None
