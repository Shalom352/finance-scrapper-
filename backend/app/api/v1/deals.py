"""UMOA Banking Intelligence — Deal Intelligence router (Phase 13). Read-only.

Deals enter the database only through the structured import (CLI); human decisions go
through the existing Review Center (/api/v1/data-quality/deals/...).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.deals import DEAL_STATUSES, DEAL_TYPES, PARTICIPANT_ROLES
from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.data_quality import ReviewEventRead
from app.schemas.deal import DealAnalytics, DealDetail, DealListItem
from app.services.deal import deal_analytics, get_deal, get_deal_history, list_deals

router = APIRouter(prefix="/api/v1/deals", tags=["deals"])

DealTypeQ = Literal[DEAL_TYPES]  # type: ignore[valid-type]
StatusQ = Literal[DEAL_STATUSES]  # type: ignore[valid-type]
RoleQ = Literal[PARTICIPANT_ROLES]  # type: ignore[valid-type]


@router.get("", summary="Deal explorer (filters, pagination)", response_model=PaginatedResponse[DealListItem])
async def deals(
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(20, ge=1, le=100),
    country: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
    bank: str | None = Query(None, description="Institution id involved in any role (or in participant_role)"),
    deal_type: DealTypeQ | None = Query(None),
    sector: str | None = Query(None, max_length=100),
    year: int | None = Query(None, ge=1900, le=2100, description="Signing year, else announcement year"),
    currency: str | None = Query(None, pattern=r"^[A-Z]{3}$"),
    status: StatusQ | None = Query(None),
    participant_role: RoleQ | None = Query(None),
    borrower: str | None = Query(None, max_length=255, description="Institution id or name fragment"),
    arranger: str | None = Query(None, max_length=255, description="Institution id or name fragment"),
    include_merged: bool = Query(False, description="Include deals attached to another deal by a human decision"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DealListItem]:
    return await list_deals(
        db, page=page, page_size=page_size, country=country, bank=bank, deal_type=deal_type, sector=sector,
        year=year, currency=currency, status=status, participant_role=participant_role, borrower=borrower,
        arranger=arranger, include_merged=include_merged,
    )


@router.get("/analytics", summary="Descriptive deal counts; amounts per currency and unit",
            response_model=DealAnalytics)
async def analytics(
    dimension: Literal["country", "year", "type", "sector", "institution"] = Query("country"),
    db: AsyncSession = Depends(get_db_session),
) -> DealAnalytics:
    return await deal_analytics(db, dimension)


@router.get("/{deal_id}", summary="Deal detail: terms, participants, timeline, provenance", response_model=DealDetail)
async def deal(deal_id: str, db: AsyncSession = Depends(get_db_session)) -> DealDetail:
    result = await get_deal(db, deal_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return result


@router.get("/{deal_id}/history", summary="Audit trail of the deal", response_model=list[ReviewEventRead])
async def history(deal_id: str, db: AsyncSession = Depends(get_db_session)) -> list[ReviewEventRead]:
    if await get_deal(db, deal_id) is None:
        raise HTTPException(status_code=404, detail="Deal not found")
    return await get_deal_history(db, deal_id)
