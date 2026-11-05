"""Published amounts, rates, dates and countries — read, never estimated.

Every parser returns None when the text is not explicit: no implicit currency, no implicit unit, no
"closest" value. "FCFA" is read as XOF only by collectors whose publisher is a UMOA institution
(BOAD, BRVM, AMF-UMOA, UMOA-Titres): the franc CFA of Central Africa (XAF) is never issued there.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from scraping.deals.umoa_titres_auctions import norm

# Official country names as printed by the sources (FR / EN), normalized by ``norm``.
UMOA_COUNTRY_NAMES = {
    "BENIN": "BJ",
    "REPUBLIQUE DU BENIN": "BJ",
    "BURKINA FASO": "BF",
    "BURKINA": "BF",
    "COTE D IVOIRE": "CI",
    "IVORY COAST": "CI",
    "REPUBLIQUE DE COTE D IVOIRE": "CI",
    "GUINEE BISSAU": "GW",
    "GUINEA BISSAU": "GW",
    "MALI": "ML",
    "NIGER": "NE",
    "SENEGAL": "SN",
    "TOGO": "TG",
}
UMOA_CODES = frozenset(UMOA_COUNTRY_NAMES.values())

MONTHS = {
    # French
    "janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
    "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12,
    # English (full and abbreviated, as printed by IFC: "Apr 11, 2025")
    "january": 1, "february": 2, "march": 3, "april": 4, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10,
    "nov": 11, "dec": 12,
}

# Multiplier words -> (unit of the deal schema, factor). Only explicit words are read.
SCALE_WORDS = {
    "milliards": ("billions", Decimal("1e9")),
    "milliard": ("billions", Decimal("1e9")),
    "mds": ("billions", Decimal("1e9")),
    "md": ("billions", Decimal("1e9")),
    "billion": ("billions", Decimal("1e9")),
    "billions": ("billions", Decimal("1e9")),
    "millions": ("millions", Decimal("1e6")),
    "million": ("millions", Decimal("1e6")),
    "m": ("millions", Decimal("1e6")),
    "k": ("thousands", Decimal("1e3")),
}
# Currency spellings -> ISO 4217. "FCFA" / "F CFA" only when the caller allows it (UMOA publisher).
CURRENCY_WORDS = {"usd": "USD", "us$": "USD", "$": "USD", "eur": "EUR", "€": "EUR", "euros": "EUR", "euro": "EUR",
                  # Press (audit 22/10/2026, M6): only the explicit US dollar; "dollars" alone is not assumed.
                  "dollars americains": "USD", "dollars us": "USD", "dollars des etats-unis": "USD"}
CFA_WORDS = ("fcfa", "f cfa", "francs cfa", "xof")
# Compact forms used by Proparco: "20 MUSD", "45,9 MEUR", "150 KEUR".
COMPACT_RE = re.compile(r"(?P<num>\d[\d\s .,]*)\s*(?P<scale>[MK])(?P<cur>EUR|USD)\b")


def fold(text: str) -> str:
    """Lower-case, accents removed, spaces collapsed (comparison only, never displayed)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(text.replace(" ", " ").split())


def parse_number(text: str) -> Decimal | None:
    """'79.29' / '5,9' / '18724838' / '15 000,50' / '6 210' -> Decimal; ambiguous -> None.

    A single '.' or ',' followed by 1-2 digits is a decimal separator; groups of exactly three digits
    after a separator are thousands only when the separator is a space. '1.250' is ambiguous -> None.
    """
    t = text.strip().replace(" ", " ")
    if not t or not re.fullmatch(r"\d[\d ]*(?:[.,]\d+)?", t):
        return None
    t = t.replace(" ", "")
    if re.fullmatch(r"\d+[.,]\d{3}", t):  # '1.250' or '1,250': thousands or decimals? never guessed
        return None
    try:
        return Decimal(t.replace(",", "."))
    except InvalidOperation:
        return None


def parse_rate(text: str) -> Decimal | None:
    """'7,00 %' / '6.95%' -> Decimal('7.00'); without a percent sign -> None."""
    m = re.search(r"(\d{1,2}(?:[.,]\d{1,4})?)\s*%", text)
    return Decimal(m.group(1).replace(",", ".")) if m else None


