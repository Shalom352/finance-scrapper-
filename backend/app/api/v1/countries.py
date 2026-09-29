"""UMOA Banking Intelligence — Country Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.country import CountryList, CountryRead
from app.services.country import get_countries, get_country_by_id

router = APIRouter(prefix="/api/v1", tags=["countries"])

@router.get("/countries", summary="List countries", response_model=PaginatedResponse[CountryList])
async def list_countries(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[CountryList]:
    return await get_countries(db, page=page, page_size=page_size, is_active=is_active)

@router.get("/countries/{country_id}", summary="Get country by ID", response_model=CountryRead)
async def get_country(
    country_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> CountryRead:
    result = await get_country_by_id(db, country_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return result
