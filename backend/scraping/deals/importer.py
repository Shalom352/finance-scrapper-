"""Structured deal import (Phase 13) — the ONLY way deals enter the database.

    parse (JSON / CSV) -> Pydantic validation -> reference checks against the database
    -> one transaction: deals + sources + field provenance + participants
       + duplicate candidates + one ``import`` audit event per deal

All or nothing: a single problem anywhere in the file refuses the whole file and nothing
is written. Nothing is ever created implicitly (no document, source, institution or
country is invented to "make the import pass"). Every imported deal is ``needs_review``.

``import_deals`` is the entry point a future extractor would reuse; no extractor exists.
"""
import csv
import io
import json
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.country import Country
from app.models.deal import (
    Deal,
    DealDuplicateCandidate,
    DealFieldSource,
    DealParticipant,
    DealSource,
)
from app.models.document import Document
from app.models.entity import Entity
from app.models.institution import Institution
from app.models.review_event import FinancialDataReviewEvent
from app.models.source import Source
from scraping.deals.duplicates import DealFacts, is_candidate, matched_criteria
from scraping.deals.schemas import DealImportRecord

IMPORT_STATUS = "needs_review"
MAX_RECORDS_PER_FILE = 1000

# CSV: flat columns + two encoded columns.
#   participants = role|name|institution_id|source_ref[|commitment_amount|commitment_currency] ; ...
#   sources      = ref|document_id|source_id|page|field,field,...[|excerpt] ; ...
CSV_LIST_SEP = ";"
CSV_PART_SEP = "|"


@dataclass
class ImportIssue:
    row: int  # 1-based record number in the file (0 = the file itself)
    field: str
    code: str
    message: str


class DealImportError(Exception):
    def __init__(self, issues: list[ImportIssue]):
        self.issues = issues
        super().__init__(f"{len(issues)} import issue(s); nothing was written")


@dataclass
class ImportReport:
    created_ids: list[str] = field(default_factory=list)
    # (new deal id, other deal id, matched criteria)
    duplicate_candidates: list[tuple[str, str, list[str]]] = field(default_factory=list)
    dry_run: bool = False


# --------------------------------------------------------------------------- parsing


def parse_json(text: str) -> list[dict[str, Any]]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise DealImportError([ImportIssue(0, "file", "invalid_json", str(err))]) from err
    if not isinstance(data, list) or not all(isinstance(r, dict) for r in data):
        raise DealImportError([ImportIssue(0, "file", "invalid_json", "expected a JSON list of objects")])
    return data


def _split(value: str, sep: str) -> list[str]:
    return [p.strip() for p in value.split(sep)] if value and value.strip() else []


def parse_csv(text: str) -> list[dict[str, Any]]:
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as err:
        raise DealImportError([ImportIssue(0, "file", "invalid_csv", str(err))]) from err
    if not rows:
        raise DealImportError([ImportIssue(0, "file", "invalid_csv", "no data rows")])
    records: list[dict[str, Any]] = []
    issues: list[ImportIssue] = []
    for n, row in enumerate(rows, start=1):
        if None in row:  # more cells than headers
            issues.append(ImportIssue(n, "row", "invalid_csv", "more cells than header columns"))
            continue
        # Empty cell = not published = absent (never 0, never "").
        rec: dict[str, Any] = {k: v for k, v in row.items() if k not in ("participants", "sources") and v != ""}
        try:
            rec["sources"] = [_csv_source(p) for p in _split(row.get("sources") or "", CSV_LIST_SEP)]
            rec["participants"] = [
                _csv_participant(p) for p in _split(row.get("participants") or "", CSV_LIST_SEP)
            ]
        except ValueError as err:
            issues.append(ImportIssue(n, "row", "invalid_csv", str(err)))
            continue
        records.append(rec)
    if issues:
        raise DealImportError(issues)
    return records


def _csv_source(value: str) -> dict[str, Any]:
    parts = value.split(CSV_PART_SEP)
    if len(parts) not in (5, 6):
        raise ValueError(f"source '{value}' must be ref|document_id|source_id|page|fields[|excerpt]")
    out: dict[str, Any] = {
        "ref": parts[0], "document_id": parts[1], "source_id": parts[2], "page": parts[3],
        "fields": _split(parts[4], ","),
    }
    if len(parts) == 6 and parts[5].strip():
        out["excerpt"] = parts[5].strip()
    return out


