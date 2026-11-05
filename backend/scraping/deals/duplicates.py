"""Duplicate CANDIDATE detection for deals (Phase 13) — explicit criteria, no score.

Two deals become a *duplicate candidate* when they share an anchor and at least three criteria
match. Auction references and bond coupon/tenor prevent separate operations from being grouped.
The importer automatically merges only exact operation keys with matching published terms;
ambiguous candidates remain in the Review Center.

Cross-source criteria (automated collection, migration 0020):
  - ``counterparty`` (anchor): the borrower of one deal is the issuer of the other (a DFI loan and a
    listed bond of the same company). Added only when neither ``borrower`` nor ``issuer`` matched, so
    one party is never counted twice;
  - ``isin`` (NOT an anchor): same ISIN, value date absent on one side or different. The instrument
    anchor still requires the same value date: a re-opening never becomes a candidate through it;
  - bond labels as published ("PAD 6,60% 2020-2027"), for index entries without named parties:
    ``label_issuer`` (anchor: the words of the label other than coupon, years and generic bond words
    largely overlap), ``coupon`` (same printed coupon) and ``tenor_years`` (same year range). Read only
    from titles that print BOTH a coupon and a year range;
  - ``project`` also accepts two project titles whose significant words overlap at 80 % or more;
  - ``undated_isin`` (audit 22/10/2026, H3): same ISIN when exactly ONE side has no value date (a press
    article or an index entry naming the security of a dated primary deal). With the same amount in
    the same currency it is enough for a candidate — the reader still decides which re-opening it is.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

AMOUNT_TOLERANCE = Decimal("0.05")  # ±5 % of the larger amount, same currency only
DATE_WINDOW_DAYS = 90
ANCHORS = ("borrower", "project", "instrument", "auction", "counterparty", "label_issuer")
LABEL_OVERLAP = 0.6
PROJECT_OVERLAP = 0.8
LABEL_RE = re.compile(r"(?P<coupon>\d{1,2}(?:[.,]\d{1,4})?)\s*%.*?(?P<y1>(?:19|20)\d{2})\s*[-–/]\s*(?P<y2>(?:19|20)\d{2})")
# Generic words of a bond label: they say nothing about who issues it.
LABEL_STOPWORDS = frozenset(
    "emprunt emprunts obligataire obligataires obligation obligations par ape appel public publique epargne "
    "bond bonds green social sustainable sustainability linked gss diaspora placement prive privee "
    "de du des la le les l d et en a au aux sa s".split()
)
PROJECT_STOPWORDS = frozenset("de du des la le les l d et en a au aux pour un une the of and in for".split())
MIN_CRITERIA = 3


def normalize_name(value: str | None) -> str | None:
    """Technical comparison key: accents, case and punctuation removed. Display is unchanged."""
    if not value:
        return None
    text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().casefold()
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return text or None


def party_key(institution_id: str | None, name: str | None) -> str | None:
    if institution_id:
        return f"i:{institution_id}"
    n = normalize_name(name)
    return f"n:{n}" if n else None


@dataclass
class DealFacts:
    id: str
    deal_type: str | None = None
    project_name: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    unit: str | None = None  # amount x scale(unit) is the value: "4431.25 millions" vs "4431250000 units"
    signing_date: date | None = None
    announcement_date: date | None = None
    # (role, institution_id, name)
    participants: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    isin: str | None = None
    value_date: date | None = None
    # Entity Hub ids of the issuers (role "issuer" linked to an entity).
    issuer_entities: frozenset[str] = frozenset()
    # Published title (bond labels are compared on it; never a criterion by itself).
    title: str | None = None
    auction_reference: str | None = None
    auction_date: date | None = None
    maturity_date: date | None = None
    instrument_type: str | None = None
    country_id: str | None = None
    financial_close_date: date | None = None
    closing_date: date | None = None
    operation_key: str | None = None

    def keys(self, *, borrower: bool) -> set[str]:
        """Borrower keys, or the keys of the OTHER participants. The issuer is excluded from the
        latter: it is compared by the dedicated "issuer" criterion only (never counted twice)."""
        return {
            k
            for role, inst, name in self.participants
            if (role == "borrower") == borrower and role != "issuer" and (k := party_key(inst, name))
        }

    def issuer_keys(self) -> set[str]:
        """Issuer identity: its Entity Hub id when linked, else its directory / normalized name."""
        named = {k for role, inst, name in self.participants if role == "issuer" and (k := party_key(inst, name))}
        return {f"e:{e}" for e in self.issuer_entities} or named


    def counterparty_keys(self) -> set[str]:
        """Borrower and issuer, whatever their role: the party that receives the financing."""
        return {k for role, inst, name in self.participants
                if role in ("borrower", "issuer") and (k := party_key(inst, name))}


@dataclass(frozen=True)
class BondLabel:
    words: frozenset[str]
    coupon: Decimal
    years: tuple[int, int]


def bond_label(title: str | None) -> BondLabel | None:
    """Coupon, year range and issuer words of a published bond label; None if not a bond label."""
    if not title:
        return None
    text = re.sub(r"\([^)]*\)", " ", title)  # BRVM symbol "(PADS.O3)"
    m = LABEL_RE.search(text)
    if not m:
        return None
    rest = text[: m.start()] + " " + text[m.end():]
    words = frozenset(w for w in (normalize_name(rest) or "").split() if w not in LABEL_STOPWORDS
                      and not w.isdigit())
    return BondLabel(words, Decimal(m.group("coupon").replace(",", ".")), (int(m.group("y1")), int(m.group("y2"))))


def _overlap(a: frozenset[str] | set[str], b: frozenset[str] | set[str]) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def _project_words(name: str | None) -> set[str]:
    return {w for w in (normalize_name(name) or "").split() if w not in PROJECT_STOPWORDS}


def _same_project(a: str | None, b: str | None) -> bool:
    pa, pb = normalize_name(a), normalize_name(b)
    if not pa or not pb:
        return False
    if pa == pb:
        return True
    wa, wb = _project_words(a), _project_words(b)
    return min(len(wa), len(wb)) >= 3 and _overlap(wa, wb) >= PROJECT_OVERLAP


UNIT_SCALE = {None: 1, "units": 1, "thousands": 10**3, "millions": 10**6, "billions": 10**9}


def absolute_amount(amount: Decimal | None, unit: str | None) -> Decimal | None:
    """The value an amount stands for: the printed figure times the scale of its unit."""
    if amount is None or unit not in UNIT_SCALE:
        return None
    return amount * UNIT_SCALE[unit]


def _close_dates(a: date | None, b: date | None) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= DATE_WINDOW_DAYS


def matched_criteria(a: DealFacts, b: DealFacts) -> list[str]:
    # The AMF registry assigns one stable operation identifier per official entry.
    # Two different registry IDs are separate records even when their short labels match.
    amf_prefix = "amf-umoa:operation:"
    if (
        a.operation_key and b.operation_key
        and a.operation_key.startswith(amf_prefix) and b.operation_key.startswith(amf_prefix)
        and a.operation_key != b.operation_key
    ):
        return []

    # One ISIN can be reused in distinct adjudications on the same value date.
    # A different auction reference/date proves these are separate operations.
    same_isin = bool(a.isin and a.isin == b.isin)
    if same_isin:
        if a.auction_reference and b.auction_reference and a.auction_reference != b.auction_reference:
            return []
        if a.auction_date and b.auction_date and a.auction_date != b.auction_date:
            return []

    la, lb = bond_label(a.title), bond_label(b.title)
    # Coupon and maturity identify distinct bond issues; issuer overlap alone is not enough.
    if la and lb and (la.coupon != lb.coupon or la.years != lb.years):
        return []

    criteria: list[str] = []
    if a.keys(borrower=True) & b.keys(borrower=True):
        criteria.append("borrower")
    if _same_project(a.project_name, b.project_name):
        criteria.append("project")
    va, vb = absolute_amount(a.amount, a.unit), absolute_amount(b.amount, b.unit)
    if (
        va is not None
        and vb is not None
        and a.currency is not None
        and a.currency == b.currency
        and abs(va - vb) <= AMOUNT_TOLERANCE * max(va, vb)
    ):
        criteria.append("currency_amount")
    if _close_dates(a.signing_date, b.signing_date) or _close_dates(a.announcement_date, b.announcement_date):
        criteria.append("dates")
    if a.deal_type is not None and a.deal_type == b.deal_type:
        criteria.append("deal_type")
    if a.keys(borrower=False) & b.keys(borrower=False):
        criteria.append("participants")
    if (
        same_isin and a.value_date is not None and a.value_date == b.value_date
        and (not a.auction_reference or not b.auction_reference or a.auction_reference == b.auction_reference)
        and (not a.auction_date or not b.auction_date or a.auction_date == b.auction_date)
    ):
        criteria.append("instrument")
    if (
        a.auction_reference and b.auction_reference and a.auction_reference == b.auction_reference
        and (not a.auction_date or not b.auction_date or a.auction_date == b.auction_date)
    ):
        criteria.append("auction")
    if a.issuer_keys() & b.issuer_keys():
        criteria.append("issuer")
    if ("borrower" not in criteria and "issuer" not in criteria
            and a.counterparty_keys() & b.counterparty_keys()):
        criteria.append("counterparty")
    if "instrument" not in criteria and a.isin is not None and a.isin == b.isin:
        criteria.append("isin")
        if (a.value_date is None) != (b.value_date is None):
            criteria.append("undated_isin")
    if la and lb:
        if _overlap(la.words, lb.words) >= LABEL_OVERLAP:
            criteria.append("label_issuer")
        if la.coupon == lb.coupon:
            criteria.append("coupon")
        if la.years == lb.years:
            criteria.append("tenor_years")
    return criteria


def is_candidate(criteria: list[str]) -> bool:
    if "undated_isin" in criteria and "currency_amount" in criteria:
        return True
    return any(c in criteria for c in ANCHORS) and len(criteria) >= MIN_CRITERIA
