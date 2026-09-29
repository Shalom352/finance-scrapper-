"""UMOA Banking Intelligence — Metric Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.metric_definition import MetricList, MetricRead
from app.services.metric_definition import get_metric_by_code, get_metrics

router = APIRouter(prefix="/api/v1", tags=["metrics"])

@router.get("/metrics", summary="List metrics", response_model=PaginatedResponse[MetricList])
async def list_metrics(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    statement_type: str | None = Query(None, description="Filter by statement type"),
    category: str | None = Query(None, description="Filter by category"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    is_debt_related: bool | None = Query(None, description="Filter by debt related status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[MetricList]:
    return await get_metrics(
        db,
        page=page,
        page_size=page_size,
        statement_type=statement_type,
        category=category,
        is_active=is_active,
        is_debt_related=is_debt_related,
    )

@router.get("/metrics/{code}", summary="Get metric by code", response_model=MetricRead)
async def get_metric(
    code: str,
    db: AsyncSession = Depends(get_db_session),
) -> MetricRead:
    result = await get_metric_by_code(db, code)
    if result is None:
        raise HTTPException(status_code=404, detail="Metric not found")
    return result
