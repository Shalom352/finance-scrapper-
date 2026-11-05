from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.deal import Deal, DealDuplicateCandidate
from app.models.financial_data import FinancialData
from app.models.review_event import FinancialDataReviewEvent
from scraping.deals.duplicates import (
    DealFacts,
    absolute_amount,
    bond_label,
    is_candidate,
    matched_criteria,
    normalize_name,
)

AUTO_DEDUPLICATOR = "auto-deduplicator:v1"
_STATUS_RANK = {"verified": 4, "reviewed": 3, "needs_review": 2, "extracted": 1, "rejected": 0}


@dataclass
class ObservationDeduplicationReport:
    groups: int = 0
    removed: int = 0


@dataclass
class DealDeduplicationReport:
    merged: int = 0
    closed_distinct: int = 0
    still_open: int = 0
    resolved_candidate_ids: set[str] = field(default_factory=set)
    resolved_deal_ids: set[str] = field(default_factory=set)

    def summary(self) -> dict:
        return {
            "merged_exact_duplicates": self.merged,
            "closed_false_candidates": self.closed_distinct,
            "ambiguous_candidates_left": self.still_open,
        }


def _observation_key(row: FinancialData) -> tuple:
    raw = re.sub(r"\s+", "", row.value_original or "").casefold()
    value = row.value_normalized if row.value_normalized is not None else raw
    return (
        row.document_id, row.institution_id, row.entity_id, row.observation_level, row.consolidation_scope,
        row.metric_code, row.period_year, row.period_type, row.period_label, row.scope, row.page_number,
        value, row.unit_normalized, row.currency_normalized,
    )


def _observation_preference(row: FinancialData) -> tuple:
    return (
        _STATUS_RANK.get(row.status, 0),
        row.validation_method == "human",
        Decimal(str(row.confidence_score or 0)),
        row.created_at,
        row.id,
    )


async def deduplicate_financial_observations(
    db: AsyncSession, *, dry_run: bool = False
) -> ObservationDeduplicationReport:
    """Soft-delete repeated facts from one document page; preserve independent corroboration."""
    rows = (await db.execute(
        select(FinancialData)
        .where(FinancialData.deleted_at.is_(None), FinancialData.page_number.is_not(None))
        .order_by(FinancialData.created_at, FinancialData.id)
    )).scalars().all()
    groups: dict[tuple, list[FinancialData]] = defaultdict(list)
    for row in rows:
        groups[_observation_key(row)].append(row)

    report = ObservationDeduplicationReport()
    now = datetime.now(UTC)
    for group in groups.values():
        candidates = [r for r in group if r.status != "rejected"]
        if len(candidates) < 2:
            continue
        report.groups += 1
        keep = max(candidates, key=_observation_preference)
        for duplicate in candidates:
            if duplicate.id == keep.id:
                continue
            report.removed += 1
            if dry_run:
                continue
            duplicate.deleted_at = now
            duplicate.updated_at = now
            note = f"Doublon exact supprimé automatiquement; observation conservée: {keep.id}."
            duplicate.notes = f"{duplicate.notes} | {note}" if duplicate.notes else note
            db.add(FinancialDataReviewEvent(
                financial_data_id=duplicate.id,
                action="auto_deduplicate",
                previous_status=duplicate.status,
                new_status=duplicate.status,
                reason=note,
                actor=AUTO_DEDUPLICATOR,
                value_before=duplicate.value_normalized,
                value_after=duplicate.value_normalized,
            ))
    if not dry_run and report.removed:
        await db.flush()
    return report


def _deal_facts(deal: Deal) -> DealFacts:
    return DealFacts(
        id=deal.id,
        deal_type=deal.deal_type,
        project_name=deal.project_name,
        amount=deal.amount,
        currency=deal.currency,
        unit=deal.unit,
        signing_date=deal.signing_date,
        announcement_date=deal.announcement_date,
        participants=[(p.role, p.institution_id, p.participant_name) for p in deal.participants],
        isin=deal.isin,
        value_date=deal.value_date,
        issuer_entities=frozenset(p.entity_id for p in deal.participants if p.role == "issuer" and p.entity_id),
        title=deal.title,
        auction_reference=deal.auction_reference,
        auction_date=deal.auction_date,
        maturity_date=deal.maturity_date,
        instrument_type=deal.instrument_type,
        country_id=deal.country_id,
        financial_close_date=deal.financial_close_date,
        closing_date=deal.closing_date,
        operation_key=deal.ingestion_key,
    )


def _same_published_amount(a: DealFacts, b: DealFacts) -> bool:
    va, vb = absolute_amount(a.amount, a.unit), absolute_amount(b.amount, b.unit)
    return (
        a.currency == b.currency
        and ((va is None and vb is None) or (va is not None and vb is not None and va == vb))
    )


