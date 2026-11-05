"""
Syndication tracker service (migration 0022, docs/syndication.md) — internal TOMASTEED data.

    preview(file)  -> a plan (what would be created / updated / left / in conflict), stored, nothing else
    apply(plan, decisions) -> one transaction: mandates, counterparty events, contacts, import record

The Excel and the platform are BOTH references:
  - a mandate or a contact keeps the values of its last Excel import (``excel_snapshot``). On a new
    import, each field is merged three ways: unchanged in the Excel -> the platform value stays;
    unchanged in the platform -> the Excel value is taken; changed on both sides -> CONFLICT, the user
    chooses ("platform" or "excel"), nothing is overwritten silently;
  - counterparty lines are EVENTS (append-only history): an identical Excel line is never recorded
    twice; when the latest event of a counterparty was entered in the platform after the last import
    and the Excel says something else, the user chooses too. Both stay in the history.
Institutions are linked to the directory only through an exact name or an alias of
reference/syndication_aliases.json — never by resemblance.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.models.country import Country
from app.models.mandate import InstitutionContact, Mandate, MandateCounterparty, SyndicationImport
from scraping.universe.normalize import normalize_name

ALIASES_PATH = Path(__file__).resolve().parents[2] / "reference" / "syndication_aliases.json"
MANDATE_FIELDS = ("title", "client_name", "country_code", "country_code_raw", "stage_raw", "status")
CONTACT_FIELDS = ("institution_name", "full_name", "job_title", "email", "phone", "last_interaction_on", "context",
                  "mandate_code", "dataroom_access", "notes")
EDITABLE_MANDATE_FIELDS = ("title", "client_name", "status", "stage_raw", "sector", "deal_type", "amount", "currency",
                           "maturity_months", "year", "notes")
EVENT_FIELDS = ("stage", "lender_type", "appetite", "amount", "currency", "amount_text", "rate_text",
                "arrangement_fee_text", "commitment_fee_text", "maturity_text", "dossier_status_raw", "nda_sent_on",
                "nda_received_on", "next_steps", "notes")
EDITABLE_CONTACT_FIELDS = ("institution_name", "full_name", "job_title", "email", "phone", "last_interaction_on",
                           "context", "dataroom_access", "notes")


class SyndicationError(ValueError):
    def __init__(self, message: str, *, status: int = 422, detail: Any = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


def utcnow() -> datetime:
    return datetime.now(UTC)


def norm(name: str | None) -> str:
    return normalize_name(name or "") or ""


def aliases() -> dict[str, str]:
    try:
        data = json.loads(ALIASES_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {norm(k): v for k, v in (data.get("institutions") or {}).items()}


async def resolve_institutions(db: AsyncSession, names: set[str]) -> dict[str, tuple[str | None, str | None]]:
    """name -> (institution_id, entity_id); (None, None) when not found EXACTLY (alias, then as written)."""
    from app.directory.resolve import resolve_names

    table = aliases()
    targets = {n: table.get(norm(n), n) for n in names if n}
    hits = await resolve_names(db, set(targets.values()))
    out = {}
    for name, target in targets.items():
        hit = hits.get(target)
        out[name] = (hit.institution_id, hit.entity_id) if hit else (None, None)
    return out


def _jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    return value


def merge_fields(current: dict, snapshot: dict | None, incoming: dict, fields: tuple[str, ...]
                 ) -> tuple[dict, list[dict]]:
    """3-way merge -> (updates to apply, conflicts). Values compared as JSON values."""
    updates, conflicts = {}, []
    for f in fields:
        cur, new = _jsonable(current.get(f)), _jsonable(incoming.get(f))
        if cur == new:
            continue
        if snapshot is None:  # never imported: entered in the platform
            if cur in (None, False, ""):
                updates[f] = new
            else:
                conflicts.append({"field": f, "platform": cur, "excel_before": None, "excel_now": new})
            continue
        old = _jsonable(snapshot.get(f))
        if cur == old:
            updates[f] = new
        elif new == old:
            continue  # edited in the platform, unchanged in the Excel: the platform value stays
        else:
            conflicts.append({"field": f, "platform": cur, "excel_before": old, "excel_now": new})
    return updates, conflicts


def event_fingerprint(e: dict) -> tuple:
    return (norm(e.get("counterparty_name")), e.get("stage"), e.get("appetite"),
            *(_jsonable(e.get(f)) for f in ("amount_text", "rate_text", "arrangement_fee_text", "commitment_fee_text",
                                            "maturity_text", "dossier_status_raw", "nda_sent_on", "nda_received_on",
                                            "next_steps")))


def event_dict(c: MandateCounterparty) -> dict:
    return {"counterparty_name": c.counterparty_name, **{f: _jsonable(getattr(c, f)) for f in EVENT_FIELDS},
            "origin": c.origin, "created_at": c.created_at.isoformat() if c.created_at else None}


# =========================================================================== plan
async def build_plan(db: AsyncSession, parsed: dict) -> dict:
    """What an import would do, computed against the database now (nothing is written)."""
    codes = list(parsed["mandates"])
    existing = {m.code: m for m in (await db.execute(
        select(Mandate).where(Mandate.code.in_(codes), Mandate.deleted_at.is_(None)))).scalars()}
    country_codes = dict((await db.execute(select(Country.id, Country.code))).all())
    last_import = (await db.execute(
        select(SyndicationImport.applied_at).where(SyndicationImport.status == "applied")
        .order_by(SyndicationImport.applied_at.desc()).limit(1))).scalar_one_or_none()

    mandates, conflicts = [], []
    for code, draft in parsed["mandates"].items():
        incoming = {f: draft[f] for f in MANDATE_FIELDS}
        m = existing.get(code)
        if m is None:
            mandates.append({"code": code, "action": "create", "values": incoming})
            continue
        current = {f: getattr(m, f, None) for f in MANDATE_FIELDS if f != "country_code"}
        current["country_code"] = country_codes.get(m.country_id)
        updates, fconf = merge_fields(current, m.excel_snapshot, incoming, MANDATE_FIELDS)
        for c in fconf:
            conflicts.append({"id": f"mandate:{code}:{c['field']}", "kind": "mandate", "mandate_code": code,
                              "label": draft["title"], **c})
        mandates.append({"code": code, "action": "update" if updates or fconf else "unchanged",
                         "values": incoming, "updates": updates})

    # Counterparty events: compared with the events already recorded for the same mandate + name.
    ids = [m.id for m in existing.values()]
    recorded: dict[tuple[str, str], list[MandateCounterparty]] = defaultdict(list)
    if ids:
        by_id = {m.id: m.code for m in existing.values()}
        for c in (await db.execute(select(MandateCounterparty).where(
                MandateCounterparty.mandate_id.in_(ids), MandateCounterparty.deleted_at.is_(None))
                .order_by(MandateCounterparty.created_at))).scalars():
            recorded[(by_id[c.mandate_id], norm(c.counterparty_name))].append(c)
    events = []
    seen: set[tuple] = set()
    for e in parsed["events"]:
        k = (e["mandate_code"], norm(e["counterparty_name"]))
        fp = (e["mandate_code"], *event_fingerprint(e))
        if fp in seen:
            continue
        seen.add(fp)
        history = recorded.get(k, [])
        if any((e["mandate_code"], *event_fingerprint(event_dict(c))) == fp for c in history):
            events.append({"action": "unchanged", "event": e})
            continue
        latest = history[-1] if history else None
        if latest is not None and latest.origin == "manual" and (last_import is None or latest.created_at > last_import):
            conflicts.append({"id": f"event:{e['mandate_code']}:{norm(e['counterparty_name'])}", "kind": "event",
                              "mandate_code": e["mandate_code"], "label": e["counterparty_name"],
                              "field": "stage", "platform": event_dict(latest), "excel_before": None, "excel_now": e})
            events.append({"action": "conflict", "event": e})
        else:
            events.append({"action": "create", "event": e})

    # Contacts.
    keys = [c["key"] for c in parsed["contacts"]]
    existing_contacts = {c.contact_key: c for c in (await db.execute(
        select(InstitutionContact).where(InstitutionContact.contact_key.in_(keys),
                                         InstitutionContact.deleted_at.is_(None)))).scalars()} if keys else {}
    mandate_code_by_id = {m.id: m.code for m in existing.values()}
    contacts = []
    for c in parsed["contacts"]:
        incoming = {f: c.get(f) for f in CONTACT_FIELDS}
        row = existing_contacts.get(c["key"])
        if row is None:
            contacts.append({"key": c["key"], "action": "create", "values": incoming})
            continue
        current = {f: getattr(row, f, None) for f in CONTACT_FIELDS if f != "mandate_code"}
        current["mandate_code"] = mandate_code_by_id.get(row.mandate_id) if row.mandate_id else None
        updates, fconf = merge_fields(current, row.excel_snapshot, incoming, CONTACT_FIELDS)
        for x in fconf:
            conflicts.append({"id": f"contact:{c['key']}:{x['field']}", "kind": "contact", "label":
                              f"{c.get('full_name') or c.get('email')} ({c['institution_name']})", **x})
        contacts.append({"key": c["key"], "action": "update" if updates or fconf else "unchanged",
                         "values": incoming, "updates": updates})

    names = {e["counterparty_name"] for e in parsed["events"]} | {c["institution_name"] for c in parsed["contacts"]}
    resolved = await resolve_institutions(db, names)
    unresolved = sorted(n for n, (i, e) in resolved.items() if not i and not e)
    await db.rollback()  # read-only: no transaction kept open

    def count(items, action):
        return sum(1 for x in items if x["action"] == action)

    return {
        "file_updated_on": parsed.get("file_updated_on"),
        "mandates": mandates, "events": events, "contacts": contacts, "conflicts": conflicts,
        "resolved": {n: list(v) for n, v in resolved.items()}, "unresolved_names": unresolved,
        "detail_sheets": parsed["detail_sheets"], "ignored_sheets": parsed["ignored_sheets"],
        "warnings": parsed["warnings"], "parsed": parsed,
        "counts": {
            "mandates": {a: count(mandates, a) for a in ("create", "update", "unchanged")},
            "events": {a: count(events, a) for a in ("create", "unchanged", "conflict")},
            "contacts": {a: count(contacts, a) for a in ("create", "update", "unchanged")},
            "conflicts": len(conflicts), "unresolved_names": len(unresolved),
        },
    }


# =========================================================================== preview / apply
async def preview(db: AsyncSession, content: bytes, file_name: str, *, actor: str,
                  sheet_mapping: dict[str, str] | None = None) -> SyndicationImport:
    from app.mandates.syndication_xlsx import WorkbookError, read_workbook

    if not actor or not actor.strip():
        raise SyndicationError("actor is required")
    sha = hashlib.sha256(content).hexdigest()
    applied = (await db.execute(select(SyndicationImport).where(
        SyndicationImport.file_sha256 == sha, SyndicationImport.status == "applied"))).scalar_one_or_none()
    if applied is not None:
        raise SyndicationError("this exact file was already imported", status=409,
                               detail={"import_id": applied.id, "applied_at": _jsonable(applied.applied_at)})
    try:
        # openpyxl is synchronous: read in a worker thread, the API keeps answering meanwhile.
        parsed = (await run_in_threadpool(read_workbook, content, sheet_mapping=sheet_mapping)).as_json()
    except WorkbookError as err:
        raise SyndicationError(str(err)) from err
    plan = await build_plan(db, parsed)
    plan["sheet_mapping"] = sheet_mapping or {}
    row = SyndicationImport(file_name=file_name[:255], file_sha256=sha, status="preview", actor=actor.strip(),
                            plan=plan, counts=plan["counts"],
                            file_updated_on=date.fromisoformat(plan["file_updated_on"]) if plan["file_updated_on"]
                            else None)
    db.add(row)
    await db.commit()
    return row


async def apply(db: AsyncSession, import_id: str, *, actor: str, decisions: dict[str, str] | None = None
                ) -> SyndicationImport:
    """Write the import. The plan is recomputed now (the database may have changed since the preview);
    every conflict needs a decision ("platform" or "excel")."""
    if not actor or not actor.strip():
        raise SyndicationError("actor is required")
    actor = actor.strip()
    row = await db.get(SyndicationImport, import_id)
    if row is None or row.deleted_at is not None:
        raise SyndicationError("import not found", status=404)
    if row.status != "preview":
        raise SyndicationError(f"import already {row.status}", status=409)
    plan = await build_plan(db, row.plan["parsed"])
    decisions = decisions or {}
    missing = [c["id"] for c in plan["conflicts"] if decisions.get(c["id"]) not in ("platform", "excel")]
    if missing:
        raise SyndicationError("a decision is required for every conflict", status=409,
                               detail={"conflicts": plan["conflicts"], "missing": missing})
    row = await db.get(SyndicationImport, import_id)
    take_excel = {cid for cid, d in decisions.items() if d == "excel"}
    file_day = date.fromisoformat(plan["file_updated_on"]) if plan["file_updated_on"] else None
    countries = dict((await db.execute(select(Country.code, Country.id))).all())
    resolved = {n: tuple(v) for n, v in plan["resolved"].items()}
    parsed = plan["parsed"]
    try:
        by_code = {m.code: m for m in (await db.execute(select(Mandate).where(
            Mandate.code.in_(list(parsed["mandates"])), Mandate.deleted_at.is_(None)))).scalars()}
        for item in plan["mandates"]:
            code, values = item["code"], item["values"]
            fields = dict(item.get("updates") or {})
            fields.update({c["field"]: c["excel_now"] for c in plan["conflicts"]
                           if c["kind"] == "mandate" and c["mandate_code"] == code and c["id"] in take_excel})
            if item["action"] == "create":
                m = Mandate(code=code, recorded_by=actor, origin="excel_import", import_batch_id=row.id, **{
                    k: v for k, v in values.items() if k != "country_code"},
                    country_id=countries.get(values.get("country_code") or ""))
                db.add(m)
                by_code[code] = m
            else:
                m = by_code[code]
                for k, v in fields.items():
                    if k == "country_code":
                        m.country_id = countries.get(v or "")
                    else:
                        setattr(m, k, v)
                m.import_batch_id = row.id
            m.excel_snapshot = values
            m.last_updated_from_file = file_day
        await db.flush()

        created_events = 0
        for item in plan["events"]:
            e = item["event"]
            cid = f"event:{e['mandate_code']}:{norm(e['counterparty_name'])}"
            if item["action"] == "unchanged" or (item["action"] == "conflict" and cid not in take_excel):
                continue  # identical line already recorded, or the platform value was kept
            inst, ent = resolved.get(e["counterparty_name"], (None, None))
            db.add(MandateCounterparty(
                mandate_id=by_code[e["mandate_code"]].id, counterparty_name=e["counterparty_name"][:255],
                institution_id=inst, entity_id=ent, stage=e["stage"],
                amount=Decimal(e["amount"]) if e.get("amount") else None, currency=e.get("currency"),
                contact_date=file_day, notes=e.get("notes"), recorded_by=actor, origin="excel_import",
                import_batch_id=row.id, lender_type=e.get("lender_type"), appetite=e.get("appetite"),
                amount_text=e.get("amount_text"), rate_text=e.get("rate_text"),
                arrangement_fee_text=e.get("arrangement_fee_text"), commitment_fee_text=e.get("commitment_fee_text"),
                maturity_text=e.get("maturity_text"), dossier_status_raw=e.get("dossier_status_raw"),
                nda_sent_on=date.fromisoformat(e["nda_sent_on"]) if e.get("nda_sent_on") else None,
                nda_received_on=date.fromisoformat(e["nda_received_on"]) if e.get("nda_received_on") else None,
                next_steps=e.get("next_steps"),
            ))
            created_events += 1

        existing_contacts = {c.contact_key: c for c in (await db.execute(select(InstitutionContact).where(
            InstitutionContact.contact_key.in_([c["key"] for c in plan["contacts"]] or [""]),
            InstitutionContact.deleted_at.is_(None)))).scalars()}
        for item in plan["contacts"]:
            values = item["values"]
            fields = dict(item.get("updates") or {})
            fields.update({c["field"]: c["excel_now"] for c in plan["conflicts"]
                           if c["kind"] == "contact" and c["id"].startswith(f"contact:{item['key']}:")
                           and c["id"] in take_excel})
            inst, ent = resolved.get(values["institution_name"], (None, None))
            if item["action"] == "create":
                row_c = InstitutionContact(contact_key=item["key"], recorded_by=actor, origin="excel_import",
                                           institution_id=inst, entity_id=ent)
                db.add(row_c)
                fields = values
            else:
                row_c = existing_contacts[item["key"]]
            for k, v in fields.items():
                if k == "mandate_code":
                    row_c.mandate_id = by_code[v].id if v in by_code else None
                elif k == "last_interaction_on":
                    row_c.last_interaction_on = date.fromisoformat(v) if v else None
                else:
                    setattr(row_c, k, v)
            row_c.import_batch_id = row.id
            row_c.excel_snapshot = values
        row.status, row.applied_at, row.actor = "applied", utcnow(), actor
        row.counts = {**plan["counts"], "events_written": created_events,
                      "decisions": {"excel": len(take_excel), "platform": len(decisions) - len(take_excel)}}
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return row


# =========================================================================== manual edits
async def update_mandate(db: AsyncSession, mandate_id: str, changes: dict, *, actor: str) -> Mandate:
    m = await db.get(Mandate, mandate_id)
    if m is None or m.deleted_at is not None:
        raise SyndicationError("mandate not found", status=404)
    unknown = set(changes) - set(EDITABLE_MANDATE_FIELDS)
    if unknown:
        raise SyndicationError(f"fields not editable: {', '.join(sorted(unknown))}")
    for k, v in changes.items():
        setattr(m, k, v)
    m.manually_edited_at = utcnow()
    await db.commit()
    return m


async def add_event(db: AsyncSession, mandate_id: str, data: dict, *, actor: str) -> MandateCounterparty:
    m = await db.get(Mandate, mandate_id)
    if m is None or m.deleted_at is not None:
        raise SyndicationError("mandate not found", status=404)
    resolved = await resolve_institutions(db, {data["counterparty_name"]})
    inst, ent = resolved.get(data["counterparty_name"], (None, None))
    row = MandateCounterparty(mandate_id=m.id, institution_id=inst, entity_id=ent, recorded_by=actor,
                              origin="manual", contact_date=data.pop("contact_date", None) or utcnow().date(), **data)
    db.add(row)
    await db.commit()
    return row


def contact_key(institution_name: str, email: str | None, full_name: str | None) -> str:
    inst = norm(institution_name) or "?"
    return f"{inst}|{email.lower()}" if email else f"{inst}|name:{norm(full_name)}"


async def save_contact(db: AsyncSession, data: dict, *, actor: str, contact_id: str | None = None
                       ) -> InstitutionContact:
    unknown = set(data) - set(EDITABLE_CONTACT_FIELDS) - {"mandate_id"}
    if unknown:
        raise SyndicationError(f"fields not editable: {', '.join(sorted(unknown))}")
    if contact_id:
        row = await db.get(InstitutionContact, contact_id)
        if row is None or row.deleted_at is not None:
            raise SyndicationError("contact not found", status=404)
    else:
        if not data.get("institution_name") or not (data.get("email") or data.get("full_name")):
            raise SyndicationError("institution_name and a name or an e-mail are required")
        key = contact_key(data["institution_name"], data.get("email"), data.get("full_name"))
        if (await db.execute(select(InstitutionContact.id).where(InstitutionContact.contact_key == key,
                                                                 InstitutionContact.deleted_at.is_(None)))).first():
            raise SyndicationError("this contact already exists", status=409)
        resolved = await resolve_institutions(db, {data["institution_name"]})
        inst, ent = resolved.get(data["institution_name"], (None, None))
        row = InstitutionContact(contact_key=key, recorded_by=actor, origin="manual", institution_id=inst,
                                 entity_id=ent, institution_name=data["institution_name"])
        db.add(row)
    for k, v in data.items():
        setattr(row, k, v)
    row.manually_edited_at = utcnow()
    await db.commit()
    return row


async def delete_contact(db: AsyncSession, contact_id: str) -> None:
    row = await db.get(InstitutionContact, contact_id)
    if row is None or row.deleted_at is not None:
        raise SyndicationError("contact not found", status=404)
    row.deleted_at = utcnow()  # soft delete: kept for the audit trail
    await db.commit()


# =========================================================================== reads
@dataclass
class CounterpartyState:
    latest: MandateCounterparty
    history: list[MandateCounterparty]


def current_states(events: list[MandateCounterparty]) -> list[CounterpartyState]:
    """Latest RECORDED event per counterparty name: an import decision ("take the Excel") or a manual entry
    made after it is the current state, whatever the dates they carry."""
    groups: dict[str, list[MandateCounterparty]] = defaultdict(list)
    for e in events:
        groups[norm(e.counterparty_name)].append(e)
    out = []
    for items in groups.values():
        items.sort(key=lambda c: c.created_at)
        out.append(CounterpartyState(items[-1], items))
    return sorted(out, key=lambda s: s.latest.counterparty_name.lower())


STAGE_BUCKETS = {"approached": "approached", "interested": "interested", "term_sheet": "interested",
                 "committed": "committed", "disbursed": "committed", "declined": "declined", "withdrawn": "declined"}


async def load_mandates(db: AsyncSession, mandate_id: str | None = None):
    from sqlalchemy.orm import selectinload

    q = (select(Mandate, Country.code).outerjoin(Country, Country.id == Mandate.country_id)
         .options(selectinload(Mandate.counterparties)).where(Mandate.deleted_at.is_(None)))
    if mandate_id:
        q = q.where(Mandate.id == mandate_id)
    return (await db.execute(q.order_by(Mandate.title))).all()
