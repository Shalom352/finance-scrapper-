"""
Text-layer quality of a PDF (Phase 17).

"Has text" is not enough: some official PDFs embed fonts whose character mapping is broken.
Observed on BOA annual reports 2023: "CRÉANCES INTERBANCAIRES" rendered "C5(A1C(6 ,17(5BA1CA,5(6" and
amounts with dropped digits ("9 2 950 45"). A number read on such a page can be WRONG while still
looking like a number, so such pages are never extracted.

Page status:
  empty      no exploitable text (scanned image)          → not machine readable
  corrupted  garbled words above the threshold              → not reliable
  ok         readable
Document status: machine_readable (all text pages ok) | partially_corrupted (some ok, some corrupted)
| not_machine_readable (no ok page) | unknown.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pymupdf

MIN_PAGE_CHARS = 40
_ODD_GLYPHS = re.compile("[" + chr(0x01CB) + chr(0x01D1) + chr(0x0141) + chr(0x0142) + "]")
_PHONE = re.compile(r"(?:\+\d|T[ée]l|Fax|BP\b|B\.P)", re.IGNORECASE)
CORRUPTED_LINE_RATIO = 0.08
MIN_GARBLED_LINES = 3


@dataclass
class PageQuality:
    page_number: int
    status: str  # ok | corrupted | empty
    chars: int
    garbled_lines: int
    lines: int


@dataclass
class DocumentTextLayer:
    status: str  # machine_readable | partially_corrupted | not_machine_readable | unknown
    pages: list[PageQuality] = field(default_factory=list)

    def page_ok(self, page_number: int) -> bool:
        return any(p.page_number == page_number and p.status == "ok" for p in self.pages)

    @property
    def ok_pages(self) -> int:
        return sum(1 for p in self.pages if p.status == "ok")


def _garbled_line(line: str) -> bool:
    """A line showing glyph-mapping artefacts (odd glyphs, labels mixing letters / digits /
    brackets, or amounts whose thousand groups lost digits)."""
    text = line.strip()
    if not text:
        return False
    if _ODD_GLYPHS.search(text):
        return True
    upper_words = [w for w in text.split() if len(w) >= 4 and w.upper() == w and any(c.isalpha() for c in w)]
    if any(re.search(r"[A-Z][(),;]|[(),;][A-Z0-9]", w) and re.search(r"\d", w) for w in upper_words):
        return True
    if _PHONE.search(text):
        return False  # phone / fax / postal box numbers are not amounts
    # amounts whose thousand groups lost digits ("9 2 950 45"); legitimate amounts group by 3.
    # Letter-spaced titles ("2 0 2 1": only single digits) are not amounts.
    for m in re.finditer(r"\d[\d ]{4,}\d", text):
        groups = m.group(0).split()
        if len(groups) >= 3 and any(len(g) < 3 for g in groups[1:]) and not all(len(g) == 1 for g in groups):
            return True
    return False


def assess_page(text: str, page_number: int) -> PageQuality:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    chars = len(text.strip())
    if chars < MIN_PAGE_CHARS:
        return PageQuality(page_number, "empty", chars, 0, len(lines))
    garbled = sum(1 for ln in lines if _garbled_line(ln))
    status = "corrupted" if garbled >= MIN_GARBLED_LINES and garbled / len(lines) >= CORRUPTED_LINE_RATIO else "ok"
    return PageQuality(page_number, status, chars, garbled, len(lines))


def assess_texts(page_texts: list[str]) -> DocumentTextLayer:
    pages = [assess_page(t, i + 1) for i, t in enumerate(page_texts)]
    if not pages:
        return DocumentTextLayer("unknown", pages)
    ok = sum(1 for p in pages if p.status == "ok")
    corrupted = sum(1 for p in pages if p.status == "corrupted")
    if ok == 0:
        status = "not_machine_readable"
    elif corrupted:
        status = "partially_corrupted"
    else:
        status = "machine_readable"
    return DocumentTextLayer(status, pages)


def assess_pdf_bytes(content: bytes) -> DocumentTextLayer:
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            return assess_texts([pdf[i].get_text() for i in range(pdf.page_count)])
    except Exception:
        return DocumentTextLayer("unknown", [])
