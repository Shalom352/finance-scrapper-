"""UMOA Banking Intelligence — Financial Data Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.financial_data import (
    ConflictRecordResponse,
    DataQualitySummary,
    DuplicateGroupResponse,
    FinancialDataBulkReviewRequest,
    FinancialDataList,
    FinancialDataRead,
    FinancialDataRejectRequest,
    FinancialDataReviewRequest,
    FinancialDataVerifyRequest,
    HistoricalQualityResponse,
    InstitutionCoverageResponse,
)
from app.services.financial_data import (
    bulk_review_financial_data,
    get_financial_data,
    get_financial_data_by_id,
    get_financial_data_conflicts,
    get_financial_data_coverage,
    get_financial_data_duplicates,
    get_financial_data_historical_quality,
    get_financial_data_quality_summary,
    reject_financial_data,
    review_financial_data,
    verify_financial_data,
)

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


@router.post("/financial-data/bulk-review", summary="Bulk review financial data", response_model=list[str])
async def bulk_review(
    payload: FinancialDataBulkReviewRequest,
    db: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Bulk transition data points to reviewed status."""
    return await bulk_review_financial_data(db, payload.data_ids, reviewer_notes=payload.reviewer_notes)


@router.get("/financial-data", summary="List financial data", response_model=PaginatedResponse[FinancialDataList])
async def list_financial_data(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    metric_code: str | None = Query(None, description="Filter by metric code"),
    period_type: str | None = Query(None, description="Filter by period type"),
    period_year: int | None = Query(None, description="Filter by period year"),
    scope: str | None = Query(None, description="Filter by scope"),
    status: str | None = Query(None, description="Filter by status"),
    currency_normalized: str | None = Query(None, description="Filter by normalized currency"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[FinancialDataList]:
    return await get_financial_data(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        metric_code=metric_code,
        period_type=period_type,
        period_year=period_year,
        scope=scope,
        status=status,
        currency_normalized=currency_normalized,
    )


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
    """Transition financial data point to 'reviewed' status."""
    try:
        return await review_financial_data(
            db,
            data_id,
            reviewer_notes=payload.reviewer_notes,
            value_normalized_override=payload.value_normalized_override,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/financial-data/{data_id}/verify", summary="Verify financial data point", response_model=FinancialDataRead)
async def verify_datum(
    data_id: str,
    payload: FinancialDataVerifyRequest,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    """Transition financial data point from 'reviewed' to 'verified' status."""
    try:
        return await verify_financial_data(
            db,
            data_id,
            verified_by=payload.verified_by,
            verification_notes=payload.verification_notes,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.post("/financial-data/{data_id}/reject", summary="Reject financial data point", response_model=FinancialDataRead)
async def reject_datum(
    data_id: str,
    payload: FinancialDataRejectRequest,
    db: AsyncSession = Depends(get_db_session),
) -> FinancialDataRead:
    """Transition financial data point to 'rejected' status."""
    try:
        return await reject_financial_data(
            db,
            data_id,
            reason=payload.reason,
        )
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
