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
from app.schemas.deal import DealDetail, DealDuplicateRead, DealListItem, DuplicateDecisionRequest
from app.schemas.financial_data import FinancialDataExplorerItem, FinancialDataRead
from app.services.data_quality import get_data_quality_counts, get_review_detail, get_review_history
from app.services.deal import (
    decide_deal,
    decide_duplicate,
    get_deal,
    list_deals,
    list_open_duplicates,
)
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


# --------------------------------------------------------------------------- Phase 21
# A human withdraws an automatic validation: back to needs_review, never re-validated automatically.


async def _revoke(model, row_id: str, payload: ReviewActionRequest, db: AsyncSession) -> None:
    from sqlalchemy import select

    from scraping.validation.automatic import RevokeError, revoke

    row = (await db.execute(select(model).where(model.id == row_id, model.deleted_at.is_(None))
                            .with_for_update(of=model))).unique().scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    if payload.expected_status is not None and row.status != payload.expected_status:
        raise HTTPException(status_code=409, detail=f"Status is now '{row.status}'; reload before deciding")
    try:
        await revoke(db, row, actor=payload.actor, reason=payload.reason)
    except RevokeError as err:
        await db.rollback()
        raise HTTPException(status_code=422, detail=str(err)) from err
    await db.commit()


@router.post("/deals/{deal_id}/revoke-automatic", summary="Withdraw an automatic validation (deal)",
             response_model=DealDetail)
async def revoke_deal_automatic(deal_id: str, payload: ReviewActionRequest, db: AsyncSession = Depends(get_db_session)):
    from app.models.deal import Deal

    await _revoke(Deal, deal_id, payload, db)
    return await get_deal(db, deal_id)


@router.post("/{data_id}/revoke-automatic", summary="Withdraw an automatic validation (observation)",
             response_model=FinancialDataRead)
async def revoke_observation_automatic(data_id: str, payload: ReviewActionRequest,
                                       db: AsyncSession = Depends(get_db_session)):
    from app.models.financial_data import FinancialData
    from app.services.financial_data import get_financial_data_by_id

    await _revoke(FinancialData, data_id, payload, db)
    return await get_financial_data_by_id(db, data_id)


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


# --------------------------------------------------------------------------- deals (Phase 13)
# Declared BEFORE /{data_id}: same Review Center, same guarantees (actor, reason, 404, 409,
# row lock, audit event in the same transaction).


@router.get("/deals", summary="Deal review queue (needs_review by default)",
            response_model=PaginatedResponse[DealListItem])
async def deal_queue(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(20, ge=1, le=100),
    status: Literal["extracted", "needs_review", "reviewed", "verified", "rejected"] = Query("needs_review"),
    country: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DealListItem]:
    return await list_deals(db, page=page, page_size=page_size, status=status, country=country)


@router.get("/deal-duplicates", summary="Open duplicate candidates (never merged automatically)",
            response_model=PaginatedResponse[DealDuplicateRead])
async def deal_duplicates(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DealDuplicateRead]:
    return await list_open_duplicates(db, page=page, page_size=page_size)


@router.post("/deal-duplicates/{candidate_id}/decide", summary="Human decision on a duplicate candidate",
             response_model=DealDuplicateRead)
async def decide_deal_duplicate(candidate_id: str, payload: DuplicateDecisionRequest,
                                db: AsyncSession = Depends(get_db_session)):
    return await _decide(
        lambda: decide_duplicate(
            db, candidate_id, decision=payload.decision, actor=payload.actor, reason=payload.reason,
            primary_deal_id=payload.primary_deal_id, expected_state=payload.expected_state,
        ),
        db,
    )


@router.get("/deals/{deal_id}", summary="Deal under review", response_model=DealDetail)
async def deal_detail(deal_id: str, db: AsyncSession = Depends(get_db_session)) -> DealDetail:
    result = await get_deal(db, deal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return result


@router.post("/deals/{deal_id}/{action}", summary="review / verify / reject a deal", response_model=DealDetail)
async def decide_on_deal(deal_id: str, action: Literal["review", "verify", "reject"], payload: ReviewActionRequest,
                         db: AsyncSession = Depends(get_db_session)):
    return await _decide(
        lambda: decide_deal(
            db, deal_id, action, actor=payload.actor, reason=payload.reason,
            expected_status=payload.expected_status, expected_updated_at=payload.expected_updated_at,
        ),
        db,
    )


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
