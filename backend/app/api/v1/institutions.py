"""UMOA Banking Intelligence — Institution Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.institution import InstitutionList, InstitutionRead
from app.services.institution import get_institution_by_id, get_institutions

router = APIRouter(prefix="/api/v1", tags=["institutions"])

@router.get("/institutions", summary="List institutions", response_model=PaginatedResponse[InstitutionList])
async def list_institutions(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search term"),
    country_code: str | None = Query(None, description="Filter by country code"),
    banking_group_id: str | None = Query(None, description="Filter by banking group ID"),
    institution_type: str | None = Query(None, description="Filter by institution type"),
    status: str | None = Query(None, description="Filter by status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[InstitutionList]:
    return await get_institutions(
        db,
        page=page,
        page_size=page_size,
        search=search,
        country_code=country_code,
        banking_group_id=banking_group_id,
        institution_type=institution_type,
        status=status,
    )

@router.get("/institutions/{institution_id}", summary="Get institution by ID", response_model=InstitutionRead)
async def get_institution(
    institution_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> InstitutionRead:
    result = await get_institution_by_id(db, institution_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Institution not found")
    return result
