"""
Syndication tracker API (migration 0022, docs/syndication.md) — INTERNAL routes (require_internal).

  POST  /api/v1/syndication/imports/preview         upload the Excel -> plan (nothing written but the plan)
  POST  /api/v1/syndication/imports/{id}/apply      write it (a decision for every conflict)
  GET   /api/v1/syndication/imports                 history of the imports
  GET   /api/v1/syndication/deals                   mandates with counterparty counts
  GET   /api/v1/syndication/deals/{id}              counterparties (current + history), terms, contacts
  PATCH /api/v1/syndication/deals/{id}              edit a mandate in the platform
  POST  /api/v1/syndication/deals/{id}/counterparties   record a new event (approach, interest...)
  GET   /api/v1/syndication/lenders | /terms        lender map and funding terms, recomputed
  GET / POST /api/v1/syndication/contacts, PATCH / DELETE /api/v1/syndication/contacts/{id}
"""
from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.deals import (
    COUNTERPARTY_STAGES,
    DEAL_TYPES,
    LENDER_TYPES,
    MANDATE_STATUSES,
    SECTORS,
)
from app.core.config import get_settings
from app.core.internal_auth import current_user, require_internal
from app.db.session import get_db_session
from app.models.mandate import InstitutionContact, Mandate, SyndicationImport
from app.services import syndication as svc

router = APIRouter(prefix="/api/v1/syndication", tags=["syndication (internal)"],
                   dependencies=[Depends(require_internal)])


def actor_of(body_actor: str | None, header_user: str | None) -> str:
    actor = (body_actor or header_user or "").strip()
    if not actor:
        raise HTTPException(status_code=422, detail="actor is required (or the authenticated user)")
    return actor[:255]


def fail(err: svc.SyndicationError):
    raise HTTPException(status_code=err.status, detail={"message": str(err), **({"detail": err.detail}
                                                                               if err.detail is not None else {})})


# =========================================================================== imports
def import_read(row: SyndicationImport, *, with_plan: bool) -> dict[str, Any]:
    out = {"id": row.id, "file_name": row.file_name, "file_updated_on": row.file_updated_on, "status": row.status,
           "actor": row.actor, "created_at": row.created_at, "applied_at": row.applied_at, "counts": row.counts}
    if with_plan:
        plan = row.plan
        out.update({
            "conflicts": plan["conflicts"], "unresolved_names": plan["unresolved_names"],
            "detail_sheets": plan["detail_sheets"], "ignored_sheets": plan["ignored_sheets"],
            "warnings": plan["warnings"], "sheet_mapping": plan.get("sheet_mapping") or {},
            "mandates": [{"code": m["code"], "title": m["values"]["title"], "action": m["action"],
                          "updates": sorted(m.get("updates") or {})} for m in plan["mandates"]],
            "events": [{"mandate_code": e["event"]["mandate_code"], "counterparty_name": e["event"]["counterparty_name"],
                        "stage": e["event"]["stage"], "action": e["action"]} for e in plan["events"]],
            "contacts": [{"institution_name": c["values"]["institution_name"], "full_name": c["values"]["full_name"],
                          "action": c["action"]} for c in plan["contacts"]],
        })
    return out


@router.post("/imports/preview", summary="Upload the syndication Excel and get the import plan")
async def preview_import(
    file: UploadFile = File(...),
    actor: str | None = Form(None),
    sheet_mapping: str | None = Form(None, description='JSON {"<detail sheet title>": "<mandate code>"}'),
    user: str | None = Depends(current_user),
    db: AsyncSession = Depends(get_db_session),
) -> dict[str, Any]:
    if not (file.filename or "").lower().endswith((".xlsx", ".xlsm")):
        raise HTTPException(status_code=422, detail="an .xlsx workbook is expected")
    content = await file.read(get_settings().syndication_max_upload_bytes + 1)
    if len(content) > get_settings().syndication_max_upload_bytes:
        raise HTTPException(status_code=413, detail="file too large")
    try:
        mapping = json.loads(sheet_mapping) if sheet_mapping else None
        if mapping is not None and not (isinstance(mapping, dict) and all(isinstance(v, str) for v in mapping.values())):
            raise ValueError
    except ValueError:
        raise HTTPException(status_code=422, detail="sheet_mapping must be a JSON object of strings") from None
    try:
        row = await svc.preview(db, content, file.filename or "syndication.xlsx", actor=actor_of(actor, user),
                                sheet_mapping=mapping)
    except svc.SyndicationError as err:
        fail(err)
    return import_read(row, with_plan=True)


class ApplyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = None
    decisions: dict[str, Literal["platform", "excel"]] = Field(default_factory=dict)


