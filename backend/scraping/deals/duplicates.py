"""Duplicate CANDIDATE detection for deals (Phase 13) — explicit criteria, no score.

Two deals become a *duplicate candidate* when they share an anchor (same borrower, same
project, or the same public-debt instrument = same ISIN AND same value date) AND at least three
criteria match in total. Two tranches of one auction (different ISINs) or two re-openings of one
ISIN (different value dates) never share the instrument anchor. The matched criteria are stored and
shown as they are. A candidate is never a merge: only a human decision in the Review Center
says "same deal", "distinct deals" or "same deal reported by several sources".
"""
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

AMOUNT_TOLERANCE = Decimal("0.05")  # ±5 % of the larger amount, same currency only
DATE_WINDOW_DAYS = 90
ANCHORS = ("borrower", "project", "instrument")
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
    signing_date: date | None = None
    announcement_date: date | None = None
    # (role, institution_id, name)
    participants: list[tuple[str, str | None, str | None]] = field(default_factory=list)
    isin: str | None = None
    value_date: date | None = None
    # Entity Hub ids of the issuers (role "issuer" linked to an entity).
    issuer_entities: frozenset[str] = frozenset()

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


def _close_dates(a: date | None, b: date | None) -> bool:
    return a is not None and b is not None and abs((a - b).days) <= DATE_WINDOW_DAYS


def matched_criteria(a: DealFacts, b: DealFacts) -> list[str]:
    criteria: list[str] = []
    if a.keys(borrower=True) & b.keys(borrower=True):
        criteria.append("borrower")
    pa, pb = normalize_name(a.project_name), normalize_name(b.project_name)
    if pa and pa == pb:
        criteria.append("project")
    if (
        a.amount is not None
        and b.amount is not None
        and a.currency is not None
        and a.currency == b.currency
        and abs(a.amount - b.amount) <= AMOUNT_TOLERANCE * max(a.amount, b.amount)
    ):
        criteria.append("currency_amount")
    if _close_dates(a.signing_date, b.signing_date) or _close_dates(a.announcement_date, b.announcement_date):
        criteria.append("dates")
    if a.deal_type is not None and a.deal_type == b.deal_type:
        criteria.append("deal_type")
    if a.keys(borrower=False) & b.keys(borrower=False):
        criteria.append("participants")
    if a.isin is not None and a.isin == b.isin and a.value_date is not None and a.value_date == b.value_date:
        criteria.append("instrument")
    if a.issuer_keys() & b.issuer_keys():
        criteria.append("issuer")
    return criteria


def is_candidate(criteria: list[str]) -> bool:
    return any(c in criteria for c in ANCHORS) and len(criteria) >= MIN_CRITERIA
