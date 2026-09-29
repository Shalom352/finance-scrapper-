"""UMOA Banking Intelligence — Search Router"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.models.banking_group import BankingGroup
from app.models.document import Document
from app.models.institution import Institution
from app.models.source import Source
from app.schemas.banking_group import BankingGroupList
from app.schemas.document import DocumentList
from app.schemas.institution import InstitutionList
from app.schemas.source import SourceList

router = APIRouter(prefix="/api/v1", tags=["search"])

class SearchResults(BaseModel):
    query: str
    total: int
    institutions: list[InstitutionList]
    banking_groups: list[BankingGroupList]
    sources: list[SourceList]
    documents: list[DocumentList]

@router.get("/search", summary="Global search", response_model=SearchResults)
async def search(
    q: str = Query(..., min_length=1, description="Search query (REQUIRED)"),
    types: str | None = Query(None, description="Comma-separated types to search (institutions,banking_groups,sources,documents)"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db_session),
) -> SearchResults:
    search_types = types.split(",") if types else ["institutions", "banking_groups", "sources", "documents"]
    search_term = f"%{q}%"

    results = SearchResults(
        query=q,
        total=0,
        institutions=[],
        banking_groups=[],
        sources=[],
        documents=[],
    )

    offset = (page - 1) * page_size

    if "institutions" in search_types:
        stmt = select(Institution).where(
            Institution.deleted_at.is_(None),
            or_(
                Institution.name_official.ilike(search_term),
                Institution.name_commercial.ilike(search_term)
            )
        ).limit(page_size).offset(offset)
        res = await db.execute(stmt)
        insts = res.scalars().all()
        results.institutions = [InstitutionList.model_validate(i) for i in insts]
        results.total += len(insts)

    if "banking_groups" in search_types:
        stmt = select(BankingGroup).where(
            BankingGroup.deleted_at.is_(None),
            or_(
                BankingGroup.name.ilike(search_term),
                BankingGroup.short_name.ilike(search_term)
            )
        ).limit(page_size).offset(offset)
        res = await db.execute(stmt)
        bgs = res.scalars().all()
        results.banking_groups = [BankingGroupList.model_validate(bg) for bg in bgs]
        results.total += len(bgs)

    if "sources" in search_types:
        stmt = select(Source).where(
            Source.deleted_at.is_(None),
            or_(
                Source.name.ilike(search_term),
                Source.short_name.ilike(search_term),
                Source.publisher.ilike(search_term)
            )
        ).limit(page_size).offset(offset)
        res = await db.execute(stmt)
        srcs = res.scalars().all()
        results.sources = [SourceList.model_validate(s) for s in srcs]
        results.total += len(srcs)

    if "documents" in search_types:
        stmt = select(Document).where(
            Document.deleted_at.is_(None),
            Document.title.ilike(search_term)
        ).limit(page_size).offset(offset)
        res = await db.execute(stmt)
        docs = res.scalars().all()
        results.documents = [DocumentList.model_validate(d) for d in docs]
        results.total += len(docs)

    return results
