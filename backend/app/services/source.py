"""UMOA Banking Intelligence — Source Service"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.source import Source
from app.schemas.common import PaginatedResponse
from app.schemas.source import SourceList, SourceRead


async def get_sources(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    source_type: str | None = None,
    is_active: bool | None = None,
) -> PaginatedResponse[SourceList]:
    """Return paginated list of sources."""
    query = select(Source).where(Source.deleted_at.is_(None))

    if source_type:
        query = query.where(Source.source_type == source_type)
    if is_active is not None:
        query = query.where(Source.is_active == is_active)

    query = query.order_by(Source.priority, Source.name)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[SourceList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_source_by_id(db: AsyncSession, source_id: str) -> SourceRead | None:
    """Return a source by UUID."""
    result = await db.execute(
        select(Source).where(Source.id == source_id, Source.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return SourceRead.model_validate(row) if row else None
