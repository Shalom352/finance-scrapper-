"""
Scope evidence assessment (Phase 16) — individual vs consolidated, from DOCUMENTARY evidence only.

Evidence is a *statement-scope phrase*: a statement head word immediately qualified by a scope,
e.g. "ÉTATS FINANCIERS CONSOLIDÉS", "COMPTES SOCIAUX", "BILAN CONSOLIDÉ", "BASE SOCIALE",
"CONSOLIDATED FINANCIAL STATEMENTS", "SEPARATE FINANCIAL STATEMENTS". A scope word inside an
accounting line label ("RÉSERVES CONSOLIDÉES ET REPORT À NOUVEAU") is NOT evidence.

Classes (see app.constants.quality):
  A  the observation page's header zone states exactly one scope, not contradicted by the title
  B  the document title (first lines of page 1) states exactly one scope, the page header is silent,
     and no page of the document mentions the other scope
  C  documented convention only, or a mention on another page only
  D  nothing, contradiction, or no exploitable text (document_not_machine_readable)

The file name is NEVER used as evidence.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

import pymupdf

INDIVIDUAL, CONSOLIDATED = "individual", "consolidated"

_HEADS = r"(?:COMPTES|ETATS FINANCIERS|BILANS?|COMPTES? DE RESULTATS?)(?: ANNUELS)?(?: RESUMES?)?"
_PATTERNS: dict[str, re.Pattern[str]] = {
    INDIVIDUAL: re.compile(
        rf"\b{_HEADS} (?:INDIVIDUELS?|SOCIAUX)\b|\bBASE (?:SOCIALE|INDIVIDUELLE)\b"
        r"|\b(?:SEPARATE|STANDALONE) FINANCIAL STATEMENTS\b"
    ),
    CONSOLIDATED: re.compile(
        rf"\b{_HEADS} CONSOLIDE(?:E|S|ES)?\b|\bBASE CONSOLIDEE\b|\bCONSOLIDATED FINANCIAL STATEMENTS\b"
    ),
}

HEADER_LINES = 8  # header zone of a page = its first non-empty text lines
TITLE_LINES = 15  # document title zone = first non-empty lines of page 1
MIN_TEXT_CHARS = 40  # below this, a page has no exploitable text layer


def normalize(text: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    ascii_text = re.sub(r"[^A-Za-z0-9]+", " ", ascii_text)
    return " ".join(ascii_text.upper().split())


def scopes_in(text: str) -> set[str]:
    norm = normalize(text)
    return {scope for scope, pattern in _PATTERNS.items() if pattern.search(norm)}


def _snippet(text: str, scope: str) -> str:
    norm = normalize(text)
    m = _PATTERNS[scope].search(norm)
    return norm[max(0, m.start() - 40): m.end() + 30] if m else ""


@dataclass(frozen=True)
class ScopeAssessment:
    evidence_class: str  # A | B | C | D
    reason_code: str
    scope: str | None = None  # individual | consolidated, only for A/B
    evidence: str | None = None

    @property
    def promotable(self) -> bool:
        return self.evidence_class in ("A", "B") and self.scope is not None


class DocumentScopeContext:
    """Scope evidence of one document, assessed per observation page."""

    def __init__(self, page_texts: list[str], convention_reason: str | None = None,
                 convention_evidence: str | None = None) -> None:
        self.pages = page_texts
        self.convention_reason = convention_reason
        self.convention_evidence = convention_evidence
        lines_p1 = [ln for ln in (page_texts[0].splitlines() if page_texts else []) if ln.strip()]
        self.title = " ".join(lines_p1[:TITLE_LINES])
        self.title_scopes = scopes_in(self.title)
        self.page_scopes = [scopes_in(t) for t in page_texts]
        self.document_scopes: set[str] = set().union(*self.page_scopes) if self.page_scopes else set()
        self.readable = any(len(t.strip()) >= MIN_TEXT_CHARS for t in page_texts)

    @classmethod
    def from_pdf_bytes(cls, content: bytes, **kwargs) -> DocumentScopeContext:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            return cls([pdf[i].get_text() for i in range(pdf.page_count)], **kwargs)

    @classmethod
    def from_pdf_path(cls, path: str, **kwargs) -> DocumentScopeContext:
        with pymupdf.open(path) as pdf:
            return cls([pdf[i].get_text() for i in range(pdf.page_count)], **kwargs)

    def _header(self, page_number: int) -> str:
        lines = [ln for ln in self.pages[page_number - 1].splitlines() if ln.strip()]
        return " ".join(lines[:HEADER_LINES])

    def assess(self, page_number: int | None) -> ScopeAssessment:
        if not self.readable:
            return ScopeAssessment("D", "document_not_machine_readable",
                                   evidence="no exploitable text layer in the document")
        page_ok = page_number is not None and 1 <= page_number <= len(self.pages)
        if page_ok and len(self.pages[page_number - 1].strip()) < MIN_TEXT_CHARS:
            return ScopeAssessment("D", "document_not_machine_readable",
                                   evidence=f"no exploitable text layer on page {page_number}")

        header_scopes = scopes_in(self._header(page_number)) if page_ok else set()
        # ---- A: explicit on the observation page, not contradicted by the title
        if len(header_scopes) == 1:
            (scope,) = header_scopes
            if self.title_scopes and self.title_scopes != header_scopes:
                return ScopeAssessment("D", "scope_conflicting_mentions",
                                       evidence=f"page {page_number} header says {scope}, "
                                                f"title says {sorted(self.title_scopes)}")
            return ScopeAssessment("A", "scope_explicit_page", scope,
                                   f"p.{page_number}: {_snippet(self._header(page_number), scope)}")
        if len(header_scopes) > 1:
            return ScopeAssessment("D", "scope_conflicting_mentions",
                                   evidence=f"page {page_number} header mentions both scopes")
        # ---- B: explicit title, no contrary mention anywhere in the document
        if len(self.title_scopes) == 1:
            (scope,) = self.title_scopes
            if self.document_scopes - self.title_scopes:
                return ScopeAssessment("D", "scope_conflicting_mentions",
                                       evidence=f"title says {scope}, the document also mentions "
                                                f"{sorted(self.document_scopes - self.title_scopes)}")
            return ScopeAssessment("B", "scope_explicit_document_title", scope,
                                   f"title: {_snippet(self.title, scope)}")
        if len(self.title_scopes) > 1 or len(self.document_scopes) > 1:
            return ScopeAssessment("D", "scope_conflicting_mentions",
                                   evidence="the document mentions both scopes without page-level separation")
        # ---- C: inference only
        if self.convention_reason:
            return ScopeAssessment("C", self.convention_reason, evidence=self.convention_evidence)
        if self.document_scopes:
            pages = [i + 1 for i, s in enumerate(self.page_scopes) if s]
            return ScopeAssessment("C", "scope_mentioned_elsewhere_only",
                                   evidence=f"scope {sorted(self.document_scopes)} stated on page(s) {pages[:5]} "
                                            f"only, not on page {page_number}")
        # ---- D: nothing
        return ScopeAssessment("D", "scope_not_stated", evidence="no statement-scope phrase in the document")