def _csv_participant(value: str) -> dict[str, Any]:
    parts = value.split(CSV_PART_SEP)
    if len(parts) not in (4, 6):
        raise ValueError(
            f"participant '{value}' must be role|name|institution_id|source_ref[|amount|currency]"
        )
    out: dict[str, Any] = {"role": parts[0], "name": parts[1], "source_ref": parts[3]}
    if parts[2].strip():
        out["institution_id"] = parts[2].strip()
    if len(parts) == 6:
        if parts[4].strip():
            out["commitment_amount"] = parts[4].strip()
        if parts[5].strip():
            out["commitment_currency"] = parts[5].strip()
    return out


def parse_file(filename: str, text: str) -> list[dict[str, Any]]:
    lower = filename.lower()
    if lower.endswith(".json"):
        return parse_json(text)
    if lower.endswith(".csv"):
        return parse_csv(text)
    raise DealImportError([ImportIssue(0, "file", "unsupported_format", "expected a .json or .csv file")])


def validate_records(raw: list[dict[str, Any]]) -> list[DealImportRecord]:
    if not raw:
        raise DealImportError([ImportIssue(0, "file", "empty", "no deal in the file")])
    if len(raw) > MAX_RECORDS_PER_FILE:
        raise DealImportError(
            [ImportIssue(0, "file", "too_many_records", f"max {MAX_RECORDS_PER_FILE} deals per file")]
        )
    records: list[DealImportRecord] = []
    issues: list[ImportIssue] = []
    for n, item in enumerate(raw, start=1):
        try:
            records.append(DealImportRecord.model_validate(item))
        except ValidationError as err:
            for e in err.errors():
                loc = ".".join(str(x) for x in e["loc"]) or "record"
                issues.append(ImportIssue(n, loc, e["type"], e["msg"]))
    if issues:
        raise DealImportError(issues)
    return records


# --------------------------------------------------------------------------- database checks


async def _check_references(db: AsyncSession, records: list[DealImportRecord]) -> dict[str, str]:
    """Every referenced entity must already exist. Returns country code -> country id."""
    doc_ids = {s.document_id for r in records for s in r.sources}
    src_ids = {s.source_id for r in records for s in r.sources}
    inst_ids = {p.institution_id for r in records for p in r.participants if p.institution_id}
    entity_ids = {p.entity_id for r in records for p in r.participants if p.entity_id}
    keys = [r.ingestion_key for r in records if r.ingestion_key]
    codes = {r.country_code for r in records if r.country_code}

    docs = {
        d.id: d
        for d in (
            await db.execute(
                select(Document.id, Document.source_id, Document.page_count).where(
                    Document.id.in_(doc_ids), Document.deleted_at.is_(None)
                )
            )
        ).all()
    }
    sources = set((await db.execute(select(Source.id).where(Source.id.in_(src_ids)))).scalars())
    insts = set(
        (
            await db.execute(
                select(Institution.id).where(Institution.id.in_(inst_ids), Institution.deleted_at.is_(None))
            )
        ).scalars()
    ) if inst_ids else set()
    entities = set(
        (
            await db.execute(select(Entity.id).where(Entity.id.in_(entity_ids), Entity.deleted_at.is_(None)))
        ).scalars()
    ) if entity_ids else set()
    existing_keys = set(
        (
            await db.execute(
                select(Deal.ingestion_key).where(Deal.ingestion_key.in_(keys), Deal.deleted_at.is_(None))
            )
        ).scalars()
    ) if keys else set()
    countries = dict(
        (await db.execute(select(Country.code, Country.id).where(Country.code.in_(codes)))).all()
    ) if codes else {}

    issues: list[ImportIssue] = []
    for n, r in enumerate(records, start=1):
        for s in r.sources:
            doc = docs.get(s.document_id)
            if doc is None:
                issues.append(ImportIssue(n, f"sources.{s.ref}.document_id", "document_not_found",
                                          f"document '{s.document_id}' does not exist"))
            if s.source_id not in sources:
                issues.append(ImportIssue(n, f"sources.{s.ref}.source_id", "source_not_found",
                                          f"source '{s.source_id}' does not exist"))
            if doc is not None and doc.source_id != s.source_id:
                issues.append(ImportIssue(n, f"sources.{s.ref}.source_id", "source_mismatch",
                                          "the document belongs to another source"))
            if doc is not None and doc.page_count is not None and s.page > doc.page_count:
                issues.append(ImportIssue(n, f"sources.{s.ref}.page", "page_out_of_range",
                                          f"page {s.page} > document page count {doc.page_count}"))
        for i, p in enumerate(r.participants):
            if p.institution_id and p.institution_id not in insts:
                issues.append(ImportIssue(n, f"participants.{i}.institution_id", "institution_not_found",
                                          f"institution '{p.institution_id}' does not exist"))
            if p.entity_id and p.entity_id not in entities:
                issues.append(ImportIssue(n, f"participants.{i}.entity_id", "entity_not_found",
                                          f"entity '{p.entity_id}' does not exist"))
        if r.ingestion_key and r.ingestion_key in existing_keys:
            issues.append(ImportIssue(n, "ingestion_key", "already_imported",
                                      f"a deal with ingestion key '{r.ingestion_key}' already exists"))
        if r.ingestion_key and keys.count(r.ingestion_key) > 1:
            issues.append(ImportIssue(n, "ingestion_key", "duplicate_in_file",
                                      f"ingestion key '{r.ingestion_key}' appears several times in the file"))
        if r.country_code and r.country_code not in countries:
            issues.append(ImportIssue(n, "country_code", "country_not_found",
                                      f"country '{r.country_code}' does not exist"))
    if issues:
        raise DealImportError(issues)
    return countries


