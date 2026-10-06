"""
Targeting (Phase 20) — "for THIS deal, which banks / institutions should we approach?"

The answer is a list of candidates with EXPLICIT criteria, each one ``met`` / ``not_met`` /
``unknown`` with its evidence. There is no score and no recommendation: the candidates are
ordered by the number of criteria met, then by the number of comparable deals, then by name.

Criteria
  presence      bank licensed in the deal's country (official list) / institution with a deal there
  experience    financing participations (FINANCING_ROLES) in comparable deals: same sector, same
                deal type, same country; reviewed or verified deals count as such, needs_review
                deals are shown as "to confirm"; rejected / merged deals never count
  capacity      banks only: indicative single-counterparty ceiling = ratio x latest PUBLISHED equity
                (``capitaux_propres``, individual, annual, same currency). The UMOA prudential norm
                uses "fonds propres effectifs", which are not published: this is an indication only,
                and an equity value in needs_review is flagged "to confirm". Never a currency conversion.
  relationship  TOMASTEED's own history with the institution (mandate contacts): positive stages,
                declines, last contact
  via_sgi       deals where the bank's SGI (documented_bank link only) had a financing role;
                a group-only link never attributes anything to a bank
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.deals import FINANCING_ROLES, POSITIVE_STAGES
from app.models.country import Country
from app.models.deal import Deal, DealParticipant, InstitutionLink
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.mandate import Mandate, MandateCounterparty

DEFAULT_CAPACITY_RATIO = Decimal("0.25")
EQUITY_METRIC = "capitaux_propres"
DIRECTORY_ENTITY_TYPES = ("development_bank", "guarantee_fund")
EQUITY_STATUS_ORDER = {"verified": 0, "reviewed": 1, "extracted": 2, "needs_review": 3}
CONFIRMED_DEAL_STATUSES = ("reviewed", "verified")
MAX_EVIDENCE_DEALS = 5
UNITS = {"units": Decimal(1), "thousands": Decimal(1_000), "millions": Decimal(1_000_000),
         "billions": Decimal(1_000_000_000)}


@dataclass
class TargetingRequest:
    country: str | None = None
    sector: str | None = None
    deal_type: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    kind: str = "all"  # all | banks | institutions
    capacity_ratio: Decimal = DEFAULT_CAPACITY_RATIO


@dataclass
class Candidate:
    kind: str  # bank | institution
    id: str
    name: str
    country_code: str | None
    entity_type: str | None = None
    website: str | None = None
    criteria: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def met(self) -> int:
        return sum(1 for c in self.criteria.values() if c["status"] == "met")

    @property
    def known(self) -> int:
        return sum(1 for c in self.criteria.values() if c["status"] != "unknown")

    @property
    def comparable_deals(self) -> int:
        return self.criteria.get("experience", {}).get("comparable_deals", 0)


def absolute_amount(amount: Decimal | None, unit: str | None) -> Decimal | None:
    """Amount in units (never a currency conversion). None if the unit is unknown."""
    if amount is None:
        return None
    factor = UNITS.get(unit or "units")
    return amount * factor if factor is not None else None


def deal_year(d: Deal) -> int | None:
    day = d.signing_date or d.announcement_date or d.value_date
    return day.year if day else None


def experience_criterion(rows: list[tuple[DealParticipant, Deal, str | None]], req: TargetingRequest) -> dict:
    """rows: (participation, deal, deal country code). Comparable = same sector OR type OR country."""
    deals: dict[str, dict[str, Any]] = {}
    for p, d, cc in rows:
        matches = []
        if req.sector and d.sector == req.sector:
            matches.append("sector")
        if req.deal_type and d.deal_type == req.deal_type:
            matches.append("deal_type")
        if req.country and cc == req.country:
            matches.append("country")
        entry = deals.setdefault(d.id, {
            "deal_id": d.id, "title": d.title, "roles": [], "matches": matches, "year": deal_year(d),
            "amount": d.amount, "unit": d.unit, "currency": d.currency, "status": d.status,
        })
        if p.role not in entry["roles"]:
            entry["roles"].append(p.role)
    comparable = [e for e in deals.values() if e["matches"]] if (req.sector or req.deal_type or req.country) \
        else list(deals.values())
    comparable.sort(key=lambda e: (-len(e["matches"]), -(e["year"] or 0), e["title"]))
    confirmed = [e for e in comparable if e["status"] in CONFIRMED_DEAL_STATUSES]
    sizes = [absolute_amount(e["amount"], e["unit"]) for e in comparable
             if req.currency and e["currency"] == req.currency and e["amount"] is not None]
    sizes = [s for s in sizes if s is not None]
    if not deals:
        status = "unknown"  # no recorded participation: absence of data, not a refusal
    else:
        status = "met" if comparable else "not_met"
    return {
        "status": status, "financing_deals": len(deals), "comparable_deals": len(comparable),
        "confirmed_deals": len(confirmed), "to_confirm": len(comparable) - len(confirmed),
        "max_comparable_amount": max(sizes) if sizes else None, "currency": req.currency if sizes else None,
        "deals": comparable[:MAX_EVIDENCE_DEALS],
    }


def capacity_criterion(equity: FinancialData | None, req: TargetingRequest) -> dict:
    if req.amount is None or req.currency is None:
        return {"status": "unknown", "reason": "amount_not_given"}
    if equity is None or equity.value_normalized is None:
        return {"status": "unknown", "reason": "equity_not_available"}
    if (equity.currency_normalized or "") != req.currency:
        return {"status": "unknown", "reason": "currency_mismatch", "equity_currency": equity.currency_normalized}
    value = Decimal(str(equity.value_normalized))
    ceiling = (value * req.capacity_ratio).quantize(Decimal("1"))
    return {
        "status": "met" if req.amount <= ceiling else "not_met",
        "equity": value, "equity_year": equity.period_year, "equity_status": equity.status,
        "equity_data_id": equity.id, "ratio": req.capacity_ratio, "indicative_ceiling": ceiling,
        "currency": req.currency, "to_confirm": equity.status not in ("verified", "reviewed"),
    }


def relationship_criterion(contacts: list[tuple[MandateCounterparty, Mandate]]) -> dict:
    if not contacts:
        return {"status": "unknown", "reason": "no_contact_recorded"}
    latest: dict[str, tuple[MandateCounterparty, Mandate]] = {}
    for c, m in contacts:  # latest stage per mandate
        prev = latest.get(m.id)
        key = (c.contact_date.isoformat() if c.contact_date else "", c.created_at.isoformat())
        if prev is None or key >= (prev[0].contact_date.isoformat() if prev[0].contact_date else "",
                                   prev[0].created_at.isoformat()):
            latest[m.id] = (c, m)
    positive = [x for x in latest.values() if x[0].stage in POSITIVE_STAGES]
    declined = [x for x in latest.values() if x[0].stage == "declined"]
    return {
        "status": "met" if positive else "not_met",
        "mandates": len(latest), "positive": len(positive), "declined": len(declined),
        "history": [{"mandate_code": m.code, "mandate_title": m.title, "stage": c.stage,
                     "contact_date": c.contact_date, "amount": c.amount, "currency": c.currency, "reason": c.reason}
                    for c, m in sorted(latest.values(), key=lambda x: x[1].code)],
    }


async def _participations(db: AsyncSession, column, ids: list[str]) -> dict[str, list]:
    if not ids:
        return {}
    rows = (await db.execute(
        select(DealParticipant, Deal, Country.code)
        .join(Deal, Deal.id == DealParticipant.deal_id)
        .outerjoin(Country, Country.id == Deal.country_id)
        .where(column.in_(ids), DealParticipant.role.in_(FINANCING_ROLES), Deal.deleted_at.is_(None),
               Deal.status != "rejected", Deal.merged_into_deal_id.is_(None))
    )).all()
    out: dict[str, list] = defaultdict(list)
    for p, d, cc in rows:
        out[getattr(p, column.key)].append((p, d, cc))
    return out


async def _latest_equity(db: AsyncSession, institution_ids: list[str]) -> dict[str, FinancialData]:
    if not institution_ids:
        return {}
    rows = (await db.execute(select(FinancialData).where(
        FinancialData.institution_id.in_(institution_ids), FinancialData.metric_code == EQUITY_METRIC,
        FinancialData.scope == "individual", FinancialData.period_type == "annual",
        FinancialData.status != "rejected", FinancialData.value_normalized.is_not(None),
        FinancialData.deleted_at.is_(None)))).scalars().all()
    best: dict[str, FinancialData] = {}
    for fd in rows:
        cur = best.get(fd.institution_id)
        key = (-fd.period_year, EQUITY_STATUS_ORDER.get(fd.status, 9))
        if cur is None or key < (-cur.period_year, EQUITY_STATUS_ORDER.get(cur.status, 9)):
            best[fd.institution_id] = fd
    return best


async def _contacts(db: AsyncSession, column, ids: list[str]) -> dict[str, list]:
    if not ids:
        return {}
    rows = (await db.execute(
        select(MandateCounterparty, Mandate).join(Mandate, Mandate.id == MandateCounterparty.mandate_id)
        .where(column.in_(ids), MandateCounterparty.deleted_at.is_(None), Mandate.deleted_at.is_(None))
    )).all()
    out: dict[str, list] = defaultdict(list)
    for c, m in rows:
        out[getattr(c, column.key)].append((c, m))
    return out


async def _via_sgi(db: AsyncSession, institution_ids: list[str], req: TargetingRequest) -> dict[str, dict]:
    links = (await db.execute(select(InstitutionLink).where(
        InstitutionLink.to_institution_id.in_(institution_ids), InstitutionLink.link_level == "documented_bank",
        InstitutionLink.status != "rejected", InstitutionLink.deleted_at.is_(None)))).scalars().all()
    out: dict[str, dict] = {}
    for link in links:
        rows = (await db.execute(
            select(DealParticipant, Deal, Country.code).join(Deal, Deal.id == DealParticipant.deal_id)
            .outerjoin(Country, Country.id == Deal.country_id)
            .where(func.upper(DealParticipant.participant_name) == link.from_name.upper(),
                   DealParticipant.role.in_(FINANCING_ROLES), Deal.deleted_at.is_(None), Deal.status != "rejected",
                   Deal.merged_into_deal_id.is_(None)))).all()
        exp = experience_criterion(list(rows), req)
        if exp["status"] == "unknown":
            continue
        exp.update({"sgi": link.from_name, "relation": link.relation, "pct": link.pct,
                    "link_source_url": link.source_url, "link_status": link.status})
        out[link.to_institution_id] = exp
    return out


async def find_candidates(db: AsyncSession, req: TargetingRequest) -> list[Candidate]:
    candidates: list[Candidate] = []

    if req.kind in ("all", "banks"):
        banks = (await db.execute(
            select(Institution, Country.code).join(Country, Country.id == Institution.country_id)
            .where(Institution.deleted_at.is_(None), Institution.status == "active")
        )).all()
        ids = [b.id for b, _ in banks]
        parts = await _participations(db, DealParticipant.institution_id, ids)
        # participations recorded on the bank's Entity Hub record (no institution row at import time)
        by_entity = {b.entity_id: b.id for b, _ in banks if b.entity_id}
        for ent_id, rows in (await _participations(db, DealParticipant.entity_id, list(by_entity))).items():
            known = {(p.id) for p, _, _ in parts.get(by_entity[ent_id], [])}
            parts.setdefault(by_entity[ent_id], []).extend(r for r in rows if r[0].id not in known)
        equity = await _latest_equity(db, ids)
        contacts = await _contacts(db, MandateCounterparty.institution_id, ids)
        sgi = await _via_sgi(db, ids, req)
        for inst, cc in banks:
            in_country = req.country is None or cc == req.country
            if not in_country and not parts.get(inst.id) and not contacts.get(inst.id) and inst.id not in sgi:
                continue  # a bank of another country with nothing on record is not a lead for this deal
            c = Candidate(kind="bank", id=inst.id, name=inst.name_official, country_code=cc,
                          website=inst.website_url)
            c.criteria["presence"] = {"status": "met" if in_country else "not_met", "country": cc} \
                if req.country else {"status": "unknown", "reason": "country_not_given"}
            c.criteria["experience"] = experience_criterion(parts.get(inst.id, []), req)
            c.criteria["capacity"] = capacity_criterion(equity.get(inst.id), req)
            c.criteria["relationship"] = relationship_criterion(contacts.get(inst.id, []))
            c.criteria["via_sgi"] = sgi.get(inst.id) or {"status": "unknown", "reason": "no_documented_sgi_deal"}
            candidates.append(c)

    if req.kind in ("all", "institutions"):
        ents = (await db.execute(
            select(Entity, Country.code).outerjoin(Country, Country.id == Entity.country_id)
            .where(Entity.deleted_at.is_(None), Entity.entity_type.in_(DIRECTORY_ENTITY_TYPES),
                   Entity.entity_class == "financial_institution")
        )).all()
        ids = [e.id for e, _ in ents]
        parts = await _participations(db, DealParticipant.entity_id, ids)
        contacts = await _contacts(db, MandateCounterparty.entity_id, ids)
        for ent, cc in ents:
            c = Candidate(kind="institution", id=ent.id, name=ent.canonical_name, country_code=cc,
                          entity_type=ent.entity_type, website=ent.website)
            rows = parts.get(ent.id, [])
            if req.country:
                in_country = any(dcc == req.country for _, _, dcc in rows)
                c.criteria["presence"] = {"status": "met", "basis": "deal_in_country"} if in_country else \
                    {"status": "unknown", "reason": "no_deal_recorded_in_country"}
            else:
                c.criteria["presence"] = {"status": "unknown", "reason": "country_not_given"}
            c.criteria["experience"] = experience_criterion(rows, req)
            c.criteria["capacity"] = {"status": "unknown", "reason": "not_applicable_institution"}
            c.criteria["relationship"] = relationship_criterion(contacts.get(ent.id, []))
            candidates.append(c)

    candidates.sort(key=lambda c: (-c.met, -c.comparable_deals, c.name.upper()))
    return candidates
