"""UMOA Banking Intelligence — Financial Data Service

Query logic for financial data.
"""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import distinct, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import raiseload, selectinload

from app.models.country import Country
from app.models.document import Document
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.review_event import FinancialDataReviewEvent
from app.models.source import Source
from app.schemas.common import PaginatedResponse
from app.schemas.financial_data import (
    ConflictRecordResponse,
    DataQualitySummary,
    DuplicateGroupResponse,
    FinancialDataExplorerItem,
    FinancialDataFacets,
    FinancialDataRead,
    HistoricalQualityResponse,
    InstitutionCoverageResponse,
    ObservationResponse,
    QualityDimensionResponse,
)
from scraping.consolidation import FinancialDataConsolidator
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.financial_data.export import EXPORT_MAX_ROWS, ExportTooLargeError, build_csv
from scraping.financial_data.qualification import qualify_rows
from scraping.financial_data.review import (
    InvalidTransitionError,
    ObservationNotFoundError,
    can_reject,
    can_review,
    can_verify,
    check_expected_state,
)

# Sortable explorer columns (backend sort only; never a currency conversion).
EXPLORER_SORTS = ("institution", "country", "indicator", "year", "value")


def _explorer_query(
    *,
    institution_id: str | None = None,
    institution_ids: list[str] | None = None,
    country_code: str | None = None,
    metric_code: str | None = None,
    period_type: str | None = None,
    period_year: int | None = None,
    scope: str | None = None,
    status: str | None = None,
    currency_normalized: str | None = None,
    include_rejected: bool = True,
    attention_ids: set[str] | None = None,
):
    """Filtered observations joined with names and document title in ONE query
    (no N+1, no full document rows)."""
    query = (
        select(FinancialData, Institution.name_official, Country.code, Source.name, Document.title)
        .join(Institution, FinancialData.institution_id == Institution.id)
        .outerjoin(Country, Institution.country_id == Country.id)
        .outerjoin(Source, FinancialData.source_id == Source.id)
        .outerjoin(Document, FinancialData.document_id == Document.id)
        # Only the columns selected above: the model's default joined relationships
        # (full document, source, metric rows) are never loaded for the list.
        .options(raiseload("*"))
        .where(FinancialData.deleted_at.is_(None))
    )
    ids = [i for i in (institution_ids or []) if i]
    if institution_id:
        ids.append(institution_id)
    if ids:
        query = query.where(FinancialData.institution_id.in_(ids))
    if country_code:
        query = query.where(Country.code == country_code.upper())
    if metric_code:
        query = query.where(FinancialData.metric_code == metric_code)
    if period_type:
        query = query.where(FinancialData.period_type == period_type)
    if period_year is not None:
        query = query.where(FinancialData.period_year == period_year)
    if scope:
        query = query.where(FinancialData.scope == scope)
    if status:
        query = query.where(FinancialData.status == status)
    elif attention_ids is not None:
        # Review queue: observations needing a human decision.
        query = query.where(or_(FinancialData.status == "needs_review", FinancialData.id.in_(attention_ids)))
    elif not include_rejected:
        query = query.where(FinancialData.status != "rejected")
    if currency_normalized:
        query = query.where(FinancialData.currency_normalized == currency_normalized)
    return query


def _order(query, sort: str | None, order: str):
    """Deterministic ordering. A value sort is grouped by currency first, so values of
    different currencies are never interleaved as if comparable; id breaks every tie."""
    desc = order == "desc"

    def d(col):
        return col.desc().nulls_last() if desc else col.asc().nulls_last()

    if sort == "institution":
        cols = [d(Institution.name_official), FinancialData.metric_code, FinancialData.period_year.desc()]
    elif sort == "country":
        cols = [d(Country.code), Institution.name_official, FinancialData.metric_code]
    elif sort == "indicator":
        cols = [d(FinancialData.metric_code), Institution.name_official, FinancialData.period_year.desc()]
    elif sort == "year":
        cols = [d(FinancialData.period_year), Institution.name_official, FinancialData.metric_code]
    elif sort == "value":
        cols = [FinancialData.currency_normalized.asc().nulls_last(), d(FinancialData.value_normalized)]
    else:
        cols = [FinancialData.period_year.desc(), FinancialData.metric_code]
    return query.order_by(*cols, FinancialData.id)


