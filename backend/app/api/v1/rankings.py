"""UMOA Banking Intelligence — Rankings Router (Phase 9)

Descriptive numerical orderings only — no qualitative judgement and no score.

Contract:
  - one indicator, one period_year, one period_type, one data_scope per ranking
    (defaults: annual + individual); period_year defaults to the latest year
    holding data, never to an arbitrary constant;
  - one authoritative value per institution (existing EligibilityEngine rules);
    rejected, conflicting and needs_review values are never ranked;
  - ties share a rank (1, 1, 3); institutions without an admissible value are
    listed in `unavailable` and never ranked;
  - heterogeneous currencies → status "needs_review", empty ranking, no conversion;
  - coverage = eligible / expected institutions, None when none is expected.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.country import Country
from app.models.institution import Institution
from scraping.rankings.definitions import RankableIndicator, get_indicator
from scraping.rankings.models import RankHistory, RankingEntry, RankingResult
from scraping.rankings.service import RankingService

router = APIRouter(prefix="/api/v1", tags=["rankings"])
ranking_service = RankingService()

# Public schema names (kept for the API contract / OpenAPI).
RankingResponse = RankingResult
__all__ = ["RankingEntry", "RankingResponse", "router"]

PeriodTypeQ = Literal["annual", "semi_annual", "quarterly"]
DataScopeQ = Literal["individual", "consolidated"]


def indicator_or_404(metric_code: str) -> RankableIndicator:
    indicator = get_indicator(metric_code)
    if indicator is None:
        raise HTTPException(status_code=404, detail=f"Rankable indicator '{metric_code}' not found")
    return indicator


async def institution_with_country(db: AsyncSession, institution_id: str) -> tuple[Institution, str]:
    row = (
        await db.execute(
            select(Institution, Country.code)
            .join(Country, Institution.country_id == Country.id)
            .where(Institution.id == institution_id, Institution.deleted_at.is_(None))
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return row[0], row[1]


@router.get("/rankings", summary="Descriptive ranking of institutions", response_model=RankingResult)
async def get_rankings(
    metric_code: str = Query(..., description="Rankable indicator: metric, growth_<metric> or ratio code"),
    period_year: int | None = Query(None, description="Fiscal year (default: latest year holding data)"),
    period_type: PeriodTypeQ = Query("annual", description="Period type (never mixed)"),
    data_scope: DataScopeQ = Query("individual", description="Accounting scope (never mixed)"),
    country_code: str | None = Query(None, description="ISO country code, or UMOA (default) for the 8 countries"),
    order: Literal["desc", "asc"] = Query("desc", description="Numerical order of the values"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> RankingResult:
    indicator = indicator_or_404(metric_code)
    return await ranking_service.rank(
        db,
        indicator,
        period_year=period_year,
        period_type=period_type,
        data_scope=data_scope,
        country_code=country_code,
        order=order,
        page=page,
        page_size=page_size,
    )


@router.get("/rankings/history", summary="Observed rank of an institution over time", response_model=RankHistory)
async def get_ranking_history(
    institution_id: str = Query(..., description="Institution ID"),
    metric_code: str = Query(..., description="Rankable indicator"),
    period_type: PeriodTypeQ = Query("annual"),
    data_scope: DataScopeQ = Query("individual"),
    country_code: str | None = Query(None, description="Ranking universe: ISO code or UMOA (default: institution's country)"),
    db: AsyncSession = Depends(get_db_session),
) -> RankHistory:
    indicator = indicator_or_404(metric_code)
    institution, own_country = await institution_with_country(db, institution_id)
    return await ranking_service.history(
        db,
        indicator,
        institution,
        period_type=period_type,
        data_scope=data_scope,
        country_code=(country_code or own_country).upper(),
    )
