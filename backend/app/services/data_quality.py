"""UMOA Banking Intelligence — Data Quality & Review Center service (Phase 12).

Read side of the Review Center. Every rule is an existing one:
  - statuses and counters: get_financial_data_quality_summary (Phase 5C);
  - conflicts / authority: qualify_rows -> qualify_metric -> EligibilityEngine;
  - transitions: scraping.financial_data.review (the guards used by the write services).
No value is computed except a difference between two observations of the same
logical key in the same currency and unit.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.review_event import FinancialDataReviewEvent
from app.schemas.data_quality import (
    DataQualityCounts,
    ReviewDetail,
    ReviewEventRead,
    ReviewObservation,
)
from app.services.financial_data import (
    conflict_observations,
    get_financial_data_by_id,
    get_financial_data_quality_summary,
    load_observations,
)
from scraping.financial_data.qualification import logical_key, qualify_rows
from scraping.financial_data.review import allowed_actions, difference, split_by_key


async def get_data_quality_counts(db: AsyncSession) -> DataQualityCounts:
    summary = await get_financial_data_quality_summary(db)
    conflicts = await conflict_observations(db)
    extra_unresolved = {o.id for o in conflicts if o.status != "needs_review"}
    return DataQualityCounts(
        total=summary.total_points,
        extracted=summary.extracted_count,
        needs_review=summary.needs_review_count,
        reviewed=summary.reviewed_count,
        verified=summary.verified_count,
        rejected=summary.rejected_count,
        conflict_keys=len({logical_key(o) for o in conflicts}),
        conflict_observations=len(conflicts),
        unresolved=summary.needs_review_count + len(extra_unresolved),
    )


async def get_review_detail(db: AsyncSession, data_id: str) -> ReviewDetail | None:
    observation = await get_financial_data_by_id(db, data_id)
    if observation is None:
        return None
    country_code = (
        await db.execute(
            select(Country.code)
            .join(Institution, Institution.country_id == Country.id)
            .where(Institution.id == observation.institution_id)
        )
    ).scalar_one_or_none()

    # Same institution / indicator / year, every scope and period type.
    related = await load_observations(
        db,
        FinancialData.institution_id == observation.institution_id,
        FinancialData.metric_code == observation.metric_code,
        FinancialData.period_year == observation.period_year,
    )
    qual = qualify_rows(related, related)  # grouped per logical key by the existing rule
    reference = next(o for o in related if o.id == data_id)
    competing, not_comparable = split_by_key(reference, related)
    competing_ids = {o.id for o in competing}

    def view(o) -> ReviewObservation:
        diff, reason = difference(reference, o) if o.id in competing_ids else (None, None)
        return ReviewObservation(
            id=o.id,
            status=o.status,
            qualification=qual.get(o.id, (None, None))[0],
            scope=o.scope or "",
            period_type=o.period_type,
            period_year=o.period_year,
            value_original=o.value_original,
            value_normalized=o.value_normalized,
            unit_normalized=o.unit_normalized,
            currency_normalized=o.currency_normalized,
            extraction_method=o.extraction_method,
            source_name=o.source_name,
            document_title=o.document_title,
            page_number=o.page_number,
            difference=diff,
            difference_reason=reason,
        )

    order = {"verified": 0, "reviewed": 1, "extracted": 2, "needs_review": 3, "rejected": 4}

    def ordered(rows):
        return sorted(rows, key=lambda o: (o.id != data_id, order.get(o.status, 9), o.id))

    qualification, authoritative_id = qual.get(data_id, (None, None))
    return ReviewDetail(
        observation=observation,
        country_code=country_code,
        qualification=qualification,
        authoritative_data_id=authoritative_id,
        allowed_actions=allowed_actions(observation.status, observation.value_normalized),
        competing=[view(o) for o in ordered(competing)],
        not_comparable=[view(o) for o in ordered(not_comparable)],
    )


async def get_review_history(db: AsyncSession, data_id: str) -> list[ReviewEventRead]:
    rows = (
        await db.execute(
            select(FinancialDataReviewEvent)
            .where(FinancialDataReviewEvent.financial_data_id == data_id)
            .order_by(FinancialDataReviewEvent.created_at, FinancialDataReviewEvent.id)
        )
    ).scalars().all()
    return [ReviewEventRead.model_validate(r) for r in rows]