@router.post("/imports/{import_id}/apply", summary="Write a previewed import")
async def apply_import(import_id: str, body: ApplyBody, user: str | None = Depends(current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    try:
        row = await svc.apply(db, import_id, actor=actor_of(body.actor, user), decisions=body.decisions)
    except svc.SyndicationError as err:
        fail(err)
    return import_read(row, with_plan=False)


@router.get("/imports", summary="History of the syndication imports")
async def list_imports(db: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    rows = (await db.execute(select(SyndicationImport).where(SyndicationImport.deleted_at.is_(None))
                             .order_by(SyndicationImport.created_at.desc()).limit(100))).scalars()
    return [import_read(r, with_plan=False) for r in rows]


# =========================================================================== deals
def event_read(c) -> dict[str, Any]:
    return {"id": c.id, "counterparty_name": c.counterparty_name, "institution_id": c.institution_id,
            "entity_id": c.entity_id, "stage": c.stage, "lender_type": c.lender_type, "appetite": c.appetite,
            "amount": c.amount, "currency": c.currency, "amount_text": c.amount_text, "rate_text": c.rate_text,
            "arrangement_fee_text": c.arrangement_fee_text, "commitment_fee_text": c.commitment_fee_text,
            "maturity_text": c.maturity_text, "dossier_status_raw": c.dossier_status_raw, "nda_sent_on": c.nda_sent_on,
            "nda_received_on": c.nda_received_on, "next_steps": c.next_steps, "notes": c.notes,
            "contact_date": c.contact_date, "origin": c.origin, "recorded_by": c.recorded_by, "created_at": c.created_at}


def mandate_read(m: Mandate, country_code: str | None) -> dict[str, Any]:
    states = svc.current_states([c for c in m.counterparties if c.deleted_at is None])
    counts = {"approached": 0, "interested": 0, "committed": 0, "declined": 0}
    for s in states:
        counts[svc.STAGE_BUCKETS.get(s.latest.stage, "approached")] += 1
    return {"id": m.id, "code": m.code, "title": m.title, "client_name": m.client_name, "country_code": country_code,
            "country_code_raw": m.country_code_raw, "status": m.status, "stage_raw": m.stage_raw, "sector": m.sector,
            "deal_type": m.deal_type, "amount": m.amount, "currency": m.currency, "notes": m.notes,
            "origin": m.origin, "last_updated_from_file": m.last_updated_from_file,
            "manually_edited_at": m.manually_edited_at, "counterparties": len(states), "counts": counts}


@router.get("/deals", summary="Syndicated deals (internal mandates) with counterparty counts")
async def list_deals(db: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    return [mandate_read(m, cc) for m, cc in await svc.load_mandates(db)]


@router.get("/deals/{mandate_id}", summary="One syndicated deal: counterparties, terms, contacts, history")
async def get_deal(mandate_id: str, db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    rows = await svc.load_mandates(db, mandate_id)
    if not rows:
        raise HTTPException(status_code=404, detail="deal not found")
    m, cc = rows[0]
    states = svc.current_states([c for c in m.counterparties if c.deleted_at is None])
    names = {svc.norm(s.latest.counterparty_name) for s in states}
    contacts = [c for c in (await db.execute(select(InstitutionContact).where(
        InstitutionContact.deleted_at.is_(None)).order_by(InstitutionContact.institution_name,
                                                          InstitutionContact.full_name))).scalars()
                if c.mandate_id == m.id or svc.norm(c.institution_name) in names]
    return {**mandate_read(m, cc),
            "counterparty_states": [{**event_read(s.latest), "history": [event_read(h) for h in s.history]}
                                    for s in states],
            "contacts": [contact_read(c) for c in contacts]}


class MandatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = None
    title: str | None = Field(default=None, min_length=1)
    client_name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal[MANDATE_STATUSES] | None = None  # type: ignore[valid-type]
    stage_raw: str | None = None
    sector: Literal[SECTORS] | None = None  # type: ignore[valid-type]
    deal_type: Literal[DEAL_TYPES] | None = None  # type: ignore[valid-type]
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    maturity_months: int | None = Field(default=None, gt=0)
    year: int | None = Field(default=None, ge=1990, le=2100)
    notes: str | None = None


@router.patch("/deals/{mandate_id}", summary="Edit a syndicated deal in the platform")
async def patch_deal(mandate_id: str, body: MandatePatch, user: str | None = Depends(current_user),
                     db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True, exclude={"actor"})
    if changes.get("amount") is not None and not changes.get("currency"):
        current = await db.get(Mandate, mandate_id)
        if current is None or not current.currency:
            raise HTTPException(status_code=422, detail="currency is required with an amount")
    try:
        await svc.update_mandate(db, mandate_id, changes, actor=actor_of(body.actor, user))
    except svc.SyndicationError as err:
        fail(err)
    return await get_deal(mandate_id, db)


class EventBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = None
    counterparty_name: str = Field(min_length=1, max_length=255)
    stage: Literal[COUNTERPARTY_STAGES]  # type: ignore[valid-type]
    lender_type: Literal[LENDER_TYPES] | None = None  # type: ignore[valid-type]
    appetite: bool | None = None
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    amount_text: str | None = None
    rate_text: str | None = None
    arrangement_fee_text: str | None = None
    commitment_fee_text: str | None = None
    maturity_text: str | None = None
    dossier_status_raw: str | None = None
    nda_sent_on: date | None = None
    nda_received_on: date | None = None
    next_steps: str | None = None
    contact_date: date | None = None
    reason: str | None = None
    notes: str | None = None


@router.post("/deals/{mandate_id}/counterparties", summary="Record a counterparty event (manual)")
async def add_event(mandate_id: str, body: EventBody, user: str | None = Depends(current_user),
                    db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    if body.amount is not None and body.currency is None:
        raise HTTPException(status_code=422, detail="currency is required with an amount")
    data = body.model_dump(exclude={"actor"})
    try:
        row = await svc.add_event(db, mandate_id, data, actor=actor_of(body.actor, user))
    except svc.SyndicationError as err:
        fail(err)
    return event_read(row)


# =========================================================================== recomputed views
@router.get("/lenders", summary="Lender map recomputed from the current counterparty states")
async def lenders(db: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    by_name: dict[str, dict[str, Any]] = {}
    for m, cc in await svc.load_mandates(db):
        for s in svc.current_states([c for c in m.counterparties if c.deleted_at is None]):
            c = s.latest
            item = by_name.setdefault(svc.norm(c.counterparty_name), {
                "name": c.counterparty_name, "institution_id": c.institution_id, "entity_id": c.entity_id,
                "lender_types": set(), "countries": set(), "deals": [], "tickets": [], "maturities": [],
                "stages": {}})
            item["lender_types"].update(h.lender_type for h in s.history if h.lender_type)
            if m.country_code_raw or cc:
                item["countries"].add(m.country_code_raw or cc)
            item["deals"].append({"id": m.id, "title": m.title, "stage": c.stage})
            if c.amount_text:
                item["tickets"].append(c.amount_text)
            if c.maturity_text:
                item["maturities"].append(c.maturity_text)
            item["stages"][c.stage] = item["stages"].get(c.stage, 0) + 1
    return sorted(({**v, "lender_types": sorted(v["lender_types"]), "countries": sorted(v["countries"])}
                   for v in by_name.values()), key=lambda x: x["name"].lower())


@router.get("/terms", summary="Funding terms recorded on the deals (as written, never averaged)")
async def terms(db: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    out = []
    for m, cc in await svc.load_mandates(db):
        for s in svc.current_states([c for c in m.counterparties if c.deleted_at is None]):
            c = s.latest
            if any((c.rate_text, c.arrangement_fee_text, c.commitment_fee_text, c.maturity_text)):
                out.append({"institution": c.counterparty_name, "lender_type": c.lender_type, "deal_id": m.id,
                            "deal": m.title, "country": m.country_code_raw or cc, "amount_text": c.amount_text,
                            "rate_text": c.rate_text, "arrangement_fee_text": c.arrangement_fee_text,
                            "commitment_fee_text": c.commitment_fee_text, "maturity_text": c.maturity_text})
    return out


# =========================================================================== contacts
def contact_read(c: InstitutionContact) -> dict[str, Any]:
    return {"id": c.id, "institution_name": c.institution_name, "institution_id": c.institution_id,
            "entity_id": c.entity_id, "full_name": c.full_name, "job_title": c.job_title, "email": c.email,
            "phone": c.phone, "last_interaction_on": c.last_interaction_on, "context": c.context,
            "mandate_id": c.mandate_id, "dataroom_access": c.dataroom_access, "notes": c.notes, "origin": c.origin,
            "manually_edited_at": c.manually_edited_at}


@router.get("/contacts", summary="Internal contacts (personal data)")
async def list_contacts(db: AsyncSession = Depends(get_db_session)) -> list[dict[str, Any]]:
    rows = (await db.execute(select(InstitutionContact).where(InstitutionContact.deleted_at.is_(None))
                             .order_by(InstitutionContact.institution_name, InstitutionContact.full_name))).scalars()
    return [contact_read(c) for c in rows]


class ContactBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    actor: str | None = None
    institution_name: str | None = Field(default=None, min_length=1, max_length=255)
    full_name: str | None = Field(default=None, max_length=255)
    job_title: str | None = None
    email: str | None = Field(default=None, pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
    phone: str | None = None
    last_interaction_on: date | None = None
    context: str | None = None
    mandate_id: str | None = None
    dataroom_access: bool | None = None
    notes: str | None = None


@router.post("/contacts", summary="Add a contact")
async def create_contact(body: ContactBody, user: str | None = Depends(current_user),
                         db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True, exclude={"actor"})
    try:
        row = await svc.save_contact(db, data, actor=actor_of(body.actor, user))
    except svc.SyndicationError as err:
        fail(err)
    return contact_read(row)


@router.patch("/contacts/{contact_id}", summary="Edit a contact")
async def patch_contact(contact_id: str, body: ContactBody, user: str | None = Depends(current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True, exclude={"actor"})
    try:
        row = await svc.save_contact(db, data, actor=actor_of(body.actor, user), contact_id=contact_id)
    except svc.SyndicationError as err:
        fail(err)
    return contact_read(row)


@router.delete("/contacts/{contact_id}", status_code=204, response_class=Response,
                summary="Remove a contact (kept for audit)")
async def remove_contact(contact_id: str, db: AsyncSession = Depends(get_db_session)) -> Response:
    try:
        await svc.delete_contact(db, contact_id)
    except svc.SyndicationError as err:
        fail(err)
    return Response(status_code=204)
