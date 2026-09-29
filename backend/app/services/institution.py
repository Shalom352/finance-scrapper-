"""UMOA Banking Intelligence — Institution Service

Query logic for institutions.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.country import Country
from app.models.institution import Institution
from app.schemas.common import PaginatedResponse
from app.schemas.institution import InstitutionList, InstitutionRead


async def get_institutions(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    search: str | None = None,
    country_code: str | None = None,
    banking_group_id: str | None = None,
    institution_type: str | None = None,
    status: str | None = None,
) -> PaginatedResponse[InstitutionList]:
    query = select(Institution).where(Institution.deleted_at.is_(None))

    if search:
        term = f"%{search.lower()}%"
        query = query.where(
            Institution.name_official.ilike(term) | Institution.name_commercial.ilike(term)
        )

    if country_code:
        query = query.join(Institution.country).where(Country.code == country_code.upper())

    if banking_group_id:
        query = query.where(Institution.banking_group_id == banking_group_id)

    if institution_type:
        query = query.where(Institution.institution_type == institution_type)

    if status:
        query = query.where(Institution.status == status)

    query = query.order_by(Institution.name_official)

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    query = query.options(
        selectinload(Institution.country),
        selectinload(Institution.banking_group)
    )
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[InstitutionList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_institution_by_id(db: AsyncSession, institution_id: str) -> InstitutionRead | None:
    result = await db.execute(
        select(Institution)
        .options(
            selectinload(Institution.country),
            selectinload(Institution.banking_group),
            selectinload(Institution.source),
        )
        .where(Institution.id == institution_id, Institution.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return InstitutionRead.model_validate(row) if row else None
