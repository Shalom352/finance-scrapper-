"""
Parser of the BCEAO fascicle "Bilans et comptes de résultat des banques et établissements
financiers de l'UMOA" (regulatory publication, one balance-sheet page and one income-statement
page per institution, three years per page, amounts in millions of FCFA).

Strict rules (DATA MISSING > DATA WRONG):
  - only published line items mapped 1:1 to an existing catalogue metric are read
    (no sum, no derived value);
  - a cell that is not a plain number ("-", empty, text) stays missing — never 0;
  - "0" printed in the document is a published value and is kept as such;
  - aggregate pages (country / sector totals) are ignored.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

import pymupdf

from scraping.universe.normalize import (
    clean_text,
    country_code_for_label,
    join_spans,
    normalize_name,
)

# Published line (normalized) → existing catalogue metric code. Deliberately excluded:
#   "TOTAL DU PASSIF" (balance-sheet total ≠ total liabilities) and immobilisations (two lines).
LINE_TO_METRIC: dict[str, str] = {
    "TOTAL DE L ACTIF": "total_actifs",
    "CREANCES SUR LA CLIENTELE": "creances_clients",
    "CREANCES INTERBANCAIRES ET ASSIMILEES": "creances_banques",
    "DETTES A L EGARD DE LA CLIENTELE": "depots_clients",
    "DETTES INTERBANCAIRES ET ASSIMILEES": "depots_banques",
    "CAPITAUX PROPRES ET RESSOURCES ASSIMILEES": "capitaux_propres",
    "PRODUIT NET BANCAIRE": "produit_net_bancaire",
    "RESULTAT D EXPLOITATION": "resultat_exploitation",
    "RESULTAT NET": "resultat_net",
    # Explicit spelling variants printed in the 2023 fascicle (exact normalized match only,
    # no fuzzy matching): 108 income statements print "PRODUITS NET BANCAIRE", one prints
    # "PRODUIT NET BANCAIRES (1 à 9)". Same line of the same statement template.
    "PRODUITS NET BANCAIRE": "produit_net_bancaire",
    "PRODUIT NET BANCAIRES 1 A 9": "produit_net_bancaire",
}

# Lines read ONLY for consistency checks (never stored as a metric): balance-sheet result of
# the year, compared with the income-statement RESULTAT NET.
CHECK_LINES: dict[str, str] = {
    "RESULTAT DE L EXERCICE": "balance_sheet_result",
}

AGGREGATE_CODES = {
    "BANQUES", "ETABLISSEMENTS FINANCIERS", "ETABLISSEMENT FINANCIER", "BANQUES ET ETABLISSEMENTS FINANCIERS",
}
UNIT_MARKER = "MILLIONS DE FRANCS CFA"
_NUMBER_RE = re.compile(r"^-?\d{1,3}(?: \d{3})*$")
_YEAR_RE = re.compile(r"^(19|20)\d{2}$")
_KIND_RE = re.compile(r"^(BILANS|COMPTES DE RESULTAT)\s+(\d{4})\s*(\d{4})?$")
_STRUCTURAL = {"ACTIF", "PASSIF", "HORS BILAN", "PRODUITS CHARGES", UNIT_MARKER}


@dataclass
class FascicleValue:
    metric_code: str
    line_label: str
    year: int
    raw: str
    value_millions: Decimal


@dataclass
class FasciclePage:
    page_number: int
    country_code: str
    code: str
    kind: str  # balance_sheet | income_statement
    label: str | None
    unit_found: bool
    values: list[FascicleValue] = field(default_factory=list)
    skipped_cells: list[str] = field(default_factory=list)
    # (check name, year) → printed value in millions (consistency checks only)
    check_values: dict[tuple[str, int], Decimal] = field(default_factory=dict)


@dataclass
class FascicleParseResult:
    page_count: int
    pages: list[FasciclePage] = field(default_factory=list)
    aggregate_pages: int = 0
    unreadable_pages: list[int] = field(default_factory=list)


@dataclass
class _Ln:
    x0: float
    x1: float
    y0: float
    y1: float
    text: str
    bold: bool

    @property
    def ymid(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def xmid(self) -> float:
        return (self.x0 + self.x1) / 2


def parse_amount(raw: str) -> Decimal | None:
    text = clean_text(raw).replace(chr(0x2212), "-")  # typographic minus sign
    if not _NUMBER_RE.match(text):
        return None
    return Decimal(text.replace(" ", ""))


def _lines(page: pymupdf.Page) -> list[_Ln]:
    out = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            spans = [s for s in line["spans"] if clean_text(s["text"])]
            if not spans:
                continue
            text = join_spans(spans)
            bold = all("bold" in s["font"].lower() or s["flags"] & 16 for s in spans)
            x0, y0, x1, y1 = line["bbox"]
            out.append(_Ln(x0, x1, y0, y1, text, bold))
    return out


class FascicleParser:
    def parse_bytes(self, content: bytes) -> FascicleParseResult:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            result = FascicleParseResult(page_count=doc.page_count)
            for pno in range(doc.page_count):
                page = self.parse_page(doc[pno], pno + 1)
                if page is None:
                    continue
                if page == "aggregate":
                    result.aggregate_pages += 1
                    continue
                result.pages.append(page)
            return result

    def parse_page(self, page: pymupdf.Page, page_number: int) -> FasciclePage | str | None:
        lines = _lines(page)
        top = sorted([ln for ln in lines if ln.bold and ln.x0 < 120 and ln.y0 < 140], key=lambda ln: ln.y0)
        if len(top) < 3:
            return None
        cc = country_code_for_label(top[0].text)
        kind_match = _KIND_RE.match(normalize_name(top[2].text))
        if cc is None or kind_match is None:
            return None
        code = clean_text(top[1].text)
        if normalize_name(code) in AGGREGATE_CODES:
            return "aggregate"
        kind = "balance_sheet" if kind_match.group(1) == "BILANS" else "income_statement"

        # Bank title: first bold line above the year header that is not one of the 3 header lines.
        years_all = [ln for ln in lines if _YEAR_RE.match(ln.text) and ln.y0 < 240]
        header_limit = min((ln.y0 for ln in years_all), default=140.0)
        used = {id(t) for t in top[:3]}
        titles = sorted(
            (
                ln for ln in lines
                if ln.bold and id(ln) not in used and ln.y0 < header_limit
                and normalize_name(ln.text) not in _STRUCTURAL and not _YEAR_RE.match(ln.text)
            ),
            key=lambda ln: ln.y0,
        )
        label = clean_text(titles[0].text) if titles else None
        unit_found = any(normalize_name(ln.text) == UNIT_MARKER for ln in lines)
        result = FasciclePage(page_number, cc, code, kind, label, unit_found)

        years = sorted((ln for ln in lines if _YEAR_RE.match(ln.text) and ln.y0 < 240), key=lambda ln: ln.x0)
        if not years or not unit_found:
            return result
        numbers = [ln for ln in lines if parse_amount(ln.text) is not None and ln.x0 > 250 and ln.y0 > years[0].y1]
        for ln in lines:
            if ln.x0 > 250:
                continue
            key = normalize_name(ln.text)
            metric = LINE_TO_METRIC.get(key)
            check = CHECK_LINES.get(key)
            if metric is None and check is None:
                continue
            row = [n for n in numbers if abs(n.ymid - ln.ymid) < 4]
            for year_line in years:
                cell = [n for n in row if abs(n.xmid - year_line.xmid) < 35]
                if len(cell) != 1:
                    result.skipped_cells.append(f"{ln.text} {year_line.text}: {len(cell)} cell(s)")
                    continue
                value = parse_amount(cell[0].text)
                if value is None:
                    result.skipped_cells.append(f"{ln.text} {year_line.text}: not a number {cell[0].text!r}")
                    continue
                if check is not None:
                    result.check_values[(check, int(year_line.text))] = value
                    continue
                result.values.append(FascicleValue(metric, clean_text(ln.text), int(year_line.text),
                                                   cell[0].text, value))
        return result
