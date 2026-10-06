"""UMOA Banking Intelligence — Deal Intelligence service (Phase 13).

Read side (explorer, detail, descriptive analytics) and the human decisions of the
Review Center (review / verify / reject, duplicate-candidate decisions).

Reused, not duplicated:
  - transitions: scraping.financial_data.review (can_review / can_verify / can_reject,
    check_expected_state, StaleStateError, ObservationNotFoundError);
  - audit: financial_data_review_events (single journal, event in the same transaction);
  - locking: SELECT ... FOR UPDATE on the rows being decided.
Nothing is converted between currencies or units; NULL stays NULL.
"""
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import extract, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.deals import SECONDARY_SOURCE_CLASSES
from app.models.country import Country
from app.models.deal import Deal, DealDuplicateCandidate, DealParticipant, DealSource
from app.models.review_event import FinancialDataReviewEvent
from app.schemas.common import PaginatedResponse
from app.schemas.data_quality import ReviewEventRead
from app.schemas.deal import (
    CurrencyTotal,
    DealAnalytics,
    DealAnalyticsRow,
    DealDetail,
    DealDuplicateRead,
    DealListItem,
    DealParticipantRead,
    DealSourceRead,
    MergedDealRead,
)
from scraping.financial_data.review import (
    InvalidTransitionError,
    ObservationNotFoundError,
    StaleStateError,
    can_reject,
    can_review,
    can_verify,
    check_expected_state,
)

ANALYTICS_DIMENSIONS = ("country", "year", "type", "sector", "institution")
AMOUNT_STATUSES = ("reviewed", "verified")


class DealNotFoundError(ObservationNotFoundError):
    pass


class UnresolvedDuplicateError(StaleStateError):
    """Verification refused while a duplicate candidate involving the deal is undecided."""


class SecondarySourceOnlyError(StaleStateError):
    """Verification refused while the deal is attested only by press / AMF index sources (D4)."""


async def _secondary_only(db: AsyncSession, deal_id: str) -> bool:
    """True when every classified source of the deal is secondary (press_reported / regulator_index).

    Legacy sources (class NULL, before Phase 19) keep the previous behaviour.
    """
    classes = set(
        (await db.execute(select(DealSource.source_class).where(DealSource.deal_id == deal_id))).scalars()
    )
    return bool(classes) and None not in classes and classes <= set(SECONDARY_SOURCE_CLASSES)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _deal_year():
    """Year of a deal: signing date, otherwise announcement date, otherwise value date (documented rule)."""
    return extract("year", func.coalesce(Deal.signing_date, Deal.announcement_date, Deal.value_date))


def _participant_filter(*, institution_id: str | None = None, name: str | None = None,
                        roles: tuple[str, ...] | None = None):
    q = select(DealParticipant.deal_id).where(DealParticipant.deleted_at.is_(None))
    if roles:
        q = q.where(DealParticipant.role.in_(roles))
    if institution_id:
        q = q.where(DealParticipant.institution_id == institution_id)
    if name:
        q = q.where(DealParticipant.participant_name.ilike(f"%{_escape_like(name)}%", escape="\\"))
    return Deal.id.in_(q)


def _party(value: str | None, roles: tuple[str, ...]):
    """A filter value is an institution id when it matches one, otherwise a name fragment."""
    if not value:
        return None
    return or_(
        _participant_filter(institution_id=value, roles=roles),
        _participant_filter(name=value, roles=roles),
    )


def _list_query(
    *,
    country: str | None = None,
    bank: str | None = None,
    deal_type: str | None = None,
    sector: str | None = None,
    year: int | None = None,
    currency: str | None = None,
    status: str | None = None,
    participant_role: str | None = None,
    borrower: str | None = None,
    arranger: str | None = None,
    include_merged: bool = False,
):
    conds: list[Any] = [Deal.deleted_at.is_(None)]
    if not include_merged:
        conds.append(Deal.merged_into_deal_id.is_(None))
    if country:
        conds.append(Deal.country_id.in_(select(Country.id).where(Country.code == country)))
    if bank or participant_role:
        # Same participant row: "bank X acting as <role>" when both are given.
        conds.append(_participant_filter(institution_id=bank,
                                         roles=(participant_role,) if participant_role else None))
    if deal_type:
        conds.append(Deal.deal_type == deal_type)
    if sector:
        conds.append(Deal.sector == sector)
    if year is not None:
        conds.append(_deal_year() == year)
    if currency:
        conds.append(Deal.currency == currency)
    if status:
        conds.append(Deal.status == status)
    for value, roles in ((borrower, ("borrower",)), (arranger, ("arranger",))):
        cond = _party(value, roles)
        if cond is not None:
            conds.append(cond)
    return conds