# --------------------------------------------------------------------------- duplicates


def _facts(deal_id: str, r: DealImportRecord) -> DealFacts:
    return DealFacts(
        id=deal_id, deal_type=r.deal_type, project_name=r.project_name, amount=r.amount, currency=r.currency,
        signing_date=r.signing_date, announcement_date=r.announcement_date,
        participants=[(p.role, p.institution_id, p.name) for p in r.participants],
        isin=r.isin, value_date=r.value_date,
        issuer_entities=frozenset(p.entity_id for p in r.participants if p.role == "issuer" and p.entity_id),
    )


async def _existing_facts(db: AsyncSession) -> list[DealFacts]:
    """Existing, non-rejected, non-merged deals that carry an anchor (borrower, project or instrument).

    Names are compared on a normalized key computed in Python (accents / punctuation), so the
    lookup is not pre-filtered by name in SQL: a candidate is never missed because of spelling.
    """
    has_borrower = select(DealParticipant.deal_id).where(DealParticipant.role == "borrower")
    rows = (
        await db.execute(
            select(Deal)
            .options(selectinload(Deal.participants))
            .where(
                Deal.deleted_at.is_(None),
                Deal.status != "rejected",
                Deal.merged_into_deal_id.is_(None),
                or_(Deal.id.in_(has_borrower), Deal.project_name.is_not(None), Deal.isin.is_not(None)),
            )
        )
    ).scalars().all()
    return [
        DealFacts(
            id=d.id, deal_type=d.deal_type, project_name=d.project_name, amount=d.amount, currency=d.currency,
            signing_date=d.signing_date, announcement_date=d.announcement_date,
            participants=[(p.role, p.institution_id, p.participant_name) for p in d.participants],
            isin=d.isin, value_date=d.value_date,
            issuer_entities=frozenset(p.entity_id for p in d.participants if p.role == "issuer" and p.entity_id),
        )
        for d in rows
    ]


# --------------------------------------------------------------------------- import


