"""UMOA Financial Intelligence — Targeting & mandates router (Phase 20). Read-only.

``GET /api/v1/targeting``: for a deal profile (country, sector, type, amount, currency), the banks
and institutions with EXPLICIT criteria (presence, experience, indicative capacity, relationship,
via SGI). No score, no recommendation: each criterion is met / not_met / unknown with its evidence.
``GET /api/v1/mandates``: TOMASTEED's internal mandates and the institutions approached.
"""
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.constants.deals import DEAL_TYPES, ISO_4217_CURRENCIES, SECTORS
from app.db.session import get_db_session
from app.models.country import Country
from app.models.mandate import Mandate
from scraping.targeting.service import DEFAULT_CAPACITY_RATIO, TargetingRequest, find_candidates

router = APIRouter(prefix="/api/v1", tags=["targeting"])

SectorQ = Literal[SECTORS]  # type: ignore[valid-type]
DealTypeQ = Literal[DEAL_TYPES]  # type: ignore[valid-type]


class CandidateRead(BaseModel):
    kind: str
    id: str
    name: str
    country_code: str | None = None
    entity_type: str | None = None
    website: str | None = None
    criteria_met: int
    criteria_known: int
    criteria: dict[str, dict[str, Any]]


class TargetingResponse(BaseModel):
    request: dict[str, Any]
    method: str
    total: int
    items: list[CandidateRead]


class CounterpartyRead(BaseModel):
    id: str
    counterparty_name: str
    institution_id: str | None = None
    entity_id: str | None = None
    stage: str
    amount: Decimal | None = None
    currency: str | None = None
    contact_date: date | None = None
    reason: str | None = None
    notes: str | None = None


class MandateRead(BaseModel):
    id: str
    code: str
    title: str
    client_name: str
    country_code: str | None = None
    sector: str | None = None
    deal_type: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    maturity_months: int | None = None
    year: int | None = None
    status: str
    notes: str | None = None
    counterparties: list[CounterpartyRead]


METHOD = (
    "Critères explicites, sans score : présence (agrément dans le pays / transaction dans le pays), expérience "
    "(rôles de financement nommés dans des transactions comparables : même secteur, type ou pays), capacité "
    "indicative (part des capitaux propres publiés, même devise, aucune conversion ; la norme UMOA porte sur les "
    "fonds propres effectifs, non publiés), relation TOMASTEED (mandats), filiale SGI documentée. Ordre : "
    "nombre de critères satisfaits, puis transactions comparables, puis nom."
)


@router.get("/targeting", summary="Banks and institutions to approach for a deal profile",
            response_model=TargetingResponse)
async def targeting(
    country: str | None = Query(None, pattern=r"^[A-Z]{2}$"),
    sector: SectorQ | None = Query(None),
    deal_type: DealTypeQ | None = Query(None),
    amount: Decimal | None = Query(None, gt=0, description="Amount in units of the currency"),
    currency: str | None = Query(None, pattern=r"^[A-Z]{3}$"),
    kind: Literal["all", "banks", "institutions"] = Query("all"),
    capacity_ratio: Decimal = Query(DEFAULT_CAPACITY_RATIO, gt=0, le=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> TargetingResponse:
    if currency is not None and currency not in ISO_4217_CURRENCIES:
        currency = None
    req = TargetingRequest(country=country, sector=sector, deal_type=deal_type, amount=amount,
                           currency=currency, kind=kind, capacity_ratio=capacity_ratio)
    found = await find_candidates(db, req)
    return TargetingResponse(
        request={"country": country, "sector": sector, "deal_type": deal_type, "amount": amount,
                 "currency": currency, "kind": kind, "capacity_ratio": capacity_ratio},
        method=METHOD, total=len(found),
        items=[CandidateRead(kind=c.kind, id=c.id, name=c.name, country_code=c.country_code,
                             entity_type=c.entity_type, website=c.website, criteria_met=c.met,
                             criteria_known=c.known, criteria=c.criteria) for c in found[:limit]],
    )


@router.get("/mandates", summary="Internal mandates and institutions approached", response_model=list[MandateRead])
async def mandates(db: AsyncSession = Depends(get_db_session)) -> list[MandateRead]:
    rows = (await db.execute(
        select(Mandate, Country.code).outerjoin(Country, Country.id == Mandate.country_id)
        .options(selectinload(Mandate.counterparties))
        .where(Mandate.deleted_at.is_(None)).order_by(Mandate.year.desc().nulls_last(), Mandate.code)
    )).all()
    return [
        MandateRead(
            id=m.id, code=m.code, title=m.title, client_name=m.client_name, country_code=cc, sector=m.sector,
            deal_type=m.deal_type, amount=m.amount, currency=m.currency, maturity_months=m.maturity_months,
            year=m.year, status=m.status, notes=m.notes,
            counterparties=[CounterpartyRead(
                id=c.id, counterparty_name=c.counterparty_name, institution_id=c.institution_id,
                entity_id=c.entity_id, stage=c.stage, amount=c.amount, currency=c.currency,
                contact_date=c.contact_date, reason=c.reason, notes=c.notes)
                for c in m.counterparties if c.deleted_at is None],
        )
        for m, cc in rows
    ]


