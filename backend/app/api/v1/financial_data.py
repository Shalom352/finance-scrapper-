"""UMOA Banking Intelligence — Financial Data Router"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.financial_data import (
    ConflictRecordResponse,
    DataQualitySummary,
    DuplicateGroupResponse,
    FinancialDataBulkReviewRequest,
    FinancialDataExplorerItem,
    FinancialDataFacets,
    FinancialDataRead,
    FinancialDataRejectRequest,
    FinancialDataReviewRequest,
    FinancialDataVerifyRequest,
    HistoricalQualityResponse,
    InstitutionCoverageResponse,
)
from app.services.financial_data import (
    bulk_review_financial_data,
    export_financial_data_csv,
    get_financial_data,
    get_financial_data_by_id,
    get_financial_data_conflicts,
    get_financial_data_coverage,
    get_financial_data_duplicates,
    get_financial_data_facets,
    get_financial_data_historical_quality,
    get_financial_data_quality_summary,
    reject_financial_data,
    review_financial_data,
    verify_financial_data,
)
from scraping.financial_data.export import EXPORT_MAX_ROWS, ExportTooLargeError
from scraping.financial_data.review import ObservationNotFoundError, StaleStateError

router = APIRouter(prefix="/api/v1", tags=["financial-data"])


@router.get("/financial-data/quality-summary", summary="Get data quality summary", response_model=DataQualitySummary)
async def quality_summary(
    db: AsyncSession = Depends(get_db_session),
) -> DataQualitySummary:
    """Retrieve statistical distribution of data points across validation workflow statuses."""
    return await get_financial_data_quality_summary(db)


@router.get("/financial-data/duplicates", summary="List duplicate financial observations", response_model=PaginatedResponse[DuplicateGroupResponse])
async def list_duplicates(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    country_code: str | None = Query(None, description="Filter by country code"),
    metric_code: str | None = Query(None, description="Filter by metric code"),
    period_year: int | None = Query(None, description="Filter by period year"),
    status: str | None = Query(None, description="Filter by status"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DuplicateGroupResponse]:
    """Retrieve grouped potential duplicate observations sharing the same logical key."""
    return await get_financial_data_duplicates(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )


@router.get("/financial-data/conflicts", summary="List conflicting financial observations", response_model=PaginatedResponse[ConflictRecordResponse])
async def list_conflicts(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    country_code: str | None = Query(None, description="Filter by country code"),
    metric_code: str | None = Query(None, description="Filter by metric code"),
    period_year: int | None = Query(None, description="Filter by period year"),
    status: str | None = Query(None, description="Filter by status"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[ConflictRecordResponse]:
    """Retrieve categorized contradictions and discrepancies between financial observations."""
    return await get_financial_data_conflicts(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )


@router.get("/financial-data/coverage", summary="List institutional historical coverage", response_model=PaginatedResponse[InstitutionCoverageResponse])
async def list_coverage(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    country_code: str | None = Query(None, description="Filter by country code"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[InstitutionCoverageResponse]:
    """Retrieve historical depth, missing intervals, and document coverage per institution."""
    return await get_financial_data_coverage(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        country_code=country_code,
    )


@router.get("/financial-data/historical-quality", summary="Get multi-dimensional historical quality report", response_model=HistoricalQualityResponse)
async def historical_quality(
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    country_code: str | None = Query(None, description="Filter by country code"),
    metric_code: str | None = Query(None, description="Filter by metric code"),
    period_year: int | None = Query(None, description="Filter by period year"),
    status: str | None = Query(None, description="Filter by status"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    db: AsyncSession = Depends(get_db_session),
) -> HistoricalQualityResponse:
    """Retrieve explainable 8-dimensional data quality scorecard and consolidation report."""
    return await get_financial_data_historical_quality(
        db,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        period_year=period_year,
        status=status,
        source_id=source_id,
    )


@router.post("/financial-data/bulk-review", summary="Bulk review (max 100, all-or-nothing, audited)",
             response_model=list[str])
async def bulk_review(
    payload: FinancialDataBulkReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Bulk transition data points to reviewed status (locked, audited, no partial write)."""
    expected = {e.data_id: (e.expected_status, e.expected_updated_at) for e in payload.expected}
    return await _legacy_decide(
        lambda: bulk_review_financial_data(
            db, payload.data_ids, actor=payload.actor, reviewer_notes=payload.reviewer_notes, expected=expected
        ),
        db,
    )


async def _legacy_decide(action, db: AsyncSession):
    """Pre-existing contract kept (invalid transition -> 400) with the Review Center guarantees:
    missing observation -> 404, stale state -> 409, never a partial or silent write."""
    try:
        return await action()
    except ObservationNotFoundError as err:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(err)) from err
    except StaleStateError as err:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(err)) from err
    except ValueError as err:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(err)) from err


SortQ = Literal["institution", "country", "indicator", "year", "value"]


