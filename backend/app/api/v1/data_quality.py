"""UMOA Banking Intelligence — Data Quality & Review Center router (Phase 12).

Thin HTTP layer over the existing services. Writes go through the existing
review / verify / reject services (same guards, audit event in the same
transaction). The resulting status is always decided by the backend.

No authentication exists in the platform: `actor` is declared by the operator
and recorded as such (documented limit).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.financial_data import SortQ, split_ids
from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.data_quality import (
    DataQualityCounts,
    ReviewActionRequest,
    ReviewDetail,
    ReviewEventRead,
)
from app.schemas.financial_data import FinancialDataExplorerItem, FinancialDataRead
from app.services.data_quality import get_data_quality_counts, get_review_detail, get_review_history
from app.services.financial_data import (
    get_financial_data,
    reject_financial_data,
    review_financial_data,
    verify_financial_data,
)
from scraping.financial_data.review import (
    InvalidTransitionError,
    ObservationNotFoundError,
    StaleStateError,
)

router = APIRouter(prefix="/api/v1/data-quality", tags=["data-quality"])


@router.get(
    "",
    summary="Review queue: needs_review and conflicting observations (or one explicit status)",
    response_model=PaginatedResponse[FinancialDataExplorerItem],
)
async def review_queue(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    institution_ids: str | None = Query(None, description="Comma-separated institution IDs"),
    country_code: str | None = Query(None),
    metric_code: str | None = Query(None),
    period_type: str | None = Query(None),
    period_year: int | None = Query(None),
    scope: str | None = Query(None),
    status: str | None = Query(None, description="Explicit status; empty = observations needing a decision"),
    currency_normalized: str | None = Query(None),
    sort: SortQ | None = Query(None),
    order: Literal["asc", "desc"] = Query("asc"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[FinancialDataExplorerItem]:
    return await get_financial_data(
        db,
        page=page,
        page_size=page_size,
        institution_ids=split_ids(institution_ids),
        country_code=country_code,
        metric_code=metric_code,
        period_type=period_type,
        period_year=period_year,
        scope=scope,
        status=status,
        currency_normalized=currency_normalized,
        sort=sort,
        order=order,
        attention_only=True,
    )


@router.get("/summary", summary="Descriptive counters of stored observations", response_model=DataQualityCounts)
async def summary(db: AsyncSession = Depends(get_db_session)) -> DataQualityCounts:
    return await get_data_quality_counts(db)


@router.get("/{data_id}", summary="Observation under review, competing observations, allowed actions",
            response_model=ReviewDetail)
async def detail(data_id: str, db: AsyncSession = Depends(get_db_session)) -> ReviewDetail:
    result = await get_review_detail(db, data_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return result


@router.get("/{data_id}/history", summary="Audit trail of the human decisions", response_model=list[ReviewEventRead])
async def history(data_id: str, db: AsyncSession = Depends(get_db_session)) -> list[ReviewEventRead]:
    if await get_review_detail(db, data_id) is None:
        raise HTTPException(status_code=404, detail="Observation not found")
    return await get_review_history(db, data_id)


async def _decide(action, db: AsyncSession) -> FinancialDataRead:
    try:
        return await action()
    except ObservationNotFoundError as err:
        await db.rollback()
        raise HTTPException(status_code=404, detail=str(err)) from err
    except StaleStateError as err:
        await db.rollback()
        raise HTTPException(status_code=409, detail=str(err)) from err
    except (InvalidTransitionError, ValueError) as err:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(err)) from err


@router.post("/{data_id}/review", summary="Mark as reviewed (existing transition)", response_model=FinancialDataRead)
async def review(data_id: str, payload: ReviewActionRequest, db: AsyncSession = Depends(get_db_session)):
    return await _decide(
        lambda: review_financial_data(
            db, data_id, reviewer_notes=payload.reason, actor=payload.actor,
            expected_status=payload.expected_status, expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )


@router.post("/{data_id}/verify", summary="Verify a reviewed observation (existing transition)",
             response_model=FinancialDataRead)
async def verify(data_id: str, payload: ReviewActionRequest, db: AsyncSession = Depends(get_db_session)):
    return await _decide(
        lambda: verify_financial_data(
            db, data_id, verified_by=payload.actor, verification_notes=payload.reason,
            expected_status=payload.expected_status, expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )


@router.post("/{data_id}/reject", summary="Reject (reason mandatory, existing transition)",
             response_model=FinancialDataRead)
async def reject(data_id: str, payload: ReviewActionRequest, db: AsyncSession = Depends(get_db_session)):
    return await _decide(
        lambda: reject_financial_data(
            db, data_id, reason=payload.reason, actor=payload.actor,
            expected_status=payload.expected_status, expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )
