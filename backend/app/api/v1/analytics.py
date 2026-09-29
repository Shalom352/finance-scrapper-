"""
UMOA Banking Intelligence — Analytics REST API Router

Endpoints for on-demand calculation of financial ratios, YoY growth rates,
sector aggregations, and comparative market analysis.
"""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.analytics import (
    ComparisonResponse,
    GrowthResponse,
    RatioDefinitionResponse,
    RatioResponse,
    SectorAggregationResponse,
    SectorStructureResponse,
)
from app.schemas.common import PaginatedResponse
from scraping.analytics.analytics_service import AnalyticsService
from scraping.analytics.ratio_calculator import RATIO_DEFINITIONS

router = APIRouter(prefix="/api/v1/analytics", tags=["analytics"])
analytics_service = AnalyticsService()


@router.get(
    "/definitions",
    response_model=list[RatioDefinitionResponse],
    summary="List official ratio definitions",
    description="Returns the catalogue of all supported banking ratios, their formulas, and eligibility rules.",
)
async def list_ratio_definitions() -> list[RatioDefinitionResponse]:
    """Retrieve the official catalogue of financial ratios."""
    return [RatioDefinitionResponse.model_validate(d) for d in RATIO_DEFINITIONS.values()]


@router.get(
    "/ratios",
    response_model=PaginatedResponse[RatioResponse],
    summary="Get calculated banking ratios",
    description="Calculate and return banking ratios with full provenance, currency consistency, and status.",
)
async def get_ratios(
    institution_id: str | None = Query(None, description="Filter by unique institution ID"),
    country_code: str | None = Query(None, description="Filter by 2-letter ISO country code (e.g. CI, SN)"),
    ratio_code: str | None = Query(None, description="Filter by ratio code (ROA, ROE, DEPOTS_ACTIFS, CREDITS_DEPOTS, DETTES_ACTIFS, COST_TO_INCOME)"),
    year: int | None = Query(None, description="Filter by fiscal year"),
    status: str | None = Query(None, description="Filter by status (calculated, calculated_from_verified, needs_review, unavailable)"),
    data_scope: Literal["individual", "consolidated"] = Query(
        "individual", description="Accounting scope (never mixed): individual or consolidated"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[RatioResponse]:
    """Retrieve banking ratios calculated on-demand."""
    offset = (page - 1) * page_size
    items, total = await analytics_service.get_ratios(
        db,
        institution_id=institution_id,
        country_code=country_code,
        ratio_code=ratio_code,
        year=year,
        status=status,
        data_scope=data_scope,
        limit=page_size,
        offset=offset,
    )

    return PaginatedResponse(
        items=[RatioResponse.model_validate(r) for r in items],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


@router.get(
    "/growth",
    response_model=PaginatedResponse[GrowthResponse],
    summary="Get annual growth rates (YoY)",
    description="Calculate year-over-year variation for core financial metrics with absolute and percentage changes.",
)
async def get_growth(
    institution_id: str | None = Query(None, description="Filter by unique institution ID"),
    country_code: str | None = Query(None, description="Filter by country code"),
    metric_code: str | None = Query(None, description="Filter by metric code (e.g. total_actifs, depots_clients, resultat_net)"),
    year: int | None = Query(None, description="Filter by fiscal year (current year t)"),
    status: str | None = Query(None, description="Filter by calculation status"),
    data_scope: Literal["individual", "consolidated"] = Query(
        "individual", description="Accounting scope (never mixed): individual or consolidated"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[GrowthResponse]:
    """Retrieve annual growth indicators calculated on-demand."""
    offset = (page - 1) * page_size
    items, total = await analytics_service.get_growth(
        db,
        institution_id=institution_id,
        country_code=country_code,
        metric_code=metric_code,
        year=year,
        status=status,
        data_scope=data_scope,
        limit=page_size,
        offset=offset,
    )

    return PaginatedResponse(
        items=[GrowthResponse.model_validate(g) for g in items],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


@router.get(
    "/aggregations",
    response_model=list[SectorAggregationResponse],
    summary="Get sector aggregations (Country & UMOA)",
    description="Calculate country and regional sector totals with strict institutional deduplication and coverage tracking.",
)
async def get_aggregations(
    year: int = Query(..., description="Fiscal year (REQUIRED)"),
    metric_code: str = Query("total_actifs", description="Metric code to aggregate"),
    country_code: str | None = Query(None, description="Filter by country code"),
    scope: str = Query("country", description="Aggregation scope: 'country' or 'umoa'"),
    include_needs_review: bool = Query(False, description="Whether to include unverified 'needs_review' observations"),
    db: AsyncSession = Depends(get_db_session),
) -> list[SectorAggregationResponse]:
    """Retrieve sector aggregates at country or regional UMOA level."""
    results = await analytics_service.get_aggregations(
        db,
        year=year,
        metric_code=metric_code,
        country_code=country_code,
        scope=scope,
        include_needs_review=include_needs_review,
    )
    return [SectorAggregationResponse.model_validate(r) for r in results]


@router.get(
    "/sector",
    response_model=SectorStructureResponse,
    summary="Get national sector structure & market shares",
    description="Returns national sector total and institution market shares for a specific metric and year.",
)
async def get_sector_structure(
    country_code: str = Query(..., description="ISO 2-letter country code (REQUIRED)"),
    year: int = Query(..., description="Fiscal year (REQUIRED)"),
    metric_code: str = Query("depots_clients", description="Metric for market share analysis (default: depots_clients)"),
    db: AsyncSession = Depends(get_db_session),
) -> SectorStructureResponse:
    """Retrieve sector structure and institution market shares."""
    sec_agg, market_shares = await analytics_service.get_sector_structure(
        db,
        country_code=country_code,
        year=year,
        metric_code=metric_code,
    )

    if not sec_agg:
        raise HTTPException(
            status_code=404,
            detail=f"No data or institutions found for country '{country_code}' in year {year}",
        )

    return SectorStructureResponse(
        aggregation=SectorAggregationResponse.model_validate(sec_agg),
        market_shares=market_shares,
    )


@router.get(
    "/compare",
    response_model=ComparisonResponse,
    summary="Factual comparative analysis",
    description="Compare two institutions, or an institution against its country, or a country against UMOA.",
)
async def compare_entities(
    comparison_type: str = Query(
        "institution_vs_institution",
        description="Type: 'institution_vs_institution', 'country_vs_umoa'",
    ),
    entity_a: str = Query(..., description="First entity identifier (bank ID or ISO country code)"),
    entity_b: str = Query(..., description="Second entity identifier (bank ID or 'UMOA')"),
    metric_or_ratio: str = Query(..., description="Metric code or ratio code to compare"),
    year: int = Query(..., description="Fiscal year"),
    data_scope: Literal["individual", "consolidated"] = Query(
        "individual", description="Accounting scope (never mixed): individual or consolidated"
    ),
    db: AsyncSession = Depends(get_db_session),
) -> ComparisonResponse:
    """Perform a factual comparison between financial entities."""
    result = await analytics_service.compare_entities(
        db,
        comparison_type=comparison_type,
        entity_a=entity_a,
        entity_b=entity_b,
        metric_or_ratio=metric_or_ratio,
        year=year,
        data_scope=data_scope,
    )
    return ComparisonResponse.model_validate(result)
