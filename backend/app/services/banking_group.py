"""UMOA Banking Intelligence — Banking Group Service"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.banking_group import BankingGroup
from app.schemas.banking_group import BankingGroupList, BankingGroupRead
from app.schemas.common import PaginatedResponse


async def get_banking_groups(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
) -> PaginatedResponse[BankingGroupList]:
    """Return paginated list of banking groups."""
    query = select(BankingGroup).where(BankingGroup.deleted_at.is_(None))

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            BankingGroup.name.ilike(term) | BankingGroup.short_name.ilike(term)
        )

    query = query.order_by(BankingGroup.name)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[BankingGroupList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_banking_group_by_id(db: AsyncSession, group_id: str) -> BankingGroupRead | None:
    """Return a banking group by UUID with source details."""
    result = await db.execute(
        select(BankingGroup)
        .options(selectinload(BankingGroup.source))
        .where(BankingGroup.id == group_id, BankingGroup.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return BankingGroupRead.model_validate(row) if row else None
