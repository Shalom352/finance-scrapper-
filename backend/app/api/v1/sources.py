"""UMOA Banking Intelligence — Source Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.source import SourceList, SourceRead
from app.services.source import get_source_by_id, get_sources

router = APIRouter(prefix="/api/v1", tags=["sources"])

@router.get("/sources", summary="List sources", response_model=PaginatedResponse[SourceList])
async def list_sources(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    source_type: str | None = Query(None, description="Filter by source type"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[SourceList]:
    return await get_sources(db, page=page, page_size=page_size, source_type=source_type, is_active=is_active)

@router.get("/sources/{source_id}", summary="Get source by ID", response_model=SourceRead)
async def get_source(
    source_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> SourceRead:
    result = await get_source_by_id(db, source_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return result
