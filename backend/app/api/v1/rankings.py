"""UMOA Banking Intelligence — Rankings Router

Provides GET /api/v1/rankings for multicriteria rankings.

CRITICAL RULES:
  - Only data with status = 'verified' may appear.
  - Heterogeneous currencies trigger a 400 rejection.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import desc, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.metric_definition import MetricDefinition

router = APIRouter(prefix="/api/v1", tags=["rankings"])


class RankingEntry(BaseModel):
    rank: int
    institution_id: str
    institution_name: str
    country_code: str | None = None
    value_normalized: float
    unit_normalized: str | None = None
    currency_normalized: str | None = None
    period_year: int
    scope: str

    model_config = {"from_attributes": True}


class RankingResponse(BaseModel):
    items: list[RankingEntry]
    total: int
    page: int
    page_size: int
    has_next: bool
    has_prev: bool
    metric_code: str
    metric_label_fr: str
    metric_label_en: str | None = None
    currency: str | None = None
    period_year: int | None = None


@router.get("/rankings", summary="Get rankings", response_model=RankingResponse)
async def get_rankings(
    metric_code: str = Query(..., description="Metric code to rank by (REQUIRED)"),
    period_year: int | None = Query(None, description="Filter by period year"),
    country_code: str | None = Query(None, description="Filter by country code"),
    scope: str | None = Query(None, description="Filter by scope"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> RankingResponse:
    # 1. Validate metric_code exists
    metric = await db.scalar(
        select(MetricDefinition).where(
            MetricDefinition.code == metric_code,
            MetricDefinition.deleted_at.is_(None),
        )
    )
    if not metric:
        raise HTTPException(status_code=404, detail="Metric not found")

    # 2. Build base filter for verified data
    base_filter = [
        FinancialData.metric_code == metric_code,
        FinancialData.status == "verified",
        FinancialData.deleted_at.is_(None),
        FinancialData.value_normalized.isnot(None),
    ]
    if period_year is not None:
        base_filter.append(FinancialData.period_year == period_year)
    if scope is not None:
        base_filter.append(FinancialData.scope == scope)

    # 3. Check currency homogeneity before returning data
    currency_q = select(distinct(FinancialData.currency_normalized)).where(*base_filter)
    if country_code:
        currency_q = (
            currency_q
            .join(Institution, FinancialData.institution_id == Institution.id)
            .join(Country, Institution.country_id == Country.id)
            .where(Country.code == country_code.upper())
        )
    currency_result = (await db.execute(currency_q)).scalars().all()
    currencies = [c for c in currency_result if c is not None]

    if len(currencies) > 1:
        raise HTTPException(
            status_code=400,
            detail=f"Heterogeneous currencies found ({', '.join(sorted(currencies))}). "
                   f"Add a currency filter to compare homogeneous values.",
        )

    currency = currencies[0] if currencies else None

    # 4. Build ranked query with joins
    stmt = (
        select(FinancialData, Institution, Country)
        .join(Institution, FinancialData.institution_id == Institution.id)
        .join(Country, Institution.country_id == Country.id)
        .where(*base_filter, Institution.deleted_at.is_(None))
    )
    if country_code:
        stmt = stmt.where(Country.code == country_code.upper())

    stmt = stmt.order_by(desc(FinancialData.value_normalized))

    # 5. Count total
    count_q = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_q)).scalar_one()

    if total == 0:
        return RankingResponse(
            items=[],
            total=0,
            page=page,
            page_size=page_size,
            has_next=False,
            has_prev=False,
            metric_code=metric_code,
            metric_label_fr=metric.label_fr,
            metric_label_en=metric.label_en,
            currency=currency,
            period_year=period_year,
        )

    # 6. Paginate and build ranking entries
    offset = (page - 1) * page_size
    result = await db.execute(stmt.offset(offset).limit(page_size))
    rows = result.all()

    items = [
        RankingEntry(
            rank=offset + idx + 1,
            institution_id=inst.id,
            institution_name=inst.name_commercial or inst.name_official,
            country_code=country.code,
            value_normalized=float(fd.value_normalized),
            unit_normalized=fd.unit_normalized,
            currency_normalized=fd.currency_normalized,
            period_year=fd.period_year,
            scope=fd.scope,
        )
        for idx, (fd, inst, country) in enumerate(rows)
    ]

    return RankingResponse(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
        metric_code=metric_code,
        metric_label_fr=metric.label_fr,
        metric_label_en=metric.label_en,
        currency=currency,
        period_year=period_year,
    )