async def import_deals(
    db: AsyncSession,
    records: list[DealImportRecord],
    *,
    actor: str,
    origin: str,
    dry_run: bool = False,
) -> ImportReport:
    """Write validated records in ONE transaction (or roll back with ``dry_run``)."""
    if not actor or not actor.strip() or len(actor.strip()) > 255:
        raise DealImportError([ImportIssue(0, "actor", "invalid_actor", "actor is required (1..255 chars)")])
    actor = actor.strip()
    countries = await _check_references(db, records)
    report = ImportReport(dry_run=dry_run)

    try:
        new_facts: list[DealFacts] = []
        for r in records:
            deal = Deal(
                title=r.title, deal_type=r.deal_type,
                country_id=countries.get(r.country_code) if r.country_code else None,
                sector=r.sector, project_name=r.project_name, amount_original=r.amount_original,
                amount=r.amount, currency=r.currency, unit=r.unit, interest_rate=r.interest_rate,
                interest_rate_type=r.interest_rate_type, benchmark=r.benchmark, spread_bps=r.spread_bps,
                maturity_months=r.maturity_months, grace_period_months=r.grace_period_months, fees=r.fees,
                guarantees=r.guarantees, announcement_date=r.announcement_date, signing_date=r.signing_date,
                financial_close_date=r.financial_close_date, closing_date=r.closing_date,
                instrument_type=r.instrument_type, isin=r.isin, auction_reference=r.auction_reference,
                auction_date=r.auction_date, value_date=r.value_date, maturity_date=r.maturity_date,
                yield_rate=r.yield_rate, ingestion_key=r.ingestion_key,
                validation_flags=[f.model_dump() for f in r.validation_flags] or None,
                use_of_proceeds=r.use_of_proceeds, use_of_proceeds_categories=r.use_of_proceeds_categories,
                filing_agent_raw=r.filing_agent_raw,
                status=IMPORT_STATUS,
            )
            db.add(deal)
            await db.flush()
            by_ref: dict[str, DealSource] = {}
            for s in r.sources:
                ds = DealSource(deal_id=deal.id, document_id=s.document_id, source_id=s.source_id,
                                page_number=s.page, excerpt=s.excerpt, source_class=s.source_class,
                                publisher=s.publisher, title=s.title, url=s.url, published_at=s.published_at,
                                paywalled=s.paywalled)
                db.add(ds)
                by_ref[s.ref] = ds
            await db.flush()
            for s in r.sources:
                for f in dict.fromkeys(s.fields):  # validated against PROVENANCE_FIELDS by the schema
                    db.add(DealFieldSource(deal_id=deal.id, field_name=f, deal_source_id=by_ref[s.ref].id))
            for p in r.participants:
                db.add(DealParticipant(
                    deal_id=deal.id, participant_name=p.name, institution_id=p.institution_id,
                    entity_id=p.entity_id, role=p.role,
                    commitment_amount=p.commitment_amount, commitment_currency=p.commitment_currency,
                    deal_source_id=by_ref[p.source_ref].id, page_number=p.page, excerpt=p.excerpt,
                    extraction_method=p.extraction_method,
                ))
            db.add(FinancialDataReviewEvent(
                deal_id=deal.id, action="import", previous_status="none", new_status=IMPORT_STATUS,
                reason=f"Structured import: {origin}", actor=actor, value_before=None, value_after=r.amount,
            ))
            report.created_ids.append(deal.id)
            new_facts.append(_facts(deal.id, r))

        await db.flush()
        created = set(report.created_ids)
        existing = [f for f in await _existing_facts(db) if f.id not in created]
        seen: set[tuple[str, str]] = set()
        for i, a in enumerate(new_facts):
            for b in existing + new_facts[i + 1:]:
                criteria = matched_criteria(a, b)
                pair = tuple(sorted((a.id, b.id)))
                if not is_candidate(criteria) or pair in seen:
                    continue
                seen.add(pair)  # type: ignore[arg-type]
                db.add(DealDuplicateCandidate(deal_a_id=pair[0], deal_b_id=pair[1], matched_criteria=criteria,
                                              state="duplicate_candidate"))
                report.duplicate_candidates.append((a.id, b.id, criteria))

        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


async def import_file(db: AsyncSession, filename: str, text: str, *, actor: str, dry_run: bool = False
                      ) -> ImportReport:
    records = validate_records(parse_file(filename, text))
    return await import_deals(db, records, actor=actor, origin=filename, dry_run=dry_run)