async def _open_candidates(db: AsyncSession, deal_ids: list[str]) -> dict[str, int]:
    if not deal_ids:
        return {}
    rows = (
        await db.execute(
            select(DealDuplicateCandidate.deal_a_id, DealDuplicateCandidate.deal_b_id).where(
                DealDuplicateCandidate.state == "duplicate_candidate",
                or_(DealDuplicateCandidate.deal_a_id.in_(deal_ids), DealDuplicateCandidate.deal_b_id.in_(deal_ids)),
            )
        )
    ).all()
    counts: dict[str, int] = defaultdict(int)
    for a, b in rows:
        counts[a] += 1
        counts[b] += 1
    return counts


def _names(deal: Deal, role: str) -> list[str]:
    return [p.participant_name for p in deal.participants if p.role == role]


def _list_item(deal: Deal, open_candidates: dict[str, int]) -> DealListItem:
    return DealListItem(
        id=deal.id, title=deal.title, deal_type=deal.deal_type, status=deal.status,
        country_code=deal.country.code if deal.country else None, sector=deal.sector,
        project_name=deal.project_name, amount=deal.amount, currency=deal.currency, unit=deal.unit,
        announcement_date=deal.announcement_date, signing_date=deal.signing_date,
        borrowers=_names(deal, "borrower"), arrangers=_names(deal, "arranger"), issuers=_names(deal, "issuer"),
        instrument_type=deal.instrument_type, isin=deal.isin, value_date=deal.value_date,
        duplicate_candidates=open_candidates.get(deal.id, 0), merged_into_deal_id=deal.merged_into_deal_id,
        updated_at=deal.updated_at,
    )


