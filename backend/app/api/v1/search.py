"""UMOA Banking Intelligence — Search Router

Global search (top bar). Every word of the query must appear (any order, accents, case and punctuation
ignored): "Ecobank Côte d'Ivoire" finds "ECOBANK - CÔTE D'IVOIRE". Institutions are also found by their
acronyms and former names (Entity Hub), deals by title, ISIN, project and participant. Each type has its
own real total and page; results are in a stable, descriptive order (exact name first), never a score.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session
from app.db.text_search import all_words, query_words, rank
from app.models.banking_group import BankingGroup
from app.models.country import Country
from app.models.deal import Deal, DealParticipant
from app.models.discovery import DocumentEntity, EntityName
from app.models.document import Document
from app.models.entity import Entity
from app.models.institution import Institution
from app.models.source import Source
from app.schemas.banking_group import BankingGroupList
from app.schemas.document import DocumentList
from app.schemas.institution import InstitutionList
from app.schemas.source import SourceList

router = APIRouter(prefix="/api/v1", tags=["search"])

UMOA_CODES = frozenset({"BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"})
SEARCH_TYPES = ("institutions", "deals", "banking_groups", "sources", "documents")
MIN_QUERY_LENGTH = 2


class DealHit(BaseModel):
    id: str
    title: str
    isin: str | None = None
    deal_type: str | None = None
    status: str
    country_code: str | None = None


class SearchTotals(BaseModel):
    institutions: int = 0
    deals: int = 0
    banking_groups: int = 0
    sources: int = 0
    documents: int = 0


class SearchResults(BaseModel):
    query: str
    total: int  # sum of the real totals per type (not of the page lengths)
    totals: SearchTotals
    institutions: list[InstitutionList]
    deals: list[DealHit]
    banking_groups: list[BankingGroupList]
    sources: list[SourceList]
    documents: list[DocumentList]


async def _page(db: AsyncSession, stmt, order, offset: int, limit: int) -> tuple[list, int]:
    total = (await db.execute(select(func.count()).select_from(stmt.order_by(None).subquery()))).scalar_one()
    rows = (await db.execute(stmt.order_by(*order).offset(offset).limit(limit))).scalars().all()
    return list(rows), total


@router.get("/search", summary="Global search", response_model=SearchResults)
async def search(
    q: str = Query(..., min_length=1, max_length=200, description="Search query (REQUIRED, 2 characters at least)"),
    types: str | None = Query(None, description=f"Comma-separated types to search ({','.join(SEARCH_TYPES)})"),
    page: int = Query(1, ge=1, description="Page number (applied to each type)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page and per type"),
    db: AsyncSession = Depends(get_db_session),
) -> SearchResults:
    query = q.strip()
    if len(query) < MIN_QUERY_LENGTH or not query_words(query):
        raise HTTPException(status_code=422, detail=f"query must contain at least {MIN_QUERY_LENGTH} characters")
    search_types = [t.strip() for t in types.split(",")] if types else list(SEARCH_TYPES)
    offset = (page - 1) * page_size
    totals = SearchTotals()
    results = SearchResults(query=query, total=0, totals=totals, institutions=[], deals=[], banking_groups=[],
                            sources=[], documents=[])

    if "institutions" in search_types:
        by_alias = select(Institution.id).join(EntityName, EntityName.entity_id == Institution.entity_id).where(
            all_words([EntityName.name], query))
        # A UMOA country code written with the name ("ECOBANK-CI", "orabank tg") designates the
        # institution's country: the other words are matched on the names (search retest of 22/10/2026).
        words = query_words(query)
        codes = {w.upper() for w in words if w.upper() in UMOA_CODES}
        names_query = " ".join(w for w in words if w.upper() not in UMOA_CODES)
        by_name = or_(all_words([Institution.name_official, Institution.name_commercial], query), Institution.id.in_(by_alias))
        if codes and names_query:
            in_country = Institution.country_id.in_(select(Country.id).where(Country.code.in_(codes)))
            by_name = or_(by_name, and_(all_words([Institution.name_official, Institution.name_commercial], names_query),
                                        in_country))
        stmt = select(Institution).where(Institution.deleted_at.is_(None), by_name)
        rows, totals.institutions = await _page(
            db, stmt, (rank(Institution.name_official, query), Institution.name_official, Institution.id),
            offset, page_size)
        results.institutions = [InstitutionList.model_validate(i) for i in rows]

    if "deals" in search_types:
        by_party = select(DealParticipant.deal_id).where(
            DealParticipant.deleted_at.is_(None), all_words([DealParticipant.participant_name], query))
        isin = "".join(character for character in query if character.isalnum()).upper()
        stmt = select(Deal).where(
            Deal.deleted_at.is_(None),
            Deal.merged_into_deal_id.is_(None),
            Deal.status != "rejected",
            or_(Deal.isin == isin, all_words([Deal.title, Deal.project_name], query), Deal.id.in_(by_party)),
        )
        # The exact ISIN first, then the most recent deals (a search is usually about current operations).
        recent = func.coalesce(Deal.value_date, Deal.signing_date, Deal.announcement_date)
        rows, totals.deals = await _page(db, stmt, ((Deal.isin == isin).desc(), recent.desc().nulls_last(), Deal.title,
                                                    Deal.id), offset, page_size)
        codes = dict((await db.execute(select(Country.id, Country.code).where(
            Country.id.in_({d.country_id for d in rows if d.country_id})))).all()) if rows else {}
        results.deals = [DealHit(id=d.id, title=d.title, isin=d.isin, deal_type=d.deal_type, status=d.status,
                                 country_code=codes.get(d.country_id)) for d in rows]

    if "banking_groups" in search_types:
        stmt = select(BankingGroup).where(
            BankingGroup.deleted_at.is_(None), all_words([BankingGroup.name, BankingGroup.short_name], query))
        rows, totals.banking_groups = await _page(
            db, stmt, (rank(BankingGroup.name, query), BankingGroup.name, BankingGroup.id), offset, page_size)
        results.banking_groups = [BankingGroupList.model_validate(bg) for bg in rows]

    if "sources" in search_types:
        stmt = select(Source).where(
            Source.deleted_at.is_(None), all_words([Source.name, Source.short_name, Source.publisher], query))
        rows, totals.sources = await _page(db, stmt, (rank(Source.name, query), Source.name, Source.id),
                                           offset, page_size)
        results.sources = [SourceList.model_validate(s) for s in rows]

    if "documents" in search_types:
        words = query_words(query)
        codes = {word.upper() for word in words if word.upper() in UMOA_CODES}
        years = {int(word) for word in words if word.isdigit() and 1900 <= int(word) <= 2100}
        text_words = [word for word in words if word.upper() not in codes and word not in {str(y) for y in years}]
        document_filters = []

        # Each word may match a different piece of document metadata: title, type, linked bank/entity,
        # label in a regulatory PDF, or publisher. This also supports queries such as "Ecobank 2023".
        for word in text_words:
            institution_match = all_words([Institution.name_official, Institution.name_commercial], word)
            if codes:
                institution_match = and_(
                    institution_match,
                    Institution.country_id.in_(select(Country.id).where(Country.code.in_(codes))),
                )
            by_institution = select(Institution.id).where(Institution.deleted_at.is_(None), institution_match)

            entity_match = all_words([EntityName.name], word)
            if codes:
                entity_ids_in_country = select(Entity.id).where(
                    Entity.country_id.in_(select(Country.id).where(Country.code.in_(codes)))
                )
                entity_match = and_(entity_match, EntityName.entity_id.in_(entity_ids_in_country))
            by_entity_name = select(EntityName.entity_id).where(entity_match)
            by_entity_document = select(DocumentEntity.document_id).where(
                DocumentEntity.deleted_at.is_(None), DocumentEntity.entity_id.in_(by_entity_name)
            )
            by_document_label = select(DocumentEntity.document_id).where(
                DocumentEntity.deleted_at.is_(None), all_words([DocumentEntity.label_in_document], word)
            )
            by_source = select(Source.id).where(
                Source.deleted_at.is_(None), all_words([Source.name, Source.short_name, Source.publisher], word)
            )
            document_filters.append(
                or_(
                    all_words([Document.title, Document.document_type], word),
                    Document.institution_id.in_(by_institution),
                    Document.entity_id.in_(by_entity_name),
                    Document.id.in_(by_entity_document),
                    Document.id.in_(by_document_label),
                    Document.source_id.in_(by_source),
                )
            )

        if years:
            # Use the stated reporting/covered year; title and linked labels are a fallback when
            # the source did not provide structured year metadata.
            year_title_matches = [all_words([Document.title], str(year)) for year in years]
            year_label_matches = [
                Document.id.in_(
                    select(DocumentEntity.document_id).where(
                        DocumentEntity.deleted_at.is_(None),
                        all_words([DocumentEntity.label_in_document], str(year)),
                    )
                )
                for year in years
            ]
            document_filters.append(
                or_(
                    Document.period_year.in_(years),
                    Document.reporting_year.in_(years),
                    *year_title_matches,
                    *year_label_matches,
                )
            )

        if codes:
            entities_in_country = select(Entity.id).where(
                Entity.country_id.in_(select(Country.id).where(Country.code.in_(codes)))
            )
            country_document_links = select(DocumentEntity.document_id).join(
                Entity, Entity.id == DocumentEntity.entity_id
            ).where(
                DocumentEntity.deleted_at.is_(None), Entity.country_id.in_(select(Country.id).where(Country.code.in_(codes)))
            )
            document_filters.append(
                or_(
                    Document.institution_id.in_(
                        select(Institution.id).where(
                            Institution.deleted_at.is_(None),
                            Institution.country_id.in_(select(Country.id).where(Country.code.in_(codes))),
                        )
                    ),
                    Document.entity_id.in_(entities_in_country),
                    Document.id.in_(country_document_links),
                    Document.source_id.in_(select(Source.id).where(Source.country_code.in_(codes))),
                )
            )

        stmt = select(Document).where(Document.deleted_at.is_(None), *document_filters)
        rows, totals.documents = await _page(
            db, stmt, (Document.period_year.desc().nulls_last(), Document.title, Document.id), offset, page_size)
        linked_entity_ids = {d.entity_id for d in rows if d.entity_id}
        institution_by_entity = dict((await db.execute(select(Institution.entity_id, Institution.id).where(
            Institution.entity_id.in_(linked_entity_ids), Institution.deleted_at.is_(None)))).all()) \
            if linked_entity_ids else {}
        results.documents = [
            DocumentList.model_validate(d).model_copy(update={
                "institution_id": d.institution_id or institution_by_entity.get(d.entity_id),
            })
            for d in rows
        ]
    results.total = sum(totals.model_dump().values())
    return results
