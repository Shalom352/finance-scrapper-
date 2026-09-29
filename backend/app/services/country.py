"""
UMOA Banking Intelligence — Country Service

Query logic for countries.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.country import Country
from app.schemas.common import PaginatedResponse
from app.schemas.country import CountryList, CountryRead


async def get_countries(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    is_active: bool | None = None,
) -> PaginatedResponse[CountryList]:
    """Return paginated list of countries."""
    query = select(Country).where(Country.deleted_at.is_(None))

    if is_active is not None:
        query = query.where(Country.is_active == is_active)

    query = query.order_by(Country.name_fr)

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    # Paginate
    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[CountryList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_country_by_id(db: AsyncSession, country_id: str) -> CountryRead | None:
    """Return a country by UUID."""
    result = await db.execute(
        select(Country).where(Country.id == country_id, Country.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return CountryRead.model_validate(row) if row else None


async def get_country_by_code(db: AsyncSession, code: str) -> CountryRead | None:
    """Return a country by ISO code."""
    result = await db.execute(
        select(Country).where(Country.code == code.upper(), Country.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return CountryRead.model_validate(row) if row else None
