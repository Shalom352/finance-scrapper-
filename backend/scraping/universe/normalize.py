"""
Name normalization for entity resolution (Phase 15).

Unlike ``scraping.reconciliation.normalizer`` this module NEVER strips the
``SUCCURSALE`` marker: a branch must stay distinguishable from its parent bank.
"""
import re
import unicodedata

# The 8 UMOA member states as they are written in BCEAO / CB-UMOA publications.
COUNTRY_LABELS: dict[str, str] = {
    "BENIN": "BJ",
    "BURKINA": "BF",
    "BURKINA FASO": "BF",
    "COTE D IVOIRE": "CI",
    "GUINEE BISSAU": "GW",
    "GUINEE": "GW",
    "MALI": "ML",
    "NIGER": "NE",
    "SENEGAL": "SN",
    "TOGO": "TG",
}

# Tokens naming a UMOA country (used to compare names "without country").
COUNTRY_TOKENS = frozenset(
    {"BENIN", "BURKINA", "FASO", "COTE", "D", "IVOIRE", "GUINEE", "BISSAU", "MALI", "NIGER", "SENEGAL", "TOGO",
     "CI", "BF", "BJ", "ML", "NE", "SN", "TG", "GW"}
)

# Legal-form tokens that carry no identity.
LEGAL_FORM_TOKENS = frozenset({"SA", "S", "A", "SARL", "SAS"})

_ZERO_WIDTH = dict.fromkeys((0x200B, 0x200C, 0x200D, 0xFEFF), None)  # zero-width chars, BOM


def clean_text(value: str | None) -> str:
    """Strip zero-width characters and collapse whitespace (keeps accents and case)."""
    if not value:
        return ""
    text = value.translate(_ZERO_WIDTH).replace(chr(0xA0), " ").replace(chr(0x202F), " ")
    return " ".join(text.split())


def join_spans(spans: list[dict]) -> str:
    """Join PyMuPDF spans of one line, inserting a space where the PDF leaves a visual gap."""
    parts: list[str] = []
    prev_x1: float | None = None
    for span in spans:
        text = span["text"]
        if prev_x1 is not None and parts and not parts[-1].endswith(" ") and not text.startswith(" "):
            gap = span["bbox"][0] - prev_x1
            if gap > 0.25 * span.get("size", 8):
                parts.append(" ")
        parts.append(text)
        prev_x1 = span["bbox"][2]
    return clean_text("".join(parts))


def strip_accents(value: str) -> str:
    nfkd = unicodedata.normalize("NFKD", value)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_name(value: str | None) -> str:
    """Uppercase ASCII, punctuation → space, collapsed. Keeps every word (incl. SUCCURSALE)."""
    text = strip_accents(clean_text(value)).upper()
    text = text.replace("*", " ")
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return " ".join(text.split())


def strip_parentheticals(value: str) -> str:
    """Remove every ``( ... )`` group (acronyms, footnotes)."""
    previous = None
    text = value
    while previous != text:
        previous = text
        text = re.sub(r"\([^()]*\)", " ", text)
    return " ".join(text.replace("(", " ").replace(")", " ").split())


def core_tokens(value: str | None) -> tuple[str, ...]:
    """Normalized tokens without parentheticals, country words and legal forms."""
    tokens = normalize_name(strip_parentheticals(clean_text(value))).split()
    return tuple(t for t in tokens if t not in COUNTRY_TOKENS and t not in LEGAL_FORM_TOKENS)


def core_key(value: str | None) -> str:
    return " ".join(core_tokens(value))


def name_key(value: str | None) -> str:
    """Full normalized name without parentheticals (country words kept)."""
    return normalize_name(strip_parentheticals(clean_text(value)))


def country_code_for_label(label: str | None) -> str | None:
    """Map a country heading ("CÔTE D'IVOIRE", "GUINEE BISSAU", "BURKINA ") to its ISO code."""
    key = normalize_name(label)
    return COUNTRY_LABELS.get(key)


def country_codes_in(value: str | None) -> set[str]:
    """ISO codes of the UMOA countries explicitly named in a text."""
    text = f" {normalize_name(value)} "
    found = set()
    for label, code in COUNTRY_LABELS.items():
        if label == "GUINEE":
            continue
        if f" {label} " in text:
            found.add(code)
    return found
