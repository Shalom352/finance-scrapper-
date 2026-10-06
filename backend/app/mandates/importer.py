"""
Internal mandates import (Phase 20) — TOMASTEED pipeline and institutions approached.

    python -m app.mandates.importer --mandates mandates.csv [--counterparties contacts.csv] \
        --actor <identifiant> --expect-db <db> [--dry-run]

mandates.csv       code,title,client_name,country_code,sector,deal_type,amount,currency,maturity_months,year,status,notes
contacts.csv       mandate_code,counterparty_name,institution_name,entity_name,stage,amount,currency,contact_date,reason,notes

Rules: strict validation, all or nothing; an empty cell stays NULL (never 0); amounts are never
converted. A mandate is matched by its ``code`` (updated if it exists). A contact row is an EVENT
(append-only history): an identical row already recorded is skipped. ``institution_name`` /
``entity_name`` must match the directory EXACTLY (official / canonical or short name), otherwise
the file is refused: no institution is ever guessed.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import io
import json
import os
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)

from app.constants.deals import (
    COUNTERPARTY_STAGES,
    DEAL_TYPES,
    ISO_4217_CURRENCIES,
    MANDATE_STATUSES,
    SECTORS,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


def _currency(v: str | None) -> str | None:
    if v is not None and v not in ISO_4217_CURRENCIES:
        raise ValueError(f"unknown ISO 4217 currency '{v}'")
    return v


class MandateRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
    title: Text
    client_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    country_code: Annotated[str, StringConstraints(pattern=r"^[A-Z]{2}$")] | None = None
    sector: Literal[SECTORS] | None = None  # type: ignore[valid-type]
    deal_type: Literal[DEAL_TYPES] | None = None  # type: ignore[valid-type]
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    maturity_months: int | None = Field(default=None, gt=0)
    year: int | None = Field(default=None, ge=1990, le=2100)
    status: Literal[MANDATE_STATUSES] = "active"  # type: ignore[valid-type]
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @model_validator(mode="after")
    def amount_currency(self) -> MandateRow:
        if self.amount is not None and self.currency is None:
            raise ValueError("currency is required when amount is given")
        return self


class ContactRow(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mandate_code: Text
    counterparty_name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    institution_name: str | None = None
    entity_name: str | None = None
    stage: Literal[COUNTERPARTY_STAGES]  # type: ignore[valid-type]
    amount: Decimal | None = Field(default=None, gt=0)
    currency: str | None = None
    contact_date: date | None = None
    reason: str | None = None
    notes: str | None = None

    @field_validator("currency")
    @classmethod
    def iso_currency(cls, value: str | None) -> str | None:
        return _currency(value)

    @model_validator(mode="after")
    def checks(self) -> ContactRow:
        if self.amount is not None and self.currency is None:
            raise ValueError("currency is required when amount is given")
        if self.institution_name and self.entity_name:
            raise ValueError("give institution_name OR entity_name, not both")
        return self


@dataclass
class MandateReport:
    mandates_created: int = 0
    mandates_updated: int = 0
    contacts_created: int = 0
    contacts_skipped: int = 0
    issues: list[str] = field(default_factory=list)


class MandateImportError(Exception):
    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__(f"{len(issues)} issue(s); nothing was written: " + "; ".join(issues))


def parse_csv(text: str, model: type[BaseModel]) -> list[Any]:
    rows = list(csv.DictReader(io.StringIO(text)))
    out, issues = [], []
    for n, row in enumerate(rows, start=2):  # line 1 = header
        clean = {k.strip(): v.strip() for k, v in row.items() if k and v is not None and v.strip() != ""}
        try:
            out.append(model.model_validate(clean))
        except ValidationError as err:
            for e in err.errors():
                issues.append(f"line {n} · {'.'.join(str(x) for x in e['loc']) or 'row'} · {e['msg']}")
    if issues:
        raise MandateImportError(issues)
    return out


async def import_mandates(db, mandates: list[MandateRow], contacts: list[ContactRow], *, actor: str,
                          dry_run: bool = False) -> MandateReport:
    from sqlalchemy import select

    from app.models.country import Country
    from app.models.mandate import Mandate, MandateCounterparty

    if not actor or not actor.strip():
        raise MandateImportError(["actor is required"])
    report = MandateReport()
    issues: list[str] = []
    countries = dict((await db.execute(select(Country.code, Country.id))).all())
    codes = [m.code for m in mandates]
    if len(set(codes)) != len(codes):
        issues.append("a mandate code appears several times in the file")
    for m in mandates:
        if m.country_code and m.country_code not in countries:
            issues.append(f"mandate {m.code}: unknown country {m.country_code}")
    existing = {m.code: m for m in (await db.execute(
        select(Mandate).where(Mandate.code.in_(codes + [c.mandate_code for c in contacts]),
                              Mandate.deleted_at.is_(None)))).scalars()}
    known_codes = set(codes) | set(existing)

    from app.directory.resolve import resolve_names

    resolved = await resolve_names(db, {c.institution_name for c in contacts if c.institution_name}
                                   | {c.entity_name for c in contacts if c.entity_name})
    inst_ids: dict[str, str] = {}
    ent_ids: dict[str, str] = {}
    for c in contacts:
        if c.mandate_code not in known_codes:
            issues.append(f"contact {c.counterparty_name}: unknown mandate {c.mandate_code}")
        for name in (c.institution_name, c.entity_name):
            if not name:
                continue
            hit = resolved.get(name)
            if hit is None or not (hit.institution_id or hit.entity_id):
                issues.append(f"'{name}' not found exactly once in the directory")
                continue
            if hit.institution_id:
                inst_ids[name] = hit.institution_id
            if hit.entity_id:
                ent_ids[name] = hit.entity_id
    if issues:
        raise MandateImportError(issues)

    try:
        by_code = dict(existing)
        for m in mandates:
            values = dict(title=m.title, client_name=m.client_name, country_id=countries.get(m.country_code or ""),
                          sector=m.sector, deal_type=m.deal_type, amount=m.amount, currency=m.currency,
                          maturity_months=m.maturity_months, year=m.year, status=m.status, notes=m.notes)
            if m.code in by_code:
                for k, v in values.items():
                    setattr(by_code[m.code], k, v)
                report.mandates_updated += 1
            else:
                row = Mandate(code=m.code, recorded_by=actor.strip(), **values)
                db.add(row)
                by_code[m.code] = row
                report.mandates_created += 1
        await db.flush()
        for c in contacts:
            mandate = by_code[c.mandate_code]
            name = c.institution_name or c.entity_name or ""
            inst = inst_ids.get(name)
            ent = ent_ids.get(name)
            dup = (await db.execute(select(MandateCounterparty.id).where(
                MandateCounterparty.mandate_id == mandate.id,
                MandateCounterparty.counterparty_name == c.counterparty_name,
                MandateCounterparty.stage == c.stage,
                MandateCounterparty.contact_date.is_(None) if c.contact_date is None
                else MandateCounterparty.contact_date == c.contact_date,
                MandateCounterparty.deleted_at.is_(None)))).first()
            if dup:
                report.contacts_skipped += 1
                continue
            db.add(MandateCounterparty(
                mandate_id=mandate.id, counterparty_name=c.counterparty_name, institution_id=inst, entity_id=ent,
                stage=c.stage, amount=c.amount, currency=c.currency, contact_date=c.contact_date, reason=c.reason,
                notes=c.notes, recorded_by=actor.strip()))
            report.contacts_created += 1
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Import TOMASTEED mandates and institutions approached")
    parser.add_argument("--mandates", required=True)
    parser.add_argument("--counterparties", default=None)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--expect-db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.core.config import database_url_source, get_settings
    from app.core.logging import configure_logging

    os.environ["DB_APPLICATION_NAME"] = "umoa_mandates_import"
    get_settings.cache_clear()
    configure_logging()
    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database

    engine.sync_engine.echo = False
    try:
        mandates = parse_csv(Path(args.mandates).read_text(encoding="utf-8-sig"), MandateRow)
        contacts = parse_csv(Path(args.counterparties).read_text(encoding="utf-8-sig"), ContactRow) \
            if args.counterparties else []
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(db, expect_db=args.expect_db,
                                                    url_source=database_url_source(get_settings()))
            print(verified.message(), flush=True)
            report = await import_mandates(db, mandates, contacts, actor=args.actor, dry_run=args.dry_run)
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    except MandateImportError as err:
        print("REFUSED (nothing written):", flush=True)
        for issue in err.issues:
            print(f"  {issue}", flush=True)
        return 2
    print(json.dumps({"dry_run": args.dry_run, **report.__dict__}, indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
