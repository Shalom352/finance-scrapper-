"""
Institution-specific financial statements parser (Phase 17).

Reads comparative statements published by a bank itself (e.g. BOA "Bilan et compte de résultat"
synoptic pages: ACTIF / PASSIF / COMPTE DE RÉSULTAT side by side, two years each, or the
"Bilan comparé des deux derniers exercices" pages of the annual reports).

Strict rules (DATA MISSING > DATA WRONG):
  - only pages whose text layer is reliable ('ok' in scraping.quality.text_layer) are read;
  - only the published PCB lines already mapped 1:1 to the catalogue are read (same mapping as the
    BCEAO fascicle, plus the exact variant "TOTAL ACTIF" of "TOTAL DE L'ACTIF");
  - a value is assigned to a year only through the year headers of ITS OWN table (x position);
    two values for one header, or none, → missing;
  - the unit / currency are taken ONLY from an explicit statement on the page ("(en F CFA)",
    "en millions de F CFA"); otherwise the original value is kept and NOT normalized;
  - interim (semester / quarter) statements are not read.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import pymupdf

from scraping.quality.text_layer import assess_page
from scraping.universe.fascicle import CHECK_LINES, LINE_TO_METRIC, _lines, parse_amount
from scraping.universe.normalize import normalize_name

INSTITUTION_LINE_TO_METRIC: dict[str, str] = {
    **LINE_TO_METRIC,
    "TOTAL ACTIF": "total_actifs",  # exact variant of "TOTAL DE L'ACTIF" (same balance-sheet line)
}

_YEAR_HEADER = re.compile(r"^(?:(\d{2})/(\d{2})/)?((?:19|20)\d{2})$")
_UNIT_MILLIONS = re.compile(r"en\s+millions\s+de\s+(?:F\s*CFA|francs\s+CFA)", re.IGNORECASE)
_UNIT_UNITS = re.compile(r"\(\s*en\s+(?:F\s*CFA|francs\s+CFA)\s*\)|\ben\s+francs\s+CFA\b", re.IGNORECASE)
_INTERIM = re.compile(r"\b(SEMESTRE|SEMESTRIEL|TRIMESTRE|TRIMESTRIEL|30 06|30 09|31 03)\b")
ROW_TOLERANCE = 1.8  # synoptic rows are ~4 pt apart
COLUMN_TOLERANCE = 35.0


@dataclass
class StatementValue:
    metric_code: str
    line_label: str
    year: int
    raw: str
    value: Decimal
    page_number: int
    unit: str | None  # 'unit' | 'millions' | None (not stated)
    currency: str | None  # 'XOF' | None (not stated)
    multiplier: Decimal | None


@dataclass
class StatementParseResult:
    values: list[StatementValue] = field(default_factory=list)
    check_values: dict[tuple[str, int], tuple[Decimal, Decimal | None]] = field(default_factory=dict)
    statement_pages: list[int] = field(default_factory=list)
    skipped_pages: dict[int, str] = field(default_factory=dict)
    skipped_cells: list[str] = field(default_factory=list)


def page_unit(text: str) -> tuple[str | None, str | None, Decimal | None]:
    if _UNIT_MILLIONS.search(text):
        return "millions", "XOF", Decimal(1_000_000)
    if _UNIT_UNITS.search(text):
        return "unit", "XOF", Decimal(1)
    return None, None, None


class InstitutionStatementParser:
    def parse_bytes(self, content: bytes, title: str = "") -> StatementParseResult:
        result = StatementParseResult()
        if _INTERIM.search(normalize_name(title)):
            result.skipped_pages[0] = "interim statement (semester / quarter) not handled"
            return result
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            for pno in range(pdf.page_count):
                page = pdf[pno]
                text = page.get_text()
                quality = assess_page(text, pno + 1)
                if quality.status != "ok":
                    result.skipped_pages[pno + 1] = f"text layer {quality.status}"
                    continue
                self._parse_page(page, pno + 1, text, result)
        return result

    @staticmethod
    def _year_headers(page: pymupdf.Page) -> list[tuple[float, float, float, int]]:
        """Year column headers read at WORD level (x0, y0, xmid, year): "2021 VARIATION" printed as one
        line still yields a precise position for 2021. Only full-year (31/12) dates are accepted."""
        out = []
        for x0, y0, x1, _y1, word, *_ in page.get_text("words"):
            m = _YEAR_HEADER.match(word.strip())
            if m and (m.group(1) is None or (m.group(1), m.group(2)) == ("31", "12")):
                out.append((x0, y0, (x0 + x1) / 2, int(m.group(3))))
        return out

    def _parse_page(self, page: pymupdf.Page, page_number: int, text: str, result: StatementParseResult) -> None:
        lines = _lines(page)
        headers = self._year_headers(page)
        labels = [ln for ln in lines
                  if normalize_name(ln.text) in INSTITUTION_LINE_TO_METRIC or normalize_name(ln.text) in CHECK_LINES]
        if len({h[3] for h in headers}) < 2 or len(labels) < 3:
            return  # not a comparative statement page
        result.statement_pages.append(page_number)
        unit, currency, multiplier = page_unit(text)
        numbers = [ln for ln in lines if parse_amount(ln.text) is not None]
        for label in labels:
            key = normalize_name(label.text)
            # Headers of the label's OWN table: the nearest header row above the label, right of it.
            above = [h for h in headers if h[1] < label.y0 and h[2] > label.x0]
            if not above:
                result.skipped_cells.append(f"p.{page_number} {label.text}: no year headers above")
                continue
            row_y = max(h[1] for h in above)
            own = sorted((h for h in above if abs(h[1] - row_y) <= 3), key=lambda h: h[2])[:2]
            if len(own) < 2 or own[0][3] == own[1][3]:
                result.skipped_cells.append(f"p.{page_number} {label.text}: no distinct year headers for its table")
                continue
            row = [n for n in numbers if abs(n.ymid - label.ymid) <= ROW_TOLERANCE and n.x0 > label.x0]
            for header in own:
                year = header[3]
                cell = [n for n in row if abs(n.xmid - header[2]) <= COLUMN_TOLERANCE
                        and min(own, key=lambda h: abs(n.xmid - h[2])) is header]
                if len(cell) != 1:
                    result.skipped_cells.append(f"p.{page_number} {label.text} {year}: {len(cell)} cell(s)")
                    continue
                value = parse_amount(cell[0].text)
                if key in CHECK_LINES:
                    result.check_values[(CHECK_LINES[key], year)] = (value, multiplier)
                    continue
                result.values.append(StatementValue(
                    INSTITUTION_LINE_TO_METRIC[key], label.text.strip(), year, cell[0].text.strip(), value,
                    page_number, unit, currency, multiplier,
                ))
