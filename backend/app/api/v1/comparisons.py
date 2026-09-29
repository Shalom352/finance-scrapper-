"""UMOA Banking Intelligence — Comparisons Router (Phase 9)

Factual, descriptive comparisons only (no ranking, no judgement):
  - GET /comparisons          : 2 to 5 institutions on one indicator;
  - GET /comparisons/sector   : institution vs its national sector total;
  - GET /comparisons/country  : country aggregate vs UMOA aggregate.
All values share the same indicator, period_year, period_type, data_scope and
currency; anything else is reported as needs_review / unavailable, never forced.
Sector and country comparisons follow the Phase 8C rule (individual + annual).
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.rankings import indicator_or_404, institution_with_country, ranking_service
from app.db.session import get_db_session
from app.models.country import Country
from app.models.institution import Institution
from scraping.rankings.models import CountryComparison, InstitutionsComparison, SectorComparison

router = APIRouter(prefix="/api/v1", tags=["comparisons"])

MIN_INSTITUTIONS = 2
MAX_INSTITUTIONS = 5


@router.get("/comparisons", summary="Compare 2 to 5 institutions", response_model=InstitutionsComparison)
async def compare_institutions(
    institution_ids: str = Query(..., description="Comma-separated institution IDs (2 to 5)"),
    metric_code: str = Query(..., description="Rankable indicator"),
    period_year: int | None = Query(None, description="Fiscal year (default: latest year holding data)"),
    period_type: Literal["annual", "semi_annual", "quarterly"] = Query("annual"),
    data_scope: Literal["individual", "consolidated"] = Query("individual"),
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionsComparison:
    ids = list(dict.fromkeys(i.strip() for i in institution_ids.split(",") if i.strip()))
    if not MIN_INSTITUTIONS <= len(ids) <= MAX_INSTITUTIONS:
        raise HTTPException(
            status_code=422, detail=f"Between {MIN_INSTITUTIONS} and {MAX_INSTITUTIONS} distinct institutions required"
        )
    indicator = indicator_or_404(metric_code)
    rows = (
        await db.execute(
            select(Institution, Country.code)
            .join(Country, Institution.country_id == Country.id)
            .where(Institution.id.in_(ids), Institution.deleted_at.is_(None))
        )
    ).all()
    found = {inst.id: (inst, code) for inst, code in rows}
    missing = [i for i in ids if i not in found]
    if missing:
        raise HTTPException(status_code=404, detail=f"Institution(s) not found: {', '.join(missing)}")
    return await ranking_service.compare_institutions(
        db,
        indicator,
        [found[i] for i in ids],
        period_year=period_year,
        period_type=period_type,
        data_scope=data_scope,
    )


@router.get("/comparisons/sector", summary="Institution vs national sector", response_model=SectorComparison)
async def compare_institution_to_sector(
    institution_id: str = Query(...),
    metric_code: str = Query(..., description="Published metric (aggregatable)"),
    period_year: int | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> SectorComparison:
    indicator = indicator_or_404(metric_code)
    institution, country_code = await institution_with_country(db, institution_id)
    return await ranking_service.institution_vs_sector(
        db, indicator, institution, country_code, period_year=period_year
    )


@router.get("/comparisons/country", summary="Country vs UMOA", response_model=CountryComparison)
async def compare_country_to_umoa(
    country_code: str = Query(..., min_length=2, max_length=2),
    metric_code: str = Query(..., description="Published metric (aggregatable)"),
    period_year: int | None = Query(None),
    db: AsyncSession = Depends(get_db_session),
) -> CountryComparison:
    indicator = indicator_or_404(metric_code)
    exists = await db.scalar(select(Country.id).where(Country.code == country_code.upper()))
    if exists is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return await ranking_service.country_vs_umoa(db, indicator, country_code.upper(), period_year=period_year)
