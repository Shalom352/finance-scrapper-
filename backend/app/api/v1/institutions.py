"""UMOA Banking Intelligence — Institution Router"""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.institution import InstitutionList, InstitutionRead
from app.services.institution import get_institution_by_id, get_institutions
from scraping.institutions.models import (
    InstitutionCoverage,
    InstitutionFinancials,
    InstitutionGrowth,
    InstitutionHistory,
    InstitutionRatios,
)
from scraping.institutions.service import InstitutionProfileService

router = APIRouter(prefix="/api/v1", tags=["institutions"])
profile_service = InstitutionProfileService()

@router.get("/institutions", summary="List institutions", response_model=PaginatedResponse[InstitutionList])
async def list_institutions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search term"),
    country_code: str | None = Query(None, description="Filter by country code"),
    banking_group_id: str | None = Query(None, description="Filter by banking group ID"),
    institution_type: str | None = Query(None, description="Filter by institution type"),
    status: str | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[InstitutionList]:
    return await get_institutions(
        db,
        page=page,
        page_size=page_size,
        search=search,
        country_code=country_code,
        banking_group_id=banking_group_id,
        institution_type=institution_type,
        status=status,
    )

@router.get("/institutions/{institution_id}", summary="Get institution by ID", response_model=InstitutionRead)
async def get_institution(
    institution_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionRead:
    result = await get_institution_by_id(db, institution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return result


# ============================================================
# Phase 10 — Institution financial profile (descriptive, fully traceable)
# ============================================================

PeriodTypeQ = Literal["annual", "semi_annual", "quarterly"]
DataScopeQ = Literal["individual", "consolidated"]


async def _existing_institution_id(db: AsyncSession, institution_id: str) -> str:
    if await get_institution_by_id(db, institution_id) is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return institution_id


@router.get(
    "/institutions/{institution_id}/financials",
    summary="Qualified financial values of one fiscal year",
    response_model=InstitutionFinancials,
)
async def get_institution_financials(
    institution_id: str,
    period_year: int | None = Query(None, description="Fiscal year (default: latest year with qualified data)"),
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    indicator: str | None = Query(None, description="Restrict to one metric code"),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionFinancials:
    await _existing_institution_id(db, institution_id)
    return await profile_service.financials(
        db, institution_id, period_year=period_year, period_type=period_type, data_scope=data_scope,
        indicator=indicator,
    )


@router.get(
    "/institutions/{institution_id}/history",
    summary="Qualified historical series (only years that hold a value)",
    response_model=InstitutionHistory,
)
async def get_institution_history(
    institution_id: str,
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    indicator: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionHistory:
    await _existing_institution_id(db, institution_id)
    return await profile_service.history(
        db, institution_id, period_type=period_type, data_scope=data_scope, indicator=indicator
    )


@router.get(
    "/institutions/{institution_id}/ratios",
    summary="Ratios of one institution (existing RatioCalculator rules)",
    response_model=InstitutionRatios,
)
async def get_institution_ratios(
    institution_id: str,
    period_year: int | None = Query(None),
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionRatios:
    await _existing_institution_id(db, institution_id)
    return await profile_service.ratios(
        db, institution_id, period_year=period_year, period_type=period_type, data_scope=data_scope
    )


@router.get(
    "/institutions/{institution_id}/growth",
    summary="Year-over-year changes of one institution (existing GrowthCalculator rules)",
    response_model=InstitutionGrowth,
)
async def get_institution_growth(
    institution_id: str,
    period_year: int | None = Query(None),
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    indicator: str | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionGrowth:
    await _existing_institution_id(db, institution_id)
    return await profile_service.growth(
        db, institution_id, period_year=period_year, period_type=period_type, data_scope=data_scope,
        indicator=indicator,
    )


@router.get(
    "/institutions/{institution_id}/coverage",
    summary="Descriptive coverage, data-quality counters and source documents",
    response_model=InstitutionCoverage,
)
async def get_institution_coverage(
    institution_id: str,
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionCoverage:
    await _existing_institution_id(db, institution_id)
    return await profile_service.coverage(db, institution_id, period_type=period_type, data_scope=data_scope)