async def list_deals(db: AsyncSession, *, page: int, page_size: int, **filters: Any
                     ) -> PaginatedResponse[DealListItem]:
    conds = _list_query(**filters)
    total = (await db.execute(select(func.count(Deal.id)).where(*conds))).scalar_one()
    rows = (
        await db.execute(
            select(Deal)
            .options(selectinload(Deal.participants), selectinload(Deal.country))
            .where(*conds)
            .order_by(func.coalesce(Deal.signing_date, Deal.announcement_date, Deal.value_date).desc().nulls_last(),
                      Deal.title, Deal.id)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    open_c = await _open_candidates(db, [d.id for d in rows])
    return PaginatedResponse(
        items=[_list_item(d, open_c) for d in rows], total=total, page=page, page_size=page_size,
        has_next=page * page_size < total, has_prev=page > 1,
    )


def _source_read(s: DealSource, fields: list[str]) -> DealSourceRead:
    return DealSourceRead(
        id=s.id, deal_id=s.deal_id, document_id=s.document_id,
        document_title=s.document.title if s.document else None,
        document_url=s.document.url if s.document else None,
        source_id=s.source_id, source_name=s.source.name if s.source else None,
        page_number=s.page_number, excerpt=s.excerpt, fields=fields, source_class=s.source_class,
        publisher=s.publisher, title=s.title, url=s.url, published_at=s.published_at, paywalled=s.paywalled,
    )


def _participant_read(p: DealParticipant) -> DealParticipantRead:
    return DealParticipantRead(
        id=p.id, participant_name=p.participant_name, institution_id=p.institution_id,
        institution_name=p.institution.name_official if p.institution else None,
        entity_id=p.entity_id, entity_name=p.entity.canonical_name if p.entity else None, role=p.role,
        commitment_amount=p.commitment_amount, commitment_currency=p.commitment_currency,
        deal_source_id=p.deal_source_id, page_number=p.page_number, excerpt=p.excerpt,
        extraction_method=p.extraction_method,
    )


def _deal_options():
    return (
        selectinload(Deal.participants).selectinload(DealParticipant.institution),
        selectinload(Deal.participants).selectinload(DealParticipant.entity),
        selectinload(Deal.sources).selectinload(DealSource.document),
        selectinload(Deal.sources).selectinload(DealSource.source),
        selectinload(Deal.field_sources),
        selectinload(Deal.country),
    )


def _deal_actions(deal: Deal, open_candidates: int) -> list[str]:
    # The deal title plays the role of the "value" required by the shared review guard.
    actions = []
    if can_review(deal.status, deal.title):
        actions.append("review")
    if can_verify(deal.status, deal.title) and open_candidates == 0:
        actions.append("verify")
    if can_reject(deal.status):
        actions.append("reject")
    return actions


async def get_deal(db: AsyncSession, deal_id: str) -> DealDetail | None:
    deal = (
        await db.execute(select(Deal).options(*_deal_options()).where(Deal.id == deal_id, Deal.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if deal is None:
        return None

    by_source: dict[str, list[str]] = defaultdict(list)
    provenance: dict[str, list[str]] = defaultdict(list)
    for fs in deal.field_sources:
        by_source[fs.deal_source_id].append(fs.field_name)
        provenance[fs.field_name].append(fs.deal_source_id)

    candidates = (
        await db.execute(
            select(DealDuplicateCandidate).where(
                or_(DealDuplicateCandidate.deal_a_id == deal.id, DealDuplicateCandidate.deal_b_id == deal.id)
            ).order_by(DealDuplicateCandidate.created_at)
        )
    ).scalars().all()
    # Columns only: loading full Deal objects here would pin them in the identity map with
    # empty (noload) relationships and hide the sources of attached deals below.
    others = {
        row.id: row
        for row in (
            await db.execute(select(Deal.id, Deal.title, Deal.status).where(Deal.id.in_(
                [c.deal_b_id if c.deal_a_id == deal.id else c.deal_a_id for c in candidates]
            )))
        ).all()
    } if candidates else {}
    duplicates = []
    for c in candidates:
        other_id = c.deal_b_id if c.deal_a_id == deal.id else c.deal_a_id
        other = others.get(other_id)
        duplicates.append(DealDuplicateRead(
            id=c.id, other_deal_id=other_id, other_deal_title=other.title if other else None,
            other_deal_status=other.status if other else None, matched_criteria=list(c.matched_criteria),
            state=c.state, primary_deal_id=c.primary_deal_id, decided_by=c.decided_by,
            decided_at=c.decided_at, decision_reason=c.decision_reason,
        ))
    open_count = sum(1 for c in candidates if c.state == "duplicate_candidate")

    merged = (
        await db.execute(
            select(Deal).options(*_deal_options()).where(Deal.merged_into_deal_id == deal.id, Deal.deleted_at.is_(None))
        )
    ).scalars().all()
    merged_reads = []
    for m in merged:
        m_fields: dict[str, list[str]] = defaultdict(list)
        for fs in m.field_sources:
            m_fields[fs.deal_source_id].append(fs.field_name)
        merged_reads.append(MergedDealRead(
            id=m.id, title=m.title, status=m.status,
            sources=[_source_read(s, sorted(m_fields[s.id])) for s in m.sources],
            participants=[_participant_read(p) for p in m.participants],
        ))

    base = _list_item(deal, {deal.id: open_count}).model_dump()
    return DealDetail(
        **base,
        amount_original=deal.amount_original, interest_rate=deal.interest_rate,
        interest_rate_type=deal.interest_rate_type, benchmark=deal.benchmark, spread_bps=deal.spread_bps,
        maturity_months=deal.maturity_months, grace_period_months=deal.grace_period_months, fees=deal.fees,
        guarantees=deal.guarantees, financial_close_date=deal.financial_close_date,
        closing_date=deal.closing_date, auction_reference=deal.auction_reference, auction_date=deal.auction_date,
        maturity_date=deal.maturity_date, yield_rate=deal.yield_rate,
        validation_flags=list(deal.validation_flags or []), use_of_proceeds=deal.use_of_proceeds,
        use_of_proceeds_categories=list(deal.use_of_proceeds_categories or []),
        filing_agent_raw=deal.filing_agent_raw, notes=deal.notes, verified_at=deal.verified_at,
        verified_by=deal.verified_by, created_at=deal.created_at,
        participants=[_participant_read(p) for p in deal.participants],
        sources=[_source_read(s, sorted(by_source[s.id])) for s in deal.sources],
        field_provenance=dict(provenance), duplicates=duplicates, merged_deals=merged_reads,
        allowed_actions=_deal_actions(deal, open_count),
    )


async def get_deal_history(db: AsyncSession, deal_id: str) -> list[ReviewEventRead]:
    rows = (
        await db.execute(
            select(FinancialDataReviewEvent)
            .where(FinancialDataReviewEvent.deal_id == deal_id)
            .order_by(FinancialDataReviewEvent.created_at, FinancialDataReviewEvent.id)
        )
    ).scalars().all()
    return [ReviewEventRead.model_validate(r) for r in rows]


# --------------------------------------------------------------------------- decisions


async def _lock_deal(db: AsyncSession, deal_id: str) -> Deal:
    deal = (
        await db.execute(select(Deal).where(Deal.id == deal_id, Deal.deleted_at.is_(None)).with_for_update(of=Deal))
    ).scalar_one_or_none()
    if deal is None:
        raise DealNotFoundError(f"Deal '{deal_id}' not found")
    return deal


def _event(deal: Deal, *, action: str, previous_status: str, reason: str | None, actor: str,
           value_before: Decimal | None, candidate_id: str | None = None) -> FinancialDataReviewEvent:
    return FinancialDataReviewEvent(
        deal_id=deal.id, deal_duplicate_candidate_id=candidate_id, action=action,
        previous_status=previous_status, new_status=deal.status, reason=reason, actor=actor,
        value_before=value_before, value_after=deal.amount,
    )


def _append_note(deal: Deal, label: str, text: str) -> None:
    deal.notes = f"{deal.notes} | {label}: {text}" if deal.notes else f"{label}: {text}"


async def decide_deal(
    db: AsyncSession,
    deal_id: str,
    action: str,
    *,
    actor: str,
    reason: str,
    expected_status: str | None = None,
    expected_updated_at: datetime | None = None,
) -> DealDetail:
    """review / verify / reject a deal: row lock, stale-state check, audit event, one commit."""
    if not actor or not actor.strip():
        raise ValueError("actor is required")
    if not reason or not reason.strip():
        raise ValueError("reason is required")
    actor, reason = actor.strip(), reason.strip()
    deal = await _lock_deal(db, deal_id)
    check_expected_state(deal, expected_status, expected_updated_at)
    previous_status, value_before = deal.status, deal.amount
    now = datetime.now(UTC)

    if action == "review":
        if not can_review(deal.status, deal.title):
            raise InvalidTransitionError(f"Cannot review a deal in status '{deal.status}'")
        deal.status = "reviewed"
        _append_note(deal, "Review", reason)
    elif action == "verify":
        if not can_verify(deal.status, deal.title):
            raise InvalidTransitionError(
                f"Direct verification from status '{deal.status}' is forbidden; the deal must be 'reviewed' first"
            )
        open_c = (await _open_candidates(db, [deal.id])).get(deal.id, 0)
        if open_c:
            raise UnresolvedDuplicateError(
                "unresolved_duplicate_candidate: decide the duplicate candidate(s) before verifying"
            )
        if await _secondary_only(db, deal.id):
            raise SecondarySourceOnlyError(
                "secondary_source_only: add a primary source (note, release, UMOA-Titres / BRVM notice) "
                "before verifying a deal attested only by the press or the AMF index"
            )
        deal.status = "verified"
        deal.verified_by = actor
        deal.verified_at = now
        _append_note(deal, "Verification", reason)
    elif action == "reject":
        if not can_reject(deal.status):
            raise InvalidTransitionError("Deal is already 'rejected'")
        deal.status = "rejected"
        _append_note(deal, "Rejection", reason)
    else:
        raise InvalidTransitionError(f"Unknown action '{action}'")

    deal.updated_at = now
    db.add(_event(deal, action=action, previous_status=previous_status, reason=reason, actor=actor,
                  value_before=value_before))
    await db.commit()
    return await get_deal(db, deal_id)  # type: ignore[return-value]


DECISION_ACTIONS = {
    "same_deal": "mark_same_deal",
    "distinct_deals": "mark_distinct",
    "same_deal_multi_source": "mark_same_deal_multi_source",
}


async def decide_duplicate(
    db: AsyncSession,
    candidate_id: str,
    *,
    decision: str,
    actor: str,
    reason: str,
    primary_deal_id: str | None = None,
    expected_state: str | None = "duplicate_candidate",
) -> DealDuplicateRead:
    """Human decision on a duplicate candidate. Never deletes anything.

    same_deal / same_deal_multi_source: the secondary deal is attached to the primary one
    (merged_into_deal_id); its sources, participants and history stay intact and visible.
    """
    if decision not in DECISION_ACTIONS:
        raise InvalidTransitionError(f"Unknown decision '{decision}'")
    actor, reason = actor.strip(), reason.strip()
    candidate = (
        await db.execute(
            select(DealDuplicateCandidate).where(DealDuplicateCandidate.id == candidate_id).with_for_update()
        )
    ).scalar_one_or_none()
    if candidate is None:
        raise ObservationNotFoundError(f"Duplicate candidate '{candidate_id}' not found")
    if expected_state is not None and candidate.state != expected_state:
        raise StaleStateError(f"Candidate state is now '{candidate.state}' (expected '{expected_state}')")
    if candidate.state != "duplicate_candidate":
        raise StaleStateError("This candidate has already been decided")

    # Lock both deals in a stable order (deal_a_id < deal_b_id by constraint).
    deal_a = await _lock_deal(db, candidate.deal_a_id)
    deal_b = await _lock_deal(db, candidate.deal_b_id)

    now = datetime.now(UTC)
    if decision == "distinct_deals":
        if primary_deal_id is not None:
            raise ValueError("primary_deal_id is only used when the deals are the same")
    else:
        if primary_deal_id not in (deal_a.id, deal_b.id):
            raise ValueError("primary_deal_id must be one of the two deals of the candidate")
        primary, secondary = (deal_a, deal_b) if primary_deal_id == deal_a.id else (deal_b, deal_a)
        if primary.merged_into_deal_id is not None:
            raise InvalidTransitionError("The primary deal is itself attached to another deal")
        if secondary.merged_into_deal_id is not None:
            raise InvalidTransitionError("The secondary deal is already attached to another deal")
        secondary.merged_into_deal_id = primary.id
        secondary.updated_at = now
        candidate.primary_deal_id = primary.id

    candidate.state = decision
    candidate.decided_by = actor
    candidate.decided_at = now
    candidate.decision_reason = reason
    candidate.updated_at = now
    for deal in (deal_a, deal_b):
        db.add(_event(deal, action=DECISION_ACTIONS[decision], previous_status=deal.status, reason=reason,
                      actor=actor, value_before=deal.amount, candidate_id=candidate.id))
    await db.commit()
    return DealDuplicateRead(
        id=candidate.id, other_deal_id=candidate.deal_b_id, other_deal_title=deal_b.title,
        other_deal_status=deal_b.status, matched_criteria=list(candidate.matched_criteria), state=candidate.state,
        primary_deal_id=candidate.primary_deal_id, decided_by=candidate.decided_by,
        decided_at=candidate.decided_at, decision_reason=candidate.decision_reason,
    )


async def list_open_duplicates(db: AsyncSession, *, page: int, page_size: int
                               ) -> PaginatedResponse[DealDuplicateRead]:
    where = DealDuplicateCandidate.state == "duplicate_candidate"
    total = (await db.execute(select(func.count(DealDuplicateCandidate.id)).where(where))).scalar_one()
    rows = (
        await db.execute(
            select(DealDuplicateCandidate).where(where).order_by(DealDuplicateCandidate.created_at)
            .offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()
    titles = dict(
        (await db.execute(select(Deal.id, Deal.title).where(Deal.id.in_([r.deal_b_id for r in rows])))).all()
    ) if rows else {}
    return PaginatedResponse(
        items=[
            DealDuplicateRead(id=c.id, other_deal_id=c.deal_b_id, other_deal_title=titles.get(c.deal_b_id),
                              matched_criteria=list(c.matched_criteria), state=c.state)
            for c in rows
        ],
        total=total, page=page, page_size=page_size, has_next=page * page_size < total, has_prev=page > 1,
    )


async def deal_counts(db: AsyncSession) -> dict[str, int]:
    rows = dict(
        (
            await db.execute(
                select(Deal.status, func.count(Deal.id))
                .where(Deal.deleted_at.is_(None), Deal.merged_into_deal_id.is_(None))
                .group_by(Deal.status)
            )
        ).all()
    )
    open_c = (
        await db.execute(
            select(func.count(DealDuplicateCandidate.id)).where(DealDuplicateCandidate.state == "duplicate_candidate")
        )
    ).scalar_one()
    return {
        "deals_total": sum(rows.values()),
        "deals_needs_review": rows.get("needs_review", 0),
        "deals_reviewed": rows.get("reviewed", 0),
        "deals_verified": rows.get("verified", 0),
        "deals_rejected": rows.get("rejected", 0),
        "deals_duplicate_candidates": open_c,
    }


# --------------------------------------------------------------------------- analytics (descriptive)


async def deal_analytics(db: AsyncSession, dimension: str) -> DealAnalytics:
    """Counts per dimension and amount totals per (currency, unit). Never a ranking or a score.

    Counted deals: not deleted, not attached to another deal, not rejected. Amount totals only
    use reviewed / verified deals with a published amount; currencies and units stay separate.
    """
    if dimension not in ANALYTICS_DIMENSIONS:
        raise ValueError(f"dimension must be one of {', '.join(ANALYTICS_DIMENSIONS)}")
    deals = (
        await db.execute(
            select(Deal)
            .options(selectinload(Deal.country), selectinload(Deal.participants).selectinload(DealParticipant.institution))
            .where(Deal.deleted_at.is_(None), Deal.merged_into_deal_id.is_(None), Deal.status != "rejected")
        )
    ).scalars().all()

    groups: dict[str | None, list[Deal]] = defaultdict(list)
    labels: dict[str | None, str | None] = {}
    for d in deals:
        if dimension == "institution":
            seen: set[str] = set()
            for p in d.participants:
                if p.institution_id and p.institution_id not in seen:
                    seen.add(p.institution_id)
                    groups[p.institution_id].append(d)
                    labels[p.institution_id] = p.institution.name_official if p.institution else None
            continue
        if dimension == "country":
            key = d.country.code if d.country else None
        elif dimension == "year":
            day = d.signing_date or d.announcement_date or d.value_date
            key = str(day.year) if day else None
        elif dimension == "type":
            key = d.deal_type
        else:
            key = d.sector
        groups[key].append(d)
        labels.setdefault(key, key)

    rows = []
    for key, items in groups.items():
        by_status: dict[str, int] = defaultdict(int)
        totals: dict[tuple[str, str | None], list[Decimal]] = defaultdict(list)
        without = 0
        for d in items:
            by_status[d.status] += 1
            if d.amount is None or d.currency is None:
                without += 1
            elif d.status in AMOUNT_STATUSES:
                totals[(d.currency, d.unit)].append(d.amount)
        rows.append(DealAnalyticsRow(
            key=key, label=labels.get(key), deals=len(items), by_status=dict(by_status),
            amounts=[CurrencyTotal(currency=c, unit=u, total=sum(v, Decimal(0)), deals=len(v))
                     for (c, u), v in sorted(totals.items(), key=lambda kv: (kv[0][0], kv[0][1] or ""))],
            deals_without_amount=without,
        ))
    # Descriptive order: by label (unknown last), never by amount.
    rows.sort(key=lambda r: (r.key is None, (r.label or r.key or "").casefold()))
    return DealAnalytics(dimension=dimension, rows=rows)

