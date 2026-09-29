"""UMOA Banking Intelligence — Banking Group Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.banking_group import BankingGroupList, BankingGroupRead
from app.schemas.common import PaginatedResponse
from app.services.banking_group import get_banking_group_by_id, get_banking_groups

router = APIRouter(prefix="/api/v1", tags=["banking-groups"])

@router.get("/banking-groups", summary="List banking groups", response_model=PaginatedResponse[BankingGroupList])
async def list_banking_groups(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    search: str | None = Query(None, description="Search by name"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[BankingGroupList]:
    return await get_banking_groups(db, page=page, page_size=page_size, search=search)

@router.get("/banking-groups/{group_id}", summary="Get banking group by ID", response_model=BankingGroupRead)
async def get_banking_group(
    group_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> BankingGroupRead:
    result = await get_banking_group_by_id(db, group_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Banking Group not found")
    return result
