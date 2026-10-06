"""
Parser of the official lists of licensed credit institutions (Phase 15).

Supported layouts (both observed on the official sites, 2026):
  - BCEAO  "Liste des établissements de crédit agréés dans l'UMOA au 31 décembre 2025":
    a UMOA summary table (banks / financial establishments / total per country), then one
    section per country with "LISTE DES BANQUES (n)", "- dont filiales (n)",
    "- dont succursales (n)", financial establishments, NOUVEL AGRÉMENT, RADIATION,
    MODIFICATIONS INTERVENUES and AGRÉMENT UNIQUE;
  - CB-UMOA "Listes des banques et des établissements financiers à caractère bancaire de
    l'UMOA (mise à jour au ...)": numbered rows, "BANQUES (n)", "SUCCURSALES",
    "ETABLISSEMENTS FINANCIERS DE CREDIT (n)", superscript footnote letters.

The parser works on text lines WITH COORDINATES (PyMuPDF): a registration number
(e.g. "B 0061 F") anchors one row; name fragments are attached to the nearest anchor of the
same section and page (multi-line designations). Counts announced by the document are kept
and checked against the rows actually parsed. Nothing is inferred: a count that the document
does not state stays None.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any

import pymupdf

from scraping.universe.names import ParsedDesignation, parse_designation
from scraping.universe.normalize import (
    clean_text,
    country_code_for_label,
    join_spans,
    normalize_name,
)

# "B 0061 F"; tolerates a stray space inside the digits as printed in the 2025 list ("H 0 210 K").
REGISTRATION_RE = re.compile(r"^\*?\s*([A-Z])\s?(\d(?:\s?\d){3})\s?([A-Z])\s*\*?$")
TRAILING_REGISTRATION_RE = re.compile(r"^(?P<name>.*\S)\s+(?P<reg>[A-Z]\s?\d(?:\s?\d){3}\s?[A-Z])\s*\*?$")


def format_registration(match: re.Match[str]) -> str:
    return f"{match.group(1)} {match.group(2).replace(' ', '')} {match.group(3)}"
INDEX_RE = re.compile(r"^\d{1,3}$")
_NULL_ROW = {"NEANT", "NEANT."}

FRENCH_MONTHS = {
    "JANVIER": 1, "FEVRIER": 2, "MARS": 3, "AVRIL": 4, "MAI": 5, "JUIN": 6, "JUILLET": 7,
    "AOUT": 8, "SEPTEMBRE": 9, "OCTOBRE": 10, "NOVEMBRE": 11, "DECEMBRE": 12,
}
_DATE_RE = re.compile(
    r"(?:MISE A JOUR AU|SITUATION A FIN|AU|A FIN)\s+(?:(\d{1,2})(?:ER)?\s+)?"
    r"(JANVIER|FEVRIER|MARS|AVRIL|MAI|JUIN|JUILLET|AOUT|SEPTEMBRE|OCTOBRE|NOVEMBRE|DECEMBRE)\s+(\d{4})"
)
_MONTH_END = {1: 31, 2: 28, 3: 31, 4: 30, 5: 31, 6: 30, 7: 31, 8: 31, 9: 30, 10: 31, 11: 30, 12: 31}

# ---------------------------------------------------------------- header patterns (normalized)
_H_BANKS = re.compile(r"^(?:LISTES? DES )?BANQUES(?: (\d+))?$")
_H_SUBSIDIARIES = re.compile(r"^(?:DONT )?FILIALES?(?: (\d+))?$")
_H_BRANCHES = re.compile(r"^(?:DONT )?SUCCURSALES?(?: (\d+))?$")
_H_EF = re.compile(
    r"^(?:LISTES? DES )?ETABLISSEMENTS FINANCIERS(?: A CARACTERE BANCAIRE| DE CREDIT)?(?: (\d+))?$"
)
_H_NEW = re.compile(r"^NOUVE(?:L|AUX)(?:LE)?S? AGREMENTS?(?: (\d+))?$")
_H_RADIATION = re.compile(r"^RADIATIONS?(?: (\d+))?$")
_H_MODIFICATIONS = re.compile(r"^MODIFICATIONS INTERVENUES")
_H_UNIQUE = re.compile(r"^(?:AGREMENT UNIQUE|ETABLISSEMENTS INSTALLES DANS LES AUTRES PAYS)")
_H_OTHER = re.compile(
    r"^(?:ETABLISSEMENTS DE PAIEMENT|ETABLISSEMENTS DE MONNAIE ELECTRONIQUE|COMPAGNIES FINANCIERES|"
    r"SYSTEMES FINANCIERS DECENTRALISES)"
)
_H_SUMMARY = re.compile(r"^ETABLISSEMENTS DE CREDIT AGREES DANS L UMOA A FIN")
_H_IGNORED = re.compile(
    r"^(?:LISTES? DES (?:BANQUES ET DES )?ETABLISSEMENTS|DENOMINATIONS?|NUMEROS|D INSCRIPTION|"
    r"SITUATION A FIN|MISE A JOUR|SOMMAIRE|PAGES?$|PAYS$|TOTAL$|ETABLISSEMENTS$|FINANCIERS$|BANQUES$)"
)


@dataclass
class ParsedMember:
    country_code: str
    category: str  # bank | financial_establishment
    form: str  # subsidiary | branch | unspecified
    raw_name: str
    designation: ParsedDesignation
    registration_number: str | None
    page_number: int
    row_index: int | None = None
    notes: list[str] = field(default_factory=list)

    @property
    def official_name(self) -> str:
        return self.designation.official_name


@dataclass
class ParsedCountry:
    country_code: str
    first_page: int
    bank_header_count: int | None = None
    bank_subsidiary_count: int | None = None
    bank_branch_count: int | None = None
    ef_header_count: int | None = None
    members: list[ParsedMember] = field(default_factory=list)
    history: list[dict[str, Any]] = field(default_factory=list)

    def banks(self) -> list[ParsedMember]:
        return [m for m in self.members if m.category == "bank"]


@dataclass
class ParsedReferenceList:
    title: str
    layout: str  # bceao_annual_list | cbumoa_list | unknown
    reference_date: date | None
    reference_date_text: str | None
    page_count: int
    summary: dict[str, dict[str, int]] = field(default_factory=dict)  # cc → banks/ef/total
    summary_total: dict[str, int] | None = None
    summary_page: int | None = None
    countries: dict[str, ParsedCountry] = field(default_factory=dict)
    anomalies: list[str] = field(default_factory=list)

    # ------------------------------------------------------------------ expected counts
    def expected_banks(self, country_code: str) -> tuple[int | None, str | None]:
        """Official expected bank count for a country and its evidence (None when not stated)."""
        if country_code in self.summary:
            return self.summary[country_code]["banks"], (
                f"summary table p.{self.summary_page}: banks={self.summary[country_code]['banks']}"
            )
        country = self.countries.get(country_code)
        if country and country.bank_header_count is not None:
            return country.bank_header_count, (
                f"country header p.{country.first_page}: BANQUES ({country.bank_header_count})"
            )
        return None, None

    def expected_banks_total(self, country_codes: tuple[str, ...]) -> tuple[int | None, str | None]:
        if self.summary_total is not None:
            return self.summary_total["banks"], f"summary table p.{self.summary_page}: TOTAL UMOA banks"
        values = [self.expected_banks(cc)[0] for cc in country_codes]
        if all(v is not None for v in values):
            return sum(values), "sum of the 8 official country headers (no UMOA total printed)"  # type: ignore[arg-type]
        return None, None

    # ------------------------------------------------------------------ self-check
    def self_check(self, country_codes: tuple[str, ...]) -> list[str]:
        """Consistency issues between announced counts and parsed rows (empty = consistent)."""
        issues = list(self.anomalies)
        if self.reference_date is None:
            issues.append("reference date not found in document")
        for cc in country_codes:
            country = self.countries.get(cc)
            if country is None:
                issues.append(f"{cc}: country section not found")
                continue
            banks = country.banks()
            header = country.bank_header_count
            if header is None:
                issues.append(f"{cc}: bank header count not found")
            elif len(banks) != header:
                issues.append(f"{cc}: parsed {len(banks)} bank rows but header announces {header}")
            if cc in self.summary and header is not None and self.summary[cc]["banks"] != header:
                issues.append(
                    f"{cc}: summary table announces {self.summary[cc]['banks']} banks, country header {header}"
                )
            if country.bank_subsidiary_count is not None:
                n = sum(1 for m in banks if m.form == "subsidiary")
                if n != country.bank_subsidiary_count:
                    issues.append(f"{cc}: parsed {n} subsidiaries, header announces {country.bank_subsidiary_count}")
            if country.bank_branch_count is not None:
                n = sum(1 for m in banks if m.form == "branch")
                if n != country.bank_branch_count:
                    issues.append(f"{cc}: parsed {n} branches, header announces {country.bank_branch_count}")
            if country.ef_header_count is not None:
                n = sum(1 for m in country.members if m.category == "financial_establishment")
                if n != country.ef_header_count:
                    issues.append(f"{cc}: parsed {n} financial establishments, header announces "
                                  f"{country.ef_header_count}")
            for m in banks:
                if m.registration_number is None:
                    issues.append(f"{cc}: bank row without registration number: {m.raw_name!r}")
            indexes = [m.row_index for m in banks if m.row_index is not None]
            if indexes and sorted(indexes) != list(range(1, len(indexes) + 1)):
                issues.append(f"{cc}: bank row numbering is not continuous: {sorted(indexes)}")
        if self.summary_total is not None and self.summary:
            total = sum(v["banks"] for v in self.summary.values())
            if total != self.summary_total["banks"]:
                issues.append(f"summary: country bank counts sum to {total}, TOTAL UMOA says "
                              f"{self.summary_total['banks']}")
        regs = [m.registration_number for c in self.countries.values() for m in c.members if m.registration_number]
        dupes = sorted({r for r in regs if regs.count(r) > 1})
        if dupes:
            issues.append(f"duplicate registration numbers: {dupes}")
        return issues


# ====================================================================== low-level lines
@dataclass
class _Line:
    page: int
    x0: float
    y0: float
    y1: float
    text: str
    bold: bool
    kind: str  # reg | index | text

    @property
    def ymid(self) -> float:
        return (self.y0 + self.y1) / 2


def _is_bold(span: dict[str, Any]) -> bool:
    return "bold" in span.get("font", "").lower() or bool(span.get("flags", 0) & 16)


def _extract_lines(doc: pymupdf.Document) -> list[_Line]:
    lines: list[_Line] = []
    for pno in range(doc.page_count):
        page = doc[pno]
        raw: list[_Line] = []
        for block in page.get_text("dict")["blocks"]:
            for line in block.get("lines", []):
                spans = [s for s in line["spans"] if clean_text(s["text"])]
                if not spans:
                    continue
                max_size = max(s["size"] for s in spans)
                # Superscript footnote markers (e.g. "NSIA BANQUE BENINᵃ") are dropped.
                kept = [s for s in spans if s["size"] >= 0.75 * max_size]
                text = join_spans(kept)
                if not text:
                    continue
                bold = all(_is_bold(s) for s in kept)
                bbox = line["bbox"]
                trailing = TRAILING_REGISTRATION_RE.match(text) if not REGISTRATION_RE.match(text) else None
                if trailing and not bold:
                    # Name and registration number extracted as one line: split them.
                    raw.append(_Line(pno + 1, bbox[0], bbox[1], bbox[3], trailing.group("name"), bold, "text"))
                    raw.append(_Line(pno + 1, bbox[2] - 1, bbox[1], bbox[3], trailing.group("reg"), bold, "reg"))
                    continue
                if REGISTRATION_RE.match(text):
                    kind = "reg"
                elif INDEX_RE.match(text):
                    kind = "index"
                else:
                    kind = "text"
                raw.append(_Line(pno + 1, bbox[0], bbox[1], bbox[3], text, bold, kind))
        # Merge justified fragments of the same visual text line ("CAISSE" "REGIONALE" ...).
        raw.sort(key=lambda ln: (round(ln.y0), ln.x0))
        merged: list[_Line] = []
        for ln in raw:
            prev = merged[-1] if merged else None
            if (
                prev is not None
                and ln.kind == prev.kind == "text"
                and abs(ln.y0 - prev.y0) < 1.5
                and ln.bold == prev.bold
            ):
                prev.text = clean_text(f"{prev.text} {ln.text}")
                continue
            merged.append(ln)
        lines.extend(sorted(merged, key=lambda ln: (ln.y0, ln.x0)))
    return lines


def _count(match: re.Match[str]) -> int | None:
    value = match.group(1) if match.lastindex else None
    return int(value) if value is not None else None


def parse_reference_date(text: str) -> tuple[date | None, str | None]:
    norm = normalize_name(text)
    m = _DATE_RE.search(norm)
    if not m:
        return None, None
    month = FRENCH_MONTHS[m.group(2)]
    year = int(m.group(3))
    day = int(m.group(1)) if m.group(1) else _MONTH_END[month]  # "à fin décembre 2025" → 31/12
    try:
        return date(year, month, day), m.group(0)
    except ValueError:
        return None, m.group(0)


# ====================================================================== parser
class ReferenceListParser:
    """Parses an official list PDF (bytes) into a :class:`ParsedReferenceList`."""

    def parse_bytes(self, content: bytes) -> ParsedReferenceList:
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            return self.parse_document(doc)

    def parse_document(self, doc: pymupdf.Document) -> ParsedReferenceList:
        lines = _extract_lines(doc)
        full_text = " ".join(ln.text for ln in lines[:200])
        ref_date, ref_text = parse_reference_date(full_text)
        title = next((ln.text for ln in lines if ln.bold or "LISTE" in ln.text.upper()), "")
        layout = "unknown"
        norm_all = normalize_name(full_text)
        if "ETABLISSEMENTS DE CREDIT AGREES DANS L UMOA" in norm_all:
            layout = "bceao_annual_list"
        elif "MISE A JOUR AU" in norm_all:
            layout = "cbumoa_list"
        result = ParsedReferenceList(
            title=title, layout=layout, reference_date=ref_date, reference_date_text=ref_text,
            page_count=doc.page_count,
        )
        summary_pages = self._parse_summary(lines, result)
        # Table of contents pages repeat country names: they are not list sections.
        toc_pages = {ln.page for ln in lines if normalize_name(ln.text) == "SOMMAIRE"}
        self._parse_sections([ln for ln in lines if ln.page not in summary_pages | toc_pages], result)
        return result

    # ------------------------------------------------------------------ summary table
    def _parse_summary(self, lines: list[_Line], result: ParsedReferenceList) -> set[int]:
        pages = {ln.page for ln in lines if ln.bold and _H_SUMMARY.match(normalize_name(ln.text))}
        for page in sorted(pages):
            rows: dict[int, list[_Line]] = {}
            for ln in lines:
                if ln.page == page:
                    rows.setdefault(round(ln.y0), []).append(ln)
            for key in sorted(rows):
                row = sorted(rows[key], key=lambda ln: ln.x0)
                labels = [ln.text for ln in row if ln.kind == "text"]
                numbers = [int(ln.text) for ln in row if ln.kind == "index"]
                if len(labels) != 1 or len(numbers) != 3:
                    continue
                label = normalize_name(labels[0])
                values = {"banks": numbers[0], "ef": numbers[1], "total": numbers[2]}
                if label == "TOTAL UMOA":
                    result.summary_total = values
                    continue
                cc = country_code_for_label(label)
                if cc:
                    result.summary[cc] = values
            result.summary_page = page
        return pages

    # ------------------------------------------------------------------ country sections
    def _parse_sections(self, lines: list[_Line], result: ParsedReferenceList) -> None:
        country: ParsedCountry | None = None
        section: str | None = None  # bank | financial_establishment | new | radiation | modif | unique | other
        form = "unspecified"
        block: list[_Line] = []

        def flush() -> None:
            nonlocal block
            if country is not None and block:
                if section in ("bank", "financial_establishment"):
                    self._assign_members(block, country, section, form, result)
                elif section in ("new", "radiation"):
                    self._assign_history(block, country, section, result)
                elif section == "modif":
                    self._parse_modifications(block, country)
            block = []

        for ln in lines:
            norm = normalize_name(ln.text)
            if ln.kind == "text" and ln.bold:
                cc = country_code_for_label(norm)
                if cc:
                    flush()
                    country = result.countries.setdefault(cc, ParsedCountry(country_code=cc, first_page=ln.page))
                    section, form = None, "unspecified"
                    continue
                header = self._classify_header(norm)
                if header is not None:
                    kind, count = header
                    flush()
                    if kind in ("bank", "financial_establishment"):
                        section, form = kind, "unspecified"
                        if country is not None:
                            if kind == "bank":
                                country.bank_header_count = count
                            else:
                                country.ef_header_count = count
                    elif kind in ("subsidiary", "branch"):
                        form = kind
                        if country is not None and section == "bank" and count is not None:
                            if kind == "subsidiary":
                                country.bank_subsidiary_count = count
                            else:
                                country.bank_branch_count = count
                    elif kind == "ignored":
                        pass
                    else:
                        section, form = kind, "unspecified"
                    continue
                if section in ("bank", "financial_establishment"):
                    result.anomalies.append(f"p.{ln.page}: unexpected bold line in member section: {ln.text!r}")
                continue
            if country is None or section is None:
                continue
            block.append(ln)
        flush()

    @staticmethod
    def _classify_header(norm: str) -> tuple[str, int | None] | None:
        norm = norm.lstrip("- ").strip()
        for pattern, kind in (
            (_H_BANKS, "bank"),
            (_H_EF, "financial_establishment"),
            (_H_SUBSIDIARIES, "subsidiary"),
            (_H_BRANCHES, "branch"),
            (_H_NEW, "new"),
            (_H_RADIATION, "radiation"),
        ):
            m = pattern.match(norm)
            if m:
                return kind, _count(m)
        if _H_MODIFICATIONS.match(norm):
            return "modif", None
        if _H_UNIQUE.match(norm):
            return "unique", None
        if _H_OTHER.match(norm):
            return "other", None
        if _H_IGNORED.match(norm):
            return "ignored", None
        return None

    @staticmethod
    def _group_rows(block: list[_Line]) -> tuple[list[tuple[_Line, list[_Line], _Line | None]], list[_Line]]:
        """Attach each name fragment to the nearest registration anchor of the same page."""
        anchors = [ln for ln in block if ln.kind == "reg"]
        indexes = [ln for ln in block if ln.kind == "index"]
        fragments = [
            ln for ln in block if ln.kind == "text" and normalize_name(ln.text) not in _NULL_ROW
        ]
        groups: dict[int, list[_Line]] = {id(a): [] for a in anchors}
        orphans: list[_Line] = []
        for frag in fragments:
            same_page = [a for a in anchors if a.page == frag.page]
            if not same_page:
                orphans.append(frag)
                continue
            nearest = min(same_page, key=lambda a: (abs(a.ymid - frag.ymid), a.y0))
            if abs(nearest.ymid - frag.ymid) > 14:
                orphans.append(frag)
                continue
            groups[id(nearest)].append(frag)
        rows = []
        for a in anchors:
            idx = [i for i in indexes if i.page == a.page and abs(i.ymid - a.ymid) < 4]
            rows.append((a, sorted(groups[id(a)], key=lambda f: f.y0), idx[0] if idx else None))
        return rows, orphans

    def _assign_members(
        self, block: list[_Line], country: ParsedCountry, category: str, form: str, result: ParsedReferenceList
    ) -> None:
        rows, orphans = self._group_rows(block)
        for frag in orphans:
            result.anomalies.append(f"{country.country_code} p.{frag.page}: name fragment without registration "
                                    f"number: {frag.text!r}")
        for anchor, frags, index in rows:
            if not frags:
                result.anomalies.append(f"{country.country_code} p.{anchor.page}: registration number without name: "
                                        f"{anchor.text!r}")
                continue
            raw_name = clean_text(" ".join(f.text for f in frags))
            reg = REGISTRATION_RE.match(anchor.text)
            registration = format_registration(reg) if reg else None
            designation = parse_designation(raw_name)
            member_form = form
            notes: list[str] = []
            if form == "unspecified" and designation.is_branch_name:
                member_form = "branch"
                notes.append("form derived from the designation (SUCCURSALE)")
            if form == "subsidiary" and designation.is_branch_name:
                notes.append("designation says SUCCURSALE but listed under subsidiaries")
            country.members.append(ParsedMember(
                country_code=country.country_code, category=category, form=member_form, raw_name=raw_name,
                designation=designation, registration_number=registration, page_number=anchor.page,
                row_index=int(index.text) if index is not None else None, notes=notes,
            ))

    def _assign_history(
        self, block: list[_Line], country: ParsedCountry, section: str, result: ParsedReferenceList
    ) -> None:
        rows, _ = self._group_rows(block)
        for anchor, frags, _index in rows:
            reg = REGISTRATION_RE.match(anchor.text)
            name = clean_text(" ".join(f.text for f in frags).replace("*", " "))
            country.history.append({
                "type": "new_licence" if section == "new" else "radiation",
                "name": name,
                "registration_number": format_registration(reg) if reg else None,
                "page": anchor.page,
            })

    @staticmethod
    def _parse_modifications(block: list[_Line], country: ParsedCountry) -> None:
        texts = [ln.text for ln in block if ln.kind == "text" and normalize_name(ln.text) not in _NULL_ROW]
        if not texts:
            return
        paragraphs: list[str] = []
        for text in texts:
            if text.startswith("*") or not paragraphs:
                paragraphs.append(text.lstrip("* "))
            else:
                paragraphs[-1] = f"{paragraphs[-1]} {text}"
        for para in paragraphs:
            m = re.search(r"D[ÉE]NOMINATION SOCIALE DE (?:LA |L['’])?(.+?)\s+EN\s+(.+)$", para, re.IGNORECASE)
            country.history.append({
                "type": "rename" if m else "modification",
                "old_name": clean_text(m.group(1)) if m else None,
                "new_name": clean_text(m.group(2)) if m else None,
                "text": clean_text(para),
                "page": block[0].page,
            })