def split_ids(institution_ids: str | None) -> list[str] | None:
    return [i.strip() for i in institution_ids.split(",") if i.strip()] if institution_ids else None


@router.get(
    "/financial-data",
    summary="List financial data (explorer: filters, sort, provenance summary, qualification)",
    response_model=PaginatedResponse[FinancialDataExplorerItem],
)
async def list_financial_data(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    institution_ids: str | None = Query(None, description="Comma-separated institution IDs"),
    country_code: str | None = Query(None, description="Filter by country code (institution's country)"),
    metric_code: str | None = Query(None, description="Filter by metric code"),
    period_type: str | None = Query(None, description="Filter by period type"),
    period_year: int | None = Query(None, description="Filter by period year"),
    scope: str | None = Query(None, description="Filter by scope"),
    status: str | None = Query(None, description="Filter by status"),
    currency_normalized: str | None = Query(None, description="Filter by normalized currency"),
    include_rejected: bool = Query(True, description="Include rejected observations (labelled 'rejected')"),
    sort: SortQ | None = Query(None, description="Sort column (value sort is grouped by currency)"),
    order: Literal["asc", "desc"] = Query("asc"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[FinancialDataExplorerItem]:
    return await get_financial_data(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        institution_ids=split_ids(institution_ids),
        country_code=country_code,
        metric_code=metric_code,
        period_type=period_type,
        period_year=period_year,
        scope=scope,
        status=status,
        currency_normalized=currency_normalized,
        include_rejected=include_rejected,
        sort=sort,
        order=order,
    )


@router.get(
    "/financial-data/export",
    summary=f"CSV export of the filtered observations (max {EXPORT_MAX_ROWS} rows)",
    response_class=Response,
)
async def export_financial_data(
    institution_id: str | None = Query(None),
    institution_ids: str | None = Query(None),
    country_code: str | None = Query(None),
    metric_code: str | None = Query(None),
    period_type: str | None = Query(None),
    period_year: int | None = Query(None),
    scope: str | None = Query(None),
    status: str | None = Query(None),
    currency_normalized: str | None = Query(None),
    include_rejected: bool = Query(False, description="Rejected rows are excluded unless explicitly requested"),
    sort: SortQ | None = Query(None),
    order: Literal["asc", "desc"] = Query("asc"),
    db: AsyncSession = Depends(get_db_session),
) -> Response:
    try:
        csv_text = await export_financial_data_csv(
            db,
            sort=sort,
            order=order,
            institution_id=institution_id,
            institution_ids=split_ids(institution_ids),
            country_code=country_code,
            metric_code=metric_code,
            period_type=period_type,
            period_year=period_year,
            scope=scope,
            status=status,
            currency_normalized=currency_normalized,
            include_rejected=include_rejected,
        )
    except ExportTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=f"export_too_large: {exc.total} rows > {EXPORT_MAX_ROWS}; refine the filters",
        ) from exc
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="financial-data.csv"'},
    )


@router.get(
    "/financial-data/facets",
    summary="Values really present in the stored observations",
    response_model=FinancialDataFacets,
)
async def financial_data_facets(db: AsyncSession = Depends(get_db_session)) -> FinancialDataFacets:
    return await get_financial_data_facets(db)


@router.get("/financial-data/{data_id}", summary="Get financial data by ID", response_model=FinancialDataRead)
async def get_financial_datum(
    data_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    result = await get_financial_data_by_id(db, data_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Financial Data not found")
    return result


@router.post("/financial-data/{data_id}/review", summary="Review financial data point", response_model=FinancialDataRead)
async def review_datum(
    data_id: str,
    payload: FinancialDataReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    """Transition financial data point to 'reviewed' status (value override audited)."""
    return await _legacy_decide(
        lambda: review_financial_data(
            db,
            data_id,
            reviewer_notes=payload.reviewer_notes,
            value_normalized_override=payload.value_normalized_override,
            actor=payload.actor,
            expected_status=payload.expected_status,
            expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )


@router.post("/financial-data/{data_id}/verify", summary="Verify financial data point", response_model=FinancialDataRead)
async def verify_datum(
    data_id: str,
    payload: FinancialDataVerifyRequest,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    """Transition financial data point from 'reviewed' to 'verified' status."""
    return await _legacy_decide(
        lambda: verify_financial_data(
            db,
            data_id,
            verified_by=payload.verified_by,
            verification_notes=payload.verification_notes,
            expected_status=payload.expected_status,
            expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )


@router.post("/financial-data/{data_id}/reject", summary="Reject financial data point", response_model=FinancialDataRead)
async def reject_datum(
    data_id: str,
    payload: FinancialDataRejectRequest,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    """Transition financial data point to 'rejected' status."""
    return await _legacy_decide(
        lambda: reject_financial_data(
            db,
            data_id,
            reason=payload.reason,
            actor=payload.actor,
            expected_status=payload.expected_status,
            expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )
