"""UMOA Banking Intelligence — Document Service

Query logic for documents.
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.document import Document
from app.schemas.common import PaginatedResponse
from app.schemas.document import DocumentList, DocumentRead


async def get_documents(
    db: AsyncSession,
    *,
    page: int = 1,
    page_size: int = 20,
    institution_id: str | None = None,
    source_id: str | None = None,
    document_type: str | None = None,
    period_year: int | None = None,
    download_status: str | None = None,
    extraction_status: str | None = None,
) -> PaginatedResponse[DocumentList]:
    query = select(Document).where(Document.deleted_at.is_(None))

    if institution_id:
        query = query.where(Document.institution_id == institution_id)

    if source_id:
        query = query.where(Document.source_id == source_id)

    if document_type:
        query = query.where(Document.document_type == document_type)

    if period_year is not None:
        query = query.where(Document.period_year == period_year)

    if download_status:
        query = query.where(Document.download_status == download_status)

    if extraction_status:
        query = query.where(Document.extraction_status == extraction_status)

    query = query.order_by(Document.created_at.desc())

    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar_one()

    offset = (page - 1) * page_size
    rows = (await db.execute(query.offset(offset).limit(page_size))).scalars().all()

    return PaginatedResponse(
        items=[DocumentList.model_validate(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        has_next=offset + page_size < total,
        has_prev=page > 1,
    )


async def get_document_by_id(db: AsyncSession, document_id: str) -> DocumentRead | None:
    result = await db.execute(
        select(Document)
        .options(
            selectinload(Document.source),
            selectinload(Document.institution),
        )
        .where(Document.id == document_id, Document.deleted_at.is_(None))
    )
    row = result.scalar_one_or_none()
    return DocumentRead.model_validate(row) if row else None
