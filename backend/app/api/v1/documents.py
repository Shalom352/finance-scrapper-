"""UMOA Banking Intelligence — Document Router"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.schemas.common import PaginatedResponse
from app.schemas.document import DocumentList, DocumentRead
from app.services.document import get_document_by_id, get_documents

router = APIRouter(prefix="/api/v1", tags=["documents"])

@router.get("/documents", summary="List documents", response_model=PaginatedResponse[DocumentList])
async def list_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    institution_id: str | None = Query(None, description="Filter by institution ID"),
    source_id: str | None = Query(None, description="Filter by source ID"),
    document_type: str | None = Query(None, description="Filter by document type"),
    period_year: int | None = Query(None, description="Filter by period year"),
    download_status: str | None = Query(None, description="Filter by download status"),
    extraction_status: str | None = Query(None, description="Filter by extraction status"),
    db: AsyncSession = Depends(get_db_session),
) -> PaginatedResponse[DocumentList]:
    return await get_documents(
        db,
        page=page,
        page_size=page_size,
        institution_id=institution_id,
        source_id=source_id,
        document_type=document_type,
        period_year=period_year,
        download_status=download_status,
        extraction_status=extraction_status,
    )

@router.get("/documents/{document_id}", summary="Get document by ID", response_model=DocumentRead)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> DocumentRead:
    result = await get_document_by_id(db, document_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Document not found")
    return result
