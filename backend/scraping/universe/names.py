"""
Parsing of one official list designation (Phase 15).

Examples (BCEAO / CB-UMOA lists):
  "BANK OF AFRICA - BÉNIN (BOA – BÉNIN)"                 → acronym "BOA – BÉNIN"
  "BANGE BANK BÉNIN ex CCEI BANK BÉNIN"                  → former name "CCEI BANK BÉNIN"
  "INTERNATIONAL BUSINESS BANK TOGO (IB BANK TOGO, ex BTCI)" → acronym + former acronym
  "CBAO, GROUPE ATTIJARIWAFA BANK, SUCCURSALE DU BÉNIN"  → branch, parent "CBAO, GROUPE ATTIJARIWAFA BANK"

Nothing is inferred beyond what the designation states.
"""
import re
from dataclasses import dataclass, field

from scraping.universe.normalize import clean_text

_EX_IN_PARENS = re.compile(r"\(([^()]*?),\s*ex\s+([^()]*)\)", re.IGNORECASE)
_EX_SPLIT = re.compile(r"\s*,?\s+\bex\b\s+", re.IGNORECASE)
_TRAILING_ACRONYM = re.compile(r"^(.*\S)\s*\(([^()]+)\)\s*$")
_BRANCH = re.compile(
    r"^(?P<parent>.*?)[\s,\-–]*\bSUCCURSALE\s+(?:DU|DE\s+LA|DE\s+L['’]|DES|DE|D['’]|EN|AU)\s*(?P<host>.+)$",
    re.IGNORECASE,
)
_BRANCH_WORD = re.compile(r"\bSUCCURSALE\b", re.IGNORECASE)


@dataclass
class ParsedDesignation:
    raw: str
    official_name: str  # current designation, without the acronym group and without "ex ..."
    acronym: str | None = None
    former_names: list[str] = field(default_factory=list)
    is_branch_name: bool = False
    parent_name: str | None = None  # as written before ", SUCCURSALE DU ..."
    host_country_text: str | None = None
    flags: list[str] = field(default_factory=list)


def _split_acronym(part: str) -> tuple[str, str | None]:
    m = _TRAILING_ACRONYM.match(part)
    if not m:
        return part.strip(" ,-–"), None
    return m.group(1).strip(" ,-–"), clean_text(m.group(2)) or None


def parse_designation(raw: str) -> ParsedDesignation:
    text = clean_text(raw)
    flags: list[str] = []
    if "*" in text:
        flags.append("footnote_marker")
        text = clean_text(text.replace("*", " "))

    former: list[str] = []

    # "(IB BANK TOGO, ex BTCI)" → acronym "IB BANK TOGO", former acronym "BTCI"
    def _ex_parens(m: re.Match[str]) -> str:
        former.append(clean_text(m.group(2)))
        return f"({clean_text(m.group(1))})"

    text = _EX_IN_PARENS.sub(_ex_parens, text)

    parts = _EX_SPLIT.split(text)
    current = parts[0]
    for old in parts[1:]:
        old_name, old_acronym = _split_acronym(old)
        if old_name:
            former.append(old_name)
        if old_acronym:
            former.append(old_acronym)

    parsed = ParsedDesignation(raw=clean_text(raw), official_name=current, flags=flags, former_names=former)

    branch = _BRANCH.match(current)
    if branch:
        parsed.is_branch_name = True
        parsed.parent_name = clean_text(branch.group("parent")).strip(" ,-–") or None
        parsed.host_country_text = clean_text(branch.group("host")) or None
        # The official designation of a branch is the full text; no acronym is attributed
        # to the branch (a parent's acronym must not become the branch's identifier).
        parsed.official_name = clean_text(current).strip(" ,-–")
        return parsed
    if _BRANCH_WORD.search(current):
        parsed.is_branch_name = True
        parsed.flags.append("branch_word_without_host")

    name, acronym = _split_acronym(current)
    parsed.official_name = name
    parsed.acronym = acronym
    return parsed