def parse_day(text: str) -> date | None:
    """'21 mai 2024', '1er juin 2025', 'Apr 11, 2025', '25/06/2025', '2026-06-26' -> date; else None."""
    t = fold(text)
    if m := re.search(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)", t):  # also '2024-12-13T13:13:26+01:00'
        return _date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    if m := re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t):
        return _date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    if m := re.search(r"\b(\d{1,2})(?:er)?\s+([a-z]+)\.?\s+(\d{4})\b", t):
        month = MONTHS.get(m.group(2))
        return _date(int(m.group(3)), month, int(m.group(1))) if month else None
    if m := re.search(r"\b([a-z]+)\.?\s+(\d{1,2}),\s*(\d{4})\b", t):
        month = MONTHS.get(m.group(1))
        return _date(int(m.group(3)), month, int(m.group(2))) if month else None
    return None


def _date(y: int, m: int | None, d: int) -> date | None:
    if m is None:
        return None
    try:
        return date(y, m, d)
    except ValueError:
        return None


@dataclass(frozen=True)
class Money:
    amount: Decimal  # absolute value (already multiplied by the scale)
    currency: str
    unit: str  # units | thousands | millions | billions (as printed)
    original: str  # the exact words read
    # The number as printed, in ``unit`` ("10 Mds" -> 10): what a deal stores in amount + unit, so that
    # amount x scale(unit) is the value for every source (UMOA-Titres stores "4431.25 millions" the same way).
    figure: Decimal = Decimal(0)


def parse_money(text: str, *, allow_cfa: bool = False) -> Money | None:
    """One explicit amount with its currency: '10 Mds FCFA', '79.29 million (USD)', 'US$40 million',
    '20 MUSD'. Two different amounts, no currency or a CFA franc not allowed -> None."""
    raw = " ".join(text.replace(" ", " ").split())
    compact = list(COMPACT_RE.finditer(raw))
    if len(compact) > 1:
        return None
    if compact:
        m = compact[0]
        num = parse_number(m.group("num"))
        if num is None:
            return None
        unit, factor = SCALE_WORDS[m.group("scale").lower()]
        return Money(_plain(num * factor), m.group("cur"), unit, m.group(0).strip(), _plain(num))
    # fold() drops non-ASCII signs: "500 M€" would lose its currency and "300–500" would become "300500".
    t = fold(re.sub(r"[–—‒−]", " - ", raw.replace("€", " eur ")))
    currency = None
    for word, iso in CURRENCY_WORDS.items():
        if re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", t):
            if currency not in (None, iso):
                return None
            currency = iso
    if any(w in t for w in CFA_WORDS):
        if not allow_cfa or currency not in (None, "XOF"):
            return None
        currency = "XOF"
    if currency is None:
        return None
    numbers = re.findall(r"\d[\d ]*(?:[.,]\d+)?", t)
    numbers = [n.strip() for n in numbers if n.strip()]
    if len(numbers) != 1:
        return None
    num = parse_number(numbers[0])
    if num is None:
        return None
    unit, factor = "units", Decimal(1)
    after = t[t.find(numbers[0]) + len(numbers[0]):]
    if m := re.match(r"\s*([a-z]+)\b", after):
        if m.group(1) in SCALE_WORDS:
            unit, factor = SCALE_WORDS[m.group(1)]
    return Money(_plain(num * factor), currency, unit, raw, _plain(num))


def _plain(value: Decimal) -> Decimal:
    """10E+9 -> 10000000000 (same value, plain notation for storage and display)."""
    value = value.normalize()
    return value.quantize(Decimal(1)) if value.as_tuple().exponent > 0 else value


def umoa_countries(text: str) -> list[str]:
    """UMOA country codes named in a text, in order, without duplicates. 'Nigeria' is not 'Niger'."""
    words = f" {norm(text)} "
    found: list[tuple[int, str]] = []
    for name, code in UMOA_COUNTRY_NAMES.items():
        for m in re.finditer(rf"(?<=\s){re.escape(name)}(?=\s)", words):
            found.append((m.start(), code))
    out: list[str] = []
    for _, code in sorted(found):
        if code not in out:
            out.append(code)
    return out