def is_exact_duplicate_deal(a: DealFacts, b: DealFacts) -> bool:
    """Merge only operations with a complete identical key and matching published terms."""
    if (
        a.isin and b.isin and a.isin == b.isin
        and a.auction_reference and b.auction_reference and a.auction_reference == b.auction_reference
        and a.auction_date and b.auction_date and a.auction_date == b.auction_date
        and a.value_date and b.value_date and a.value_date == b.value_date
    ):
        return (
            a.deal_type == b.deal_type
            and a.instrument_type == b.instrument_type
            and a.maturity_date == b.maturity_date
            and a.country_id == b.country_id
            and _same_published_amount(a, b)
        )

    borrowers_match = bool(a.keys(borrower=True) & b.keys(borrower=True))
    project_a, project_b = normalize_name(a.project_name), normalize_name(b.project_name)
    same_event_date = any(
        left is not None and left == right
        for left, right in (
            (a.signing_date, b.signing_date),
            (a.financial_close_date, b.financial_close_date),
            (a.closing_date, b.closing_date),
        )
    )
    aa, ab = absolute_amount(a.amount, a.unit), absolute_amount(b.amount, b.unit)
    return bool(
        borrowers_match and project_a and project_a == project_b and same_event_date
        and a.country_id and a.country_id == b.country_id
        and a.deal_type and a.deal_type == b.deal_type
        and a.currency and a.currency == b.currency
        and aa is not None and aa == ab
    )


def _known_distinct_reason(a: DealFacts, b: DealFacts) -> str:
    if (
        a.operation_key and b.operation_key
        and a.operation_key.startswith("amf-umoa:operation:")
        and b.operation_key.startswith("amf-umoa:operation:")
        and a.operation_key != b.operation_key
    ):
        return "Opérations distinctes : les identifiants d’opération officiels de l’AMF sont différents."
    if (
        a.isin and a.isin == b.isin and a.value_date and a.value_date == b.value_date
        and a.auction_reference and b.auction_reference and a.auction_reference != b.auction_reference
    ):
        return "Opérations distinctes : même ISIN et date de valeur, mais références d’adjudication différentes."
    la, lb = bond_label(a.title), bond_label(b.title)
    if la and lb and (la.coupon != lb.coupon or la.years != lb.years):
        return "Opérations distinctes : le coupon ou l’échéance du titre obligataire diffère."
    return "Le recalcul des critères stricts ne confirme pas qu’il s’agit de la même opération."


def _preferred_deal(a: Deal, b: Deal) -> tuple[Deal, Deal]:
    def rank(deal: Deal) -> tuple:
        return (-_STATUS_RANK.get(deal.status, 0), -(deal.validation_method == "human"), deal.created_at, deal.id)
    return (a, b) if rank(a) <= rank(b) else (b, a)


async def reconcile_deal_duplicates(
    db: AsyncSession, *, dry_run: bool = False
) -> DealDeduplicationReport:
    """Merge only exact repeated operations and close stale false positives with an audit trail."""
    report = DealDeduplicationReport()
    candidates = (await db.execute(
        select(DealDuplicateCandidate)
        .where(DealDuplicateCandidate.state == "duplicate_candidate")
        .order_by(DealDuplicateCandidate.created_at, DealDuplicateCandidate.id)
    )).scalars().all()
    if not candidates:
        return report

    ids = {deal_id for candidate in candidates for deal_id in (candidate.deal_a_id, candidate.deal_b_id)}
    deals = (await db.execute(
        select(Deal).options(selectinload(Deal.participants))
        .where(Deal.id.in_(ids), Deal.deleted_at.is_(None))
        .with_for_update(of=Deal)
    )).scalars().all()
    by_id = {deal.id: deal for deal in deals}
    now = datetime.now(UTC)

    for candidate in candidates:
        a, b = by_id.get(candidate.deal_a_id), by_id.get(candidate.deal_b_id)
        if a is None or b is None:
            continue
        fa, fb = _deal_facts(a), _deal_facts(b)
        criteria = matched_criteria(fa, fb)
        if is_candidate(criteria) and is_exact_duplicate_deal(fa, fb) and a.status != "rejected" and b.status != "rejected":
            primary, secondary = _preferred_deal(a, b)
            state = "same_deal_multi_source"
            reason = "Doublon exact fusionné automatiquement : identifiant d’opération, dates, devise et montant concordent."
            candidate.primary_deal_id = primary.id
            secondary.merged_into_deal_id = primary.id
            secondary.updated_at = now
            report.merged += 1
            action = "mark_same_deal_multi_source"
        elif not is_candidate(criteria):
            state = "distinct_deals"
            reason = _known_distinct_reason(fa, fb)
            candidate.primary_deal_id = None
            report.closed_distinct += 1
            action = "mark_distinct"
        else:
            candidate.matched_criteria = criteria
            report.still_open += 1
            continue

        report.resolved_candidate_ids.add(candidate.id)
        report.resolved_deal_ids.update((a.id, b.id))
        if dry_run:
            continue
        candidate.state = state
        candidate.decided_by = AUTO_DEDUPLICATOR
        candidate.decided_at = now
        candidate.decision_reason = reason
        candidate.updated_at = now
        for deal in (a, b):
            db.add(FinancialDataReviewEvent(
                deal_id=deal.id,
                deal_duplicate_candidate_id=candidate.id,
                action=action,
                previous_status=deal.status,
                new_status=deal.status,
                reason=reason,
                actor=AUTO_DEDUPLICATOR,
                value_before=deal.amount,
                value_after=deal.amount,
            ))

    if not dry_run and report.resolved_candidate_ids:
        await db.flush()
    return report