LOGICAL_KEY = (
    FinancialData.institution_id,
    FinancialData.metric_code,
    FinancialData.period_year,
    FinancialData.period_type,
    FinancialData.scope,
)


async def load_observations(db: AsyncSession, *conditions: Any) -> list:
    """Stored (non-deleted) observations matching `conditions`, as ObservationSummary, loading
    exactly what the authority rule reads (source priority / name / type, document title)."""
    query = (
        select(FinancialData)
        .options(
            raiseload("*"),
            selectinload(FinancialData.source)
            .load_only(Source.id, Source.name, Source.source_type, Source.priority)
            .raiseload("*"),
            selectinload(FinancialData.document).load_only(Document.id, Document.title).raiseload("*"),
        )
        .where(FinancialData.deleted_at.is_(None), *conditions)
    )
    rows = (await db.execute(query)).scalars().all()
    detector = DuplicateDetector()
    return [detector.observation_from_orm(r) for r in rows]


async def key_observations(db: AsyncSession, keys) -> list:
    """Every stored observation of the given logical keys."""
    keys = list(keys)
    return await load_observations(db, tuple_(*LOGICAL_KEY).in_(keys)) if keys else []


async def _qualify_page(db: AsyncSession, rows: list[FinancialData]) -> dict[str, tuple[str, str | None]]:
    """Qualification of the page rows, decided over ALL observations of their logical keys."""
    if not rows:
        return {}
    keys = {(r.institution_id, r.metric_code, r.period_year, r.period_type, r.scope) for r in rows}
    obs = await key_observations(db, keys)
    page_ids = {r.id for r in rows}
    return qualify_rows([o for o in obs if o.id in page_ids], obs)


async def conflict_observations(db: AsyncSession, **dims: Any) -> list:
    """Observations whose logical key is in conflict according to the EXISTING authority rule.

    SQL only narrows the candidates (keys with >= 2 non-rejected valued rows and no verified
    row); the decision itself is qualify_rows -> qualify_metric -> EligibilityEngine.
    """
    candidates = (
        _explorer_query(**dims, include_rejected=False)
        .with_only_columns(*LOGICAL_KEY)
        .where(FinancialData.value_normalized.is_not(None))
        .group_by(*LOGICAL_KEY)
        .having(func.count() >= 2, func.count().filter(FinancialData.status == "verified") == 0)
    )
    keys = [tuple(k) for k in (await db.execute(candidates)).all()]
    obs = await key_observations(db, keys)
    qual = qualify_rows(obs, obs)
    return [o for o in obs if qual.get(o.id, (None,))[0] == "conflict"]


async def conflict_observation_ids(db: AsyncSession, **dims: Any) -> set[str]:
    return {o.id for o in await conflict_observations(db, **dims)}


def _to_item(row, inst_name, country, source_name, doc_title, qual) -> FinancialDataExplorerItem:
    qualification, authoritative_id = qual.get(row.id, (None, None))
    return FinancialDataExplorerItem.model_validate(row).model_copy(
        update={
            "institution_name": inst_name,
            "country_code": country,
            "source_id": row.source_id,
            "source_name": source_name,
            "document_id": row.document_id,
            "document_title": doc_title,
            "page_number": row.page_number,
            "qualification": qualification,
            "authoritative_data_id": authoritative_id,
        }
    )


