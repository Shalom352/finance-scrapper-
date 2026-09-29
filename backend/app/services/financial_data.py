"""UMOA Banking Intelligence — Financial Data Service

Query logic for financial data.
"""
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.schemas.common import PaginatedResponse
from app.schemas.financial_data import (
    ConflictRecordResponse,
    DataQualitySummary,
    DuplicateGroupResponse,
    FinancialDataList,
    FinancialDataRead,
    HistoricalQualityResponse,
    InstitutionCoverageResponse,
    ObservationResponse,
    QualityDimensionResponse,
)
from scraping.consolidation import FinancialDataConsolidator


async def get_financial_data(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    metric_code: str | None = None,
    period_type: str | None = None,
    period_year: int | None = None,
    scope: str | None = None,
    status: str | None = None,
    currency_normalized: str | None = None,
) -> PaginatedResponse[FinancialDataList]:
    query = select(FinancialData).where(FinancialData.deleted_at.is_(None))

    if institution_id:
        query = query.where(FinancialData.institution_id == institution_id)

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

    if currency_normalized:
        query = query.where(FinancialData.currency_normalized == currency_normalized)

    query = query.order_by(FinancialData.period_year.desc(), FinancialData.metric_code)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[FinancialDataList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
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


async def review_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    reviewer_notes: str | None = None,
    value_normalized_override: Any | None = None,
) -> FinancialDataRead:
    """
    Transition financial data point to 'reviewed' status.
    Requires value_normalized to be NOT NULL.
    """
    result = await db.execute(
        select(FinancialData).where(FinancialData.id == data_id, FinancialData.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"FinancialData '{data_id}' not found")

    if row.status in ("verified", "rejected"):
        raise ValueError(f"Cannot transition to 'reviewed' from status '{row.status}'")

    if value_normalized_override is not None:
        row.value_normalized = value_normalized_override

    if row.value_normalized is None:
        raise ValueError("Cannot review financial data: value_normalized must not be null")

    row.status = "reviewed"
    if reviewer_notes:
        row.notes = f"{row.notes} | Review: {reviewer_notes}" if row.notes else f"Review: {reviewer_notes}"

    row.updated_at = datetime.now(UTC)

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def verify_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    verified_by: str,
    verification_notes: str | None = None,
) -> FinancialDataRead:
    """
    Transition financial data point to 'verified' status.
    Invariant: Can ONLY be verified if previously 'reviewed'. Direct jump is forbidden.
    Requires verified_by and sets verified_at.
    """
    result = await db.execute(
        select(FinancialData).where(FinancialData.id == data_id, FinancialData.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"FinancialData '{data_id}' not found")

    if row.status != "reviewed":
        raise ValueError(
            f"Direct verification from status '{row.status}' is forbidden; record must be 'reviewed' first"
        )

    if not verified_by or not verified_by.strip():
        raise ValueError("verified_by validator identifier is required")

    if row.value_normalized is None:
        raise ValueError("Cannot verify financial data: value_normalized must not be null")

    now = datetime.now(UTC)
    row.status = "verified"
    row.verified_by = verified_by.strip()
    row.verified_at = now
    row.updated_at = now
    if verification_notes:
        row.notes = (
            f"{row.notes} | Verification: {verification_notes}"
            if row.notes
            else f"Verification: {verification_notes}"
        )

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def reject_financial_data(
    db: AsyncSession,
    data_id: str,
    *,
    reason: str,
) -> FinancialDataRead:
    """
    Transition financial data point to 'rejected' status.
    Requires mandatory rejection reason.
    """
    if not reason or not reason.strip():
        raise ValueError("Rejection reason is mandatory")

    result = await db.execute(
        select(FinancialData).where(FinancialData.id == data_id, FinancialData.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    if not row:
        raise ValueError(f"FinancialData '{data_id}' not found")

    row.status = "rejected"
    row.notes = f"{row.notes} | Rejection: {reason.strip()}" if row.notes else f"Rejection: {reason.strip()}"
    row.updated_at = datetime.now(UTC)

    await db.commit()
    return await get_financial_data_by_id(db, data_id)  # type: ignore[return-value]


async def bulk_review_financial_data(
    db: AsyncSession,
    data_ids: list[str],
    *,
    reviewer_notes: str | None = None,
) -> list[str]:
    """Bulk transition multiple data points to reviewed status."""
    updated_ids: list[str] = []
    for d_id in data_ids:
        result = await db.execute(
            select(FinancialData).where(FinancialData.id == d_id, FinancialData.deleted_at.is_(None))
        )
        row = result.scalar_one_or_none()
        if row and row.status in ("extracted", "needs_review") and row.value_normalized is not None:
            row.status = "reviewed"
            if reviewer_notes:
                row.notes = (
                    f"{row.notes} | Bulk Review: {reviewer_notes}"
                    if row.notes
                    else f"Bulk Review: {reviewer_notes}"
                )
            row.updated_at = datetime.now(UTC)
            updated_ids.append(d_id)

    await db.commit()
    return updated_ids


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

    verif_rate = round(verified_c / total_c, 4) if total_c > 0 else 0.0
    needs_review_rate = round(needs_review_c / total_c, 4) if total_c > 0 else 0.0

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

