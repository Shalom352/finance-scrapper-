"""
Automatic validation (Phase 21) — conservative, explained, always reversible by a human.

Decision of the owner (06/10/2026): rows may be validated automatically when EVERY check below
passes. The automatic decision is recorded as such (``validation_method = 'automatic'``, ruleset
version, result of each check, audit event ``auto_validate``) and a human can withdraw it at any
time (``revoke_automatic``): the row goes back to ``needs_review`` and the robot never validates it
again (``auto_validation_blocked``).

Outcome
  every check passes AND an independent document gives the same value  -> verified  (automatic)
  every check passes, single source                                     -> reviewed  (automatic), or
                                       verified when the owner sets single_source_status='verified'
  one check fails                                                       -> unchanged (report stored)
Rows decided by a human (reviewed / verified / rejected with method 'human' or legacy) are never
touched. ``reviewed`` rows validated automatically are upgraded to ``verified`` once corroborated.

Financial observation checks
  provenance          institution, source, document, page, original value, unit; currency for amounts
  normalization       value_original x unit multiplier == value_normalized; currency unchanged
  source_text         the original value is printed on its page of the stored document (re-read)
  scope_evidence      scope evidence class in the accepted classes (default A, B, C)
  quality_flags       no blocking quality flag
  no_conflict         no other non-rejected observation of the same key with another value
  accounting          balance-sheet components <= total assets (same document, same year), totals > 0
  time_series         balance-sheet amount within x0.2 .. x5 of the adjacent years (when they exist)
  corroboration       (not a failure) another document gives the same value -> verified

Deal checks
  sources             >= 1 source; every published field attested by a source (field provenance)
  primary_source      at least one primary source (note, market result, issuer release); press /
                      AMF index only -> never automatic
  participants        every role read in the TEXT of a source (visual readings need a human)
  duplicates          no undecided duplicate candidate
  amount              amount > 0 with a currency, or no amount
  corroboration       (not a failure) two PRIMARY documents -> verified
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.deals import PROVENANCE_FIELDS
from app.constants.quality import BLOCKING_QUALITY_FLAGS
from app.models.deal import (
    Deal,
    DealDuplicateCandidate,
    DealFieldSource,
    DealParticipant,
    DealSource,
)
from app.models.document import Document
from app.models.financial_data import FinancialData
from app.models.review_event import FinancialDataReviewEvent

RULESET_VERSION = "auto-v1"
ACTOR = f"auto-validator:{RULESET_VERSION}"
DEFAULT_SCOPE_CLASSES = ("A", "B", "C")
PRIMARY_CLASSES = ("primary_regulatory", "primary_market", "issuer_official", "issuer_press_release")
AUTOMATED_PRIMARY_KEYS = ("umoa_titres:",)  # automated ingestions that cross-check page vs PDF

MULTIPLIERS = {
    "absolute": 1, "unit": 1, "units": 1, "%": 1, "ratio": 1, "percent": 1,
    "thousand": 1_000, "thousands": 1_000, "mille": 1_000, "milliers": 1_000, "k": 1_000,
    "million": 1_000_000, "millions": 1_000_000, "m": 1_000_000,
    "milliard": 1_000_000_000, "milliards": 1_000_000_000, "billion": 1_000_000_000, "billions": 1_000_000_000,
}
BALANCE_COMPONENTS = ("creances_clients", "creances_banques", "depots_clients", "depots_banques",
                      "immobilisations", "tresorerie", "capitaux_propres", "dettes_totales", "emprunts_bancaires")
BALANCE_METRICS = ("total_actifs", "total_passifs") + BALANCE_COMPONENTS
INCOME_METRICS = ("produit_net_bancaire", "resultat_exploitation", "resultat_net", "produits_totaux",
                  "charges_totales", "chiffre_affaires")
NUMBER_RE = re.compile(r"[-−]?\d{1,3}(?:[    ]\d{3})+(?:[.,]\d+)?|[-−]?\d+(?:[.,]\d+)?")


def _check(name: str, ok: bool | None, detail: str = "") -> dict[str, Any]:
    return {"check": name, "result": "skip" if ok is None else ("pass" if ok else "fail"), "detail": detail}


def compact_number(raw: str) -> str:
    text = unicodedata.normalize("NFKC", raw).replace("−", "-")
    return re.sub(r"[\s   ]", "", text).replace(",", ".")


def parse_original(raw: str) -> Decimal | None:
    try:
        return Decimal(compact_number(raw))
    except (InvalidOperation, ValueError):
        return None


def multiplier(unit: str | None) -> int | None:
    return MULTIPLIERS.get((unit or "").strip().lower())


class PageTextCache:
    """Numbers printed on each page of the stored documents (re-read from the file itself)."""

    def __init__(self, storage_root: Path):
        self.root = storage_root
        self._cache: dict[str, list[set[str]] | None] = {}

    def numbers(self, doc: Document, page: int) -> set[str] | None:
        if doc.id not in self._cache:
            self._cache[doc.id] = self._load(doc)
        pages = self._cache[doc.id]
        if pages is None or not (0 < page <= len(pages)):
            return None
        return pages[page - 1]

    def _load(self, doc: Document) -> list[set[str]] | None:
        if not doc.storage_path:
            return None
        path = self.root / doc.storage_path
        if not path.is_file() or path.suffix.lower() != ".pdf":
            return None
        import pymupdf

        out = []
        with pymupdf.open(path) as pdf:
            for page in pdf:
                found: set[str] = set()
                for line in page.get_text().splitlines():
                    found.update(compact_number(m.group(0)) for m in NUMBER_RE.finditer(line))
                    found.add(compact_number(line.strip()))
                out.append(found)
        return out


@dataclass
class AutoReport:
    examined: int = 0
    reviewed: list[str] = field(default_factory=list)
    verified: list[str] = field(default_factory=list)
    upgraded: list[str] = field(default_factory=list)
    unchanged: int = 0
    failures: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def summary(self) -> dict[str, Any]:
        return {"examined": self.examined, "reviewed_auto": len(self.reviewed), "verified_auto": len(self.verified),
                "upgraded_to_verified": len(self.upgraded), "unchanged": self.unchanged,
                "failed_checks": dict(sorted(self.failures.items()))}


def _key(r: FinancialData) -> tuple:
    return (r.institution_id, r.metric_code, r.period_year, r.period_type, r.scope)


def _tolerance(a: FinancialData, b: FinancialData) -> Decimal:
    m = max(multiplier(a.unit_original) or 1, multiplier(b.unit_original) or 1)
    return Decimal(m) / 2


def basic_checks(r: FinancialData, doc: Document | None, pages: PageTextCache) -> list[dict]:
    checks = []
    monetary = (r.unit_normalized or "") == "absolute"
    missing = [n for n, v in (("institution", r.institution_id), ("document", r.document_id),
                              ("page", r.page_number), ("value_original", r.value_original),
                              ("unit", r.unit_original)) if not v]
    if monetary and not r.currency_original:
        missing.append("currency")
    checks.append(_check("provenance", not missing, ", ".join(missing)))

    original, mult = parse_original(r.value_original or ""), multiplier(r.unit_original)
    if original is None or mult is None or r.value_normalized is None:
        checks.append(_check("normalization", False, f"cannot re-read '{r.value_original}' {r.unit_original}"))
    else:
        expected = original * mult
        ok = abs(Decimal(str(r.value_normalized)) - expected) <= Decimal("0.000001") * max(abs(expected), 1)
        ok = ok and (r.currency_normalized or None) == (r.currency_original or None)
        checks.append(_check("normalization", ok, f"{r.value_original} x {mult} = {expected}"))

    if doc is None or not r.page_number:
        checks.append(_check("source_text", False, "document or page missing"))
    else:
        nums = pages.numbers(doc, r.page_number)
        if nums is None:
            checks.append(_check("source_text", False, "stored document file not available for re-reading"))
        else:
            target = compact_number(r.value_original or "")
            checks.append(_check("source_text", target in nums, f"'{r.value_original}' on p.{r.page_number}"))
    return checks


def accounting_check(r: FinancialData, same_doc: dict[str, FinancialData]) -> dict:
    if r.metric_code not in BALANCE_METRICS and r.metric_code not in INCOME_METRICS:
        return _check("accounting", None, "no accounting rule for this metric")
    total = same_doc.get("total_actifs")
    if total is None or total.value_normalized is None:
        return _check("accounting", False, "total_actifs not published in the same document / year")
    t = Decimal(str(total.value_normalized))
    if t <= 0:
        return _check("accounting", False, "total_actifs <= 0")
    def v(m: str) -> Decimal | None:
        row = same_doc.get(m)
        return Decimal(str(row.value_normalized)) if row is not None and row.value_normalized is not None else None
    problems = []
    for m in BALANCE_COMPONENTS:
        x = v(m)
        if x is not None and x > t:
            problems.append(f"{m} > total_actifs")
    assets = [x for x in (v("creances_clients"), v("creances_banques")) if x is not None and x > 0]
    if sum(assets, Decimal(0)) > t:
        problems.append("créances clientèle + interbancaires > total_actifs")
    liabilities = [x for x in (v("depots_clients"), v("depots_banques"), v("capitaux_propres")) if x is not None and x > 0]
    if sum(liabilities, Decimal(0)) > t:
        problems.append("dépôts + dettes interbancaires + capitaux propres > total_actifs")
    for m in ("produit_net_bancaire", "resultat_net", "resultat_exploitation"):
        x = v(m)
        if x is not None and abs(x) > t:
            problems.append(f"|{m}| > total_actifs")
    passifs = v("total_passifs")
    if passifs is not None and abs(passifs - t) > _tolerance(total, same_doc["total_passifs"]):
        problems.append("total_passifs != total_actifs")
    return _check("accounting", not problems, "; ".join(problems) or "coherent with total_actifs")


def time_check(r: FinancialData, series: dict[int, list[FinancialData]]) -> dict:
    if r.metric_code not in BALANCE_METRICS:
        return _check("time_series", None, "not applied to this metric")
    x = Decimal(str(r.value_normalized))
    neighbours = [n for y in (r.period_year - 1, r.period_year + 1) for n in series.get(y, [])
                  if n.value_normalized is not None and n.status != "rejected"]
    if not neighbours:
        return _check("time_series", None, "no adjacent year")
    bad = []
    for n in neighbours:
        y = Decimal(str(n.value_normalized))
        if x <= 0 or y <= 0:
            continue
        ratio = x / y
        if ratio < Decimal("0.2") or ratio > 5:
            bad.append(f"{n.period_year}: x{ratio:.2f}")
    return _check("time_series", not bad, "; ".join(bad) or "within x0.2..x5 of adjacent years")


async def validate_financial_data(db: AsyncSession, *, storage_root: Path, scope_classes=DEFAULT_SCOPE_CLASSES,
                                  dry_run: bool = False, limit: int | None = None,
                                  single_source_status: str = "reviewed") -> AutoReport:
    report = AutoReport()
    pages = PageTextCache(storage_root)
    cand_q = select(FinancialData).where(
        FinancialData.deleted_at.is_(None), FinancialData.auto_validation_blocked.is_(False),
        FinancialData.institution_id.is_not(None), FinancialData.value_normalized.is_not(None),
        or_(FinancialData.status.in_(("extracted", "needs_review")),
            (FinancialData.status == "reviewed") & (FinancialData.validation_method == "automatic")),
    ).order_by(FinancialData.institution_id, FinancialData.period_year)
    if limit:
        cand_q = cand_q.limit(limit)
    candidates = (await db.execute(cand_q)).scalars().all()
    if not candidates:
        return report
    inst_ids = {c.institution_id for c in candidates}
    rows = (await db.execute(select(FinancialData).where(
        FinancialData.institution_id.in_(inst_ids), FinancialData.deleted_at.is_(None),
        FinancialData.status != "rejected"))).scalars().all()
    docs = {d.id: d for d in (await db.execute(select(Document).where(
        Document.id.in_({r.document_id for r in rows})))).scalars()}
    by_key: dict[tuple, list[FinancialData]] = defaultdict(list)
    by_doc_year: dict[tuple, dict[str, FinancialData]] = defaultdict(dict)
    series: dict[tuple, dict[int, list[FinancialData]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        by_key[_key(r)].append(r)
        by_doc_year[(r.document_id, r.institution_id, r.period_year, r.period_type, r.scope)][r.metric_code] = r
        series[(r.institution_id, r.metric_code, r.period_type, r.scope)][r.period_year].append(r)

    now = datetime.now(UTC)
    for r in candidates:
        report.examined += 1
        doc = docs.get(r.document_id)
        checks = basic_checks(r, doc, pages)
        checks.append(_check("scope_evidence", (r.scope_evidence_class or "") in scope_classes,
                             f"class {r.scope_evidence_class or 'none'} (accepted: {', '.join(scope_classes)})"))
        blocking = [f["code"] for f in r.quality_flags or [] if f.get("code") in BLOCKING_QUALITY_FLAGS]
        checks.append(_check("quality_flags", not blocking, ", ".join(blocking)))
        others = [o for o in by_key[_key(r)] if o.id != r.id and o.value_normalized is not None]
        conflicting = [o for o in others if abs(Decimal(str(o.value_normalized)) - Decimal(str(r.value_normalized)))
                       > _tolerance(r, o)]
        checks.append(_check("no_conflict", not conflicting,
                             ", ".join(f"{o.value_normalized} ({o.status})" for o in conflicting)))
        checks.append(accounting_check(r, by_doc_year[(r.document_id, r.institution_id, r.period_year,
                                                       r.period_type, r.scope)]))
        checks.append(time_check(r, series[(r.institution_id, r.metric_code, r.period_type, r.scope)]))
        corroborating = []
        for o in others:
            od = docs.get(o.document_id)
            if od is None or o.document_id == r.document_id or (od.file_hash and doc and od.file_hash == doc.file_hash):
                continue
            if all(c["result"] == "pass" for c in basic_checks(o, od, pages)):
                corroborating.append(o)
        checks.append({"check": "corroboration", "result": "pass" if corroborating else "info",
                       "detail": ", ".join(f"document {o.document_id} p.{o.page_number}" for o in corroborating)
                       or "single source"})
        failed = [c for c in checks if c["result"] == "fail"]
        payload = {"ruleset": RULESET_VERSION, "checked_at": now.isoformat(), "checks": checks,
                   "outcome": None}
        if failed:
            for c in failed:
                report.failures[c["check"]] += 1
            payload["outcome"] = "not_validated"
            r.auto_validation = payload
            report.unchanged += 1
            continue
        target = "verified" if corroborating else single_source_status
        if r.status == target:
            r.auto_validation = {**payload, "outcome": target}
            report.unchanged += 1
            continue
        previous = r.status
        r.status = target
        r.validation_method = "automatic"
        r.auto_validation = {**payload, "outcome": target}
        if target == "verified":
            r.verified_by, r.verified_at = ACTOR, now
            (report.upgraded if previous == "reviewed" else report.verified).append(r.id)
        else:
            report.reviewed.append(r.id)
        r.updated_at = now
        db.add(FinancialDataReviewEvent(
            financial_data_id=r.id, action="auto_validate", previous_status=previous, new_status=target,
            reason=f"Validation automatique {RULESET_VERSION} : {len(checks)} contrôles"
                   + (" ; corroborée par un second document" if corroborating else " ; source unique"),
            actor=ACTOR, value_before=r.value_normalized, value_after=r.value_normalized))
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report


async def validate_deals(db: AsyncSession, *, dry_run: bool = False,
                         single_source_status: str = "reviewed") -> AutoReport:
    report = AutoReport()
    deals = (await db.execute(select(Deal).where(
        Deal.deleted_at.is_(None), Deal.merged_into_deal_id.is_(None), Deal.auto_validation_blocked.is_(False),
        or_(Deal.status.in_(("extracted", "needs_review")),
            (Deal.status == "reviewed") & (Deal.validation_method == "automatic"))))).scalars().all()
    if not deals:
        return report
    ids = [d.id for d in deals]
    sources: dict[str, list[DealSource]] = defaultdict(list)
    for s in (await db.execute(select(DealSource).where(DealSource.deal_id.in_(ids)))).scalars():
        sources[s.deal_id].append(s)
    attested: dict[str, set[str]] = defaultdict(set)
    for fs in (await db.execute(select(DealFieldSource).where(DealFieldSource.deal_id.in_(ids)))).scalars():
        attested[fs.deal_id].add(fs.field_name)
    parts: dict[str, list[DealParticipant]] = defaultdict(list)
    for p in (await db.execute(select(DealParticipant).where(DealParticipant.deal_id.in_(ids)))).scalars():
        parts[p.deal_id].append(p)
    open_dups: set[str] = set()
    for c in (await db.execute(select(DealDuplicateCandidate).where(
            DealDuplicateCandidate.state == "duplicate_candidate"))).scalars():
        open_dups.update((c.deal_a_id, c.deal_b_id))

    now = datetime.now(UTC)
    for d in deals:
        report.examined += 1
        srcs = sources.get(d.id, [])
        published = [f for f in PROVENANCE_FIELDS if f != "country_code" and getattr(d, f, None) is not None]
        unattested = [f for f in published if f not in attested[d.id]]
        automated = bool(d.ingestion_key and d.ingestion_key.startswith(AUTOMATED_PRIMARY_KEYS))
        primaries = [s for s in srcs if s.source_class in PRIMARY_CLASSES or (s.source_class is None and automated)]
        visual = [p.participant_name for p in parts.get(d.id, []) if (p.extraction_method or "text") != "text"]
        checks = [
            _check("sources", bool(srcs) and not unattested,
                   "no source" if not srcs else (", ".join(unattested) or f"{len(srcs)} source(s)")),
            _check("primary_source", bool(primaries), f"{len(primaries)} primary source(s)"),
            _check("participants", not visual, ", ".join(visual) or "all roles read in the text"),
            _check("duplicates", d.id not in open_dups, "undecided duplicate candidate" if d.id in open_dups else ""),
            _check("amount", d.amount is None or (d.amount > 0 and bool(d.currency)), f"{d.amount} {d.currency}"),
        ]
        primary_documents = {s.document_id for s in primaries}
        corroborated = len(primary_documents) >= 2  # two PRIMARY documents (press / AMF index never count)
        checks.append({"check": "corroboration", "result": "pass" if corroborated else "info",
                       "detail": f"{len(primary_documents)} primary document(s)"})
        failed = [c for c in checks if c["result"] == "fail"]
        payload = {"ruleset": RULESET_VERSION, "checked_at": now.isoformat(), "checks": checks, "outcome": None}
        if failed:
            for c in failed:
                report.failures[c["check"]] += 1
            d.auto_validation = {**payload, "outcome": "not_validated"}
            report.unchanged += 1
            continue
        target = "verified" if corroborated else single_source_status
        if d.status == target:
            d.auto_validation = {**payload, "outcome": target}
            report.unchanged += 1
            continue
        previous = d.status
        d.status, d.validation_method = target, "automatic"
        d.auto_validation = {**payload, "outcome": target}
        if target == "verified":
            d.verified_by, d.verified_at = ACTOR, now
            (report.upgraded if previous == "reviewed" else report.verified).append(d.id)
        else:
            report.reviewed.append(d.id)
        d.updated_at = now
        db.add(FinancialDataReviewEvent(
            deal_id=d.id, action="auto_validate", previous_status=previous, new_status=target,
            reason=f"Validation automatique {RULESET_VERSION} : {len(checks)} contrôles", actor=ACTOR,
            value_before=d.amount, value_after=d.amount))
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report


class RevokeError(ValueError):
    pass


async def revoke(db: AsyncSession, target: Any, *, actor: str, reason: str) -> None:
    """A human withdraws an automatic validation: back to needs_review, never re-validated automatically."""
    if not actor or not actor.strip() or not reason or not reason.strip():
        raise RevokeError("actor and reason are required")
    if target.validation_method != "automatic":
        raise RevokeError("this row was not validated automatically")
    now = datetime.now(UTC)
    previous = target.status
    target.status = "needs_review"
    target.validation_method = None
    target.verified_by = None
    target.verified_at = None
    target.auto_validation_blocked = True
    target.auto_validation = {**(target.auto_validation or {}), "revoked_by": actor.strip(),
                              "revoked_at": now.isoformat(), "revoke_reason": reason.strip()}
    target.updated_at = now
    is_deal = isinstance(target, Deal)
    value = target.amount if is_deal else target.value_normalized
    db.add(FinancialDataReviewEvent(
        deal_id=target.id if is_deal else None, financial_data_id=None if is_deal else target.id,
        action="revoke_automatic", previous_status=previous, new_status="needs_review", reason=reason.strip(),
        actor=actor.strip(), value_before=value, value_after=value))


async def revoke_all(db: AsyncSession, *, actor: str, reason: str, dry_run: bool = False) -> dict[str, int]:
    """Withdraw EVERY automatic validation at once (kill switch)."""
    counts = {"financial_data": 0, "deals": 0}
    for model, key in ((FinancialData, "financial_data"), (Deal, "deals")):
        rows = (await db.execute(select(model).where(model.validation_method == "automatic",
                                                     model.deleted_at.is_(None)))).scalars().all()
        for row in rows:
            await revoke(db, row, actor=actor, reason=reason)
            counts[key] += 1
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return counts