async def get_financial_data(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    institution_ids: list[str] | None = None,
    country_code: str | None = None,
    metric_code: str | None = None,
    period_type: str | None = None,
    period_year: int | None = None,
    scope: str | None = None,
    status: str | None = None,
    currency_normalized: str | None = None,
    include_rejected: bool = True,
    sort: str | None = None,
    order: str = "asc",
    attention_only: bool = False,
) -> PaginatedResponse[FinancialDataExplorerItem]:
    dims = dict(
        institution_id=institution_id, institution_ids=institution_ids, country_code=country_code,
        metric_code=metric_code, period_type=period_type, period_year=period_year, scope=scope,
    )
    attention_ids = await conflict_observation_ids(db, **dims) if attention_only and not status else None
    query = _explorer_query(
        **dims, status=status, currency_normalized=currency_normalized, include_rejected=include_rejected,
        attention_ids=attention_ids,
    )
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    result = (await db.execute(_order(query, sort, order).offset(offset).limit(page_size))).all()
    qual = await _qualify_page(db, [r[0] for r in result])

    return PaginatedResponse(
        items=[_to_item(*r, qual) for r in result],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def export_financial_data_csv(
    db: AsyncSession,
    *,
    sort: str | None = None,
    order: str = "asc",
    **filters: Any,
) -> str:
    """CSV of exactly the filtered rows; refused above EXPORT_MAX_ROWS (refine the filters)."""
    query = _explorer_query(**filters)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    if total > EXPORT_MAX_ROWS:
        raise ExportTooLargeError(total)
    result = (await db.execute(_order(query, sort, order))).all()
    qual = await _qualify_page(db, [r[0] for r in result])
    return build_csv(_to_item(*r, qual) for r in result)


async def get_financial_data_facets(db: AsyncSession) -> FinancialDataFacets:
    """Distinct values really stored (non-deleted rows) — nothing is listed that does not exist."""
    base = FinancialData.deleted_at.is_(None)

    async def values(col) -> list:
        return [v for v in (await db.execute(select(distinct(col)).where(base))).scalars().all() if v is not None]

    return FinancialDataFacets(
        period_years=sorted(await values(FinancialData.period_year), reverse=True),
        period_types=sorted(await values(FinancialData.period_type)),
        scopes=sorted(await values(FinancialData.scope)),
        currencies=sorted(await values(FinancialData.currency_normalized)),
        statuses=sorted(await values(FinancialData.status)),
        metric_codes=sorted(await values(FinancialData.metric_code)),
    )


async def get_financial_data_by_id(db: AsyncSession, data_id: str) -> FinancialDataRead | None:
    result = await db.execute(
        select(FinancialData)
        .options(
            selectinload(FinancialData.institution),
            selectinload(FinancialData.source),
            selectinload(FinancialData.document),
            selectinload(FinancialData.metric),
        )
        .where(FinancialData.id == data_id, FinancialData.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return FinancialDataRead.model_validate(row) if row else None


async def _load_for_decision(
    db: AsyncSession,
    data_id: str,
    expected_status: str | None,
    expected_updated_at: datetime | None,
) -> FinancialData:
    """Load the observation locked for the decision (SELECT ... FOR UPDATE on financial_data
    only) and refuse a decision taken on a stale view (optimistic concurrency)."""
    result = await db.execute(
        select(FinancialData)
        .where(FinancialData.id == data_id, FinancialData.deleted_at.is_(None))
        .with_for_update(of=FinancialData)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ObservationNotFoundError(f"FinancialData '{data_id}' not found")
    check_expected_state(row, expected_status, expected_updated_at)
    return row


def _record_event(
    db: AsyncSession,
    row: FinancialData,
    *,
    action: str,
    previous_status: str,
    reason: str | None,
    actor: str | None,
    value_before: Any,
) -> None:
    """Append the decision to the audit trail, in the same transaction as the change."""
    db.add(
        FinancialDataReviewEvent(
            financial_data_id=row.id,
            action=action,
            previous_status=previous_status,
            new_status=row.status,
            reason=reason,
            actor=actor,
            value_before=value_before,
            value_after=row.value_normalized,
        )
    )


def _clean(text: str | None) -> str | None:
    return text.strip() if text and text.strip() else None


async def review_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    reviewer_notes: str | None = None,
    value_normalized_override: Any | None = None,
    actor: str | None = None,
    expected_status: str | None = None,
    expected_updated_at: datetime | None = None,
) -> FinancialDataRead:
    """
    Transition financial data point to 'reviewed' status.
    Requires value_normalized to be NOT NULL.
    A value override is traced in the audit trail (value before / after).
    """
    row = await _load_for_decision(db, data_id, expected_status, expected_updated_at)
    previous_status, value_before = row.status, row.value_normalized

    if row.status in ("verified", "rejected"):
        raise InvalidTransitionError(f"Cannot transition to 'reviewed' from status '{row.status}'")

    if value_normalized_override is not None:
        row.value_normalized = value_normalized_override

    if not can_review(row.status, row.value_normalized):
        raise InvalidTransitionError("Cannot review financial data: value_normalized must not be null")

    row.status = "reviewed"
    row.validation_method = "human"
    if reviewer_notes:
        row.notes = f"{row.notes} | Review: {reviewer_notes}" if row.notes else f"Review: {reviewer_notes}"

    row.updated_at = datetime.now(UTC)
    _record_event(db, row, action="review", previous_status=previous_status, reason=_clean(reviewer_notes),
                  actor=_clean(actor), value_before=value_before)

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def verify_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    verified_by: str,
    verification_notes: str | None = None,
    expected_status: str | None = None,
    expected_updated_at: datetime | None = None,
) -> FinancialDataRead:
    """
    Transition financial data point to 'verified' status.
    Invariant: Can ONLY be verified if previously 'reviewed'. Direct jump is forbidden.
    Requires verified_by and sets verified_at.
    """
    row = await _load_for_decision(db, data_id, expected_status, expected_updated_at)
    previous_status, value_before = row.status, row.value_normalized

    if row.status != "reviewed":
        raise InvalidTransitionError(
            f"Direct verification from status '{row.status}' is forbidden; record must be 'reviewed' first"
        )

    if not verified_by or not verified_by.strip():
        raise ValueError("verified_by validator identifier is required")

    if not can_verify(row.status, row.value_normalized):
        raise InvalidTransitionError("Cannot verify financial data: value_normalized must not be null")

    now = datetime.now(UTC)
    row.status = "verified"
    row.validation_method = "human"
    row.verified_by = verified_by.strip()
    row.verified_at = now
    row.updated_at = now
    if verification_notes:
        row.notes = (
            f"{row.notes} | Verification: {verification_notes}"
            if row.notes
            else f"Verification: {verification_notes}"
        )
    _record_event(db, row, action="verify", previous_status=previous_status, reason=_clean(verification_notes),
                  actor=row.verified_by, value_before=value_before)

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def reject_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    reason: str,
    actor: str | None = None,
    expected_status: str | None = None,
    expected_updated_at: datetime | None = None,
) -> FinancialDataRead:
    """
    Transition financial data point to 'rejected' status.
    Requires mandatory rejection reason. A rejected observation stays rejected.
    """
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is mandatory")

    row = await _load_for_decision(db, data_id, expected_status, expected_updated_at)
    previous_status, value_before = row.status, row.value_normalized
    if not can_reject(row.status):
        raise InvalidTransitionError("Observation is already 'rejected'")

    row.status = "rejected"
    row.notes = f"{row.notes} | Rejection: {reason.strip()}" if row.notes else f"Rejection: {reason.strip()}"
    row.updated_at = datetime.now(UTC)
    _record_event(db, row, action="reject", previous_status=previous_status, reason=reason.strip(),
                  actor=_clean(actor), value_before=value_before)

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def bulk_review_financial_data(
    db: AsyncSession,
    data_ids: list[str],
    *,
    actor: str,
    reviewer_notes: str | None = None,
    expected: dict[str, tuple[str | None, datetime | None]] | None = None,
) -> list[str]:
    """Review several observations in ONE all-or-nothing transaction.

    Every row is locked (SELECT ... FOR UPDATE, ordered by id to avoid deadlocks), checked
    against the state the caller saw, and must be reviewable; otherwise nothing is written
    (404 / 409 / invalid transition). Each change gets its own audit event with the actor.
    """
    if not actor or not actor.strip():
        raise ValueError("actor is required")
    expected = expected or {}
    unique_ids = sorted(set(data_ids))
    result = await db.execute(
        select(FinancialData)
        .where(FinancialData.id.in_(unique_ids), FinancialData.deleted_at.is_(None))
        .order_by(FinancialData.id)
        .with_for_update(of=FinancialData)
    )
    rows = {row.id: row for row in result.scalars().all()}
    missing = [d for d in unique_ids if d not in rows]
    if missing:
        raise ObservationNotFoundError(f"FinancialData not found: {', '.join(missing)}")
    for d_id in unique_ids:
        exp_status, exp_updated_at = expected.get(d_id, (None, None))
        check_expected_state(rows[d_id], exp_status, exp_updated_at)
        if rows[d_id].status not in ("extracted", "needs_review") or not can_review(
            rows[d_id].status, rows[d_id].value_normalized
        ):
            raise InvalidTransitionError(
                f"FinancialData '{d_id}' cannot be reviewed from status '{rows[d_id].status}'"
            )

    now = datetime.now(UTC)
    for d_id in unique_ids:
        row = rows[d_id]
        previous_status, value_before = row.status, row.value_normalized
        row.status = "reviewed"
        row.validation_method = "human"
        if reviewer_notes:
            row.notes = (
                f"{row.notes} | Bulk Review: {reviewer_notes}" if row.notes else f"Bulk Review: {reviewer_notes}"
            )
        row.updated_at = now
        _record_event(db, row, action="review", previous_status=previous_status,
                      reason=_clean(reviewer_notes), actor=actor.strip(), value_before=value_before)

    await db.commit()
    return unique_ids


async def get_financial_data_quality_summary(db: AsyncSession):
    """Calculate and return DataQualitySummary metrics across financial data points."""
    # Query counts by status
    status_q = (
        select(FinancialData.status, func.count(FinancialData.id))
        .where(FinancialData.deleted_at.is_(None))
        .group_by(FinancialData.status)
    )
    status_rows = (await db.execute(status_q)).all()
    counts = dict(status_rows)

    extracted_c = counts.get("extracted", 0)
    needs_review_c = counts.get("needs_review", 0)
    reviewed_c = counts.get("reviewed", 0)
    verified_c = counts.get("verified", 0)
    rejected_c = counts.get("rejected", 0)
    total_c = extracted_c + needs_review_c + reviewed_c + verified_c + rejected_c

    # No observation: a rate is undefined (None), never 0 %.
    verif_rate = round(verified_c / total_c, 4) if total_c > 0 else None
    needs_review_rate = round(needs_review_c / total_c, 4) if total_c > 0 else None

    # Distinct institutions and metrics
    inst_q = select(func.count(func.distinct(FinancialData.institution_id))).where(
        FinancialData.deleted_at.is_(None)
    )
    distinct_inst = (await db.execute(inst_q)).scalar_one()

    metric_q = select(func.count(func.distinct(FinancialData.metric_code))).where(
        FinancialData.deleted_at.is_(None)
    )
    distinct_met = (await db.execute(metric_q)).scalar_one()

    return DataQualitySummary(
        total_points=total_c,
        extracted_count=extracted_c,
        needs_review_count=needs_review_c,
        reviewed_count=reviewed_c,
        verified_count=verified_c,
        rejected_count=rejected_c,
        verification_rate=verif_rate,
        needs_review_rate=needs_review_rate,
        distinct_institutions_count=distinct_inst,
        distinct_metrics_count=distinct_met,
    )


async def get_financial_data_duplicates(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    country_code: str | None = None,
    metric_code: str | None = None,
    period_year: int | None = None,
    status: str | None = None,
    source_id: str | None = None,
) -> PaginatedResponse[DuplicateGroupResponse]:
    """Retrieve grouped duplicate financial data observations."""
    consolidator = FinancialDataConsolidator()
    rows = await consolidator.fetch_observations(
        db,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )
    dup_groups = consolidator.get_duplicates(rows)
    total = len(dup_groups)
    offset = (page - 1) * page_size
    paged = dup_groups[offset : offset + page_size]

    items = [
        DuplicateGroupResponse(
            logical_key=g.logical_key,
            institution_id=g.institution_id,
            metric_code=g.metric_code,
            period_year=g.period_year,
            period_type=g.period_type,
            duplicate_type=g.duplicate_type,
            count=g.count,
            observations=[ObservationResponse.model_validate(o.model_dump()) for o in g.observations],
        )
        for g in paged
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_financial_data_conflicts(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    country_code: str | None = None,
    metric_code: str | None = None,
    period_year: int | None = None,
    status: str | None = None,
    source_id: str | None = None,
) -> PaginatedResponse[ConflictRecordResponse]:
    """Retrieve categorized contradictions between financial observations."""
    consolidator = FinancialDataConsolidator()
    rows = await consolidator.fetch_observations(
        db,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )
    conflicts = consolidator.get_conflicts(rows)
    total = len(conflicts)
    offset = (page - 1) * page_size
    paged = conflicts[offset : offset + page_size]

    items = [
        ConflictRecordResponse(
            conflict_id=c.conflict_id,
            conflict_type=c.conflict_type,
            institution_id=c.institution_id,
            institution_name=c.institution_name,
            metric_code=c.metric_code,
            period_year=c.period_year,
            period_type=c.period_type,
            observations=[ObservationResponse.model_validate(o.model_dump()) for o in c.observations],
            proposed_resolution=c.proposed_resolution,
            recommendation_reason=c.recommendation_reason,
            requires_human_review=c.requires_human_review,
            has_verified_observation=c.has_verified_observation,
        )
        for g in paged
        for c in [g]
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_financial_data_coverage(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    country_code: str | None = None,
) -> PaginatedResponse[InstitutionCoverageResponse]:
    """Retrieve historical depth and document coverage per institution."""
    consolidator = FinancialDataConsolidator()
    rows = await consolidator.fetch_observations(
        db,
        institution_id=institution_id,
        country_code=country_code,
    )

    # Build institution metadata lookup
    inst_q = select(Institution).options(selectinload(Institution.country)).where(Institution.deleted_at.is_(None))
    if institution_id:
        inst_q = inst_q.where(Institution.id == institution_id)
    inst_res = (await db.execute(inst_q)).scalars().all()
    meta = {
        i.id: {
            "name": i.name_commercial or i.name_official,
            "country": i.country.code if i.country else "UMOA",
        }
        for i in inst_res
    }

    coverages = consolidator.get_coverage(rows, institution_meta=meta)
    total = len(coverages)
    offset = (page - 1) * page_size
    paged = coverages[offset : offset + page_size]

    items = [
        InstitutionCoverageResponse(
            institution_id=c.institution_id,
            institution_name=c.institution_name,
            country_code=c.country_code,
            first_year=c.first_year,
            last_year=c.last_year,
            available_years=c.available_years,
            missing_years=c.missing_years,
            coverage_ratio=c.coverage_ratio,
            metrics_available_count=c.metrics_available_count,
            documents_available_count=c.documents_available_count,
            data_points_count=c.data_points_count,
        )
        for c in paged
    ]

    return PaginatedResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_financial_data_historical_quality(
    db: AsyncSession,
    *,
    institution_id: str | None = None,
    country_code: str | None = None,
    metric_code: str | None = None,
    period_year: int | None = None,
    status: str | None = None,
    source_id: str | None = None,
) -> HistoricalQualityResponse:
    """Generate multi-dimensional data quality scorecard."""
    consolidator = FinancialDataConsolidator()
    rows = await consolidator.fetch_observations(
        db,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )
    report = consolidator.get_quality_report(rows)
    return HistoricalQualityResponse(
        total_points=report.total_points,
        verified_count=report.verified_count,
        reviewed_count=report.reviewed_count,
        needs_review_count=report.needs_review_count,
        rejected_count=report.rejected_count,
        extracted_count=report.extracted_count,
        potential_duplicates_count=report.potential_duplicates_count,
        conflicts_count=report.conflicts_count,
        institutions_covered_count=report.institutions_covered_count,
        metrics_covered_count=report.metrics_covered_count,
        periods_covered_count=report.periods_covered_count,
        missing_periods_count=report.missing_periods_count,
        historical_anomalies_count=report.historical_anomalies_count,
        overall_quality_score=report.overall_quality_score,
        quality_dimensions=[
            QualityDimensionResponse(
                dimension=d.dimension,
                status=d.status,
                score=d.score,
                weight=d.weight,
                details=d.details,
            )
            for d in report.quality_dimensions
        ],
    )

