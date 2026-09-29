"""UMOA Banking Intelligence — Metric Definition Service

Query logic for metric definitions.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.metric_definition import MetricDefinition
from app.schemas.common import PaginatedResponse
from app.schemas.metric_definition import MetricList, MetricRead


async def get_metrics(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    statement_type: str | None = None,
    category: str | None = None,
    is_active: bool | None = None,
    is_debt_related: bool | None = None,
) -> PaginatedResponse[MetricList]:
    query = select(MetricDefinition).where(MetricDefinition.deleted_at.is_(None))

    if statement_type:
        query = query.where(MetricDefinition.statement_type == statement_type)

    if category:
        query = query.where(MetricDefinition.category == category)

    if is_active is not None:
        query = query.where(MetricDefinition.is_active == is_active)

    if is_debt_related is not None:
        query = query.where(MetricDefinition.is_debt_related == is_debt_related)

    query = query.order_by(MetricDefinition.display_order)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[MetricList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_metric_by_code(db: AsyncSession, code: str) -> MetricRead | None:
    result = await db.execute(
        select(MetricDefinition)
        .where(MetricDefinition.code == code, MetricDefinition.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return MetricRead.model_validate(row) if row else None
