"""
Financing directory seed (Phase 20) — development finance institutions and guarantee funds.

    python -m app.directory.seed --file reference/financing_institutions.json --expect-db <db> [--dry-run]

Each entry of the reference file is registered as an Entity (class ``financial_institution``)
from its OWN official website only. An entity that already exists (same canonical or short name)
is never modified. Banks are NOT created here: they come from the official BCEAO / CB-UMOA lists
(discovery engine, Phase 15).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DIRECTORY_TYPES = ("development_bank", "guarantee_fund")


@dataclass
class SeedReport:
    created: list[str] = field(default_factory=list)
    existing: list[str] = field(default_factory=list)


def validate(entries: list[dict[str, Any]]) -> None:
    problems = []
    names = set()
    for i, e in enumerate(entries, start=1):
        if not e.get("canonical_name") or not e.get("short_name"):
            problems.append(f"#{i}: canonical_name and short_name are required")
        if e.get("entity_type") not in DIRECTORY_TYPES:
            problems.append(f"#{i}: entity_type must be one of {DIRECTORY_TYPES}")
        if not re.match(r"^https://[^\s/]+", e.get("website") or ""):
            problems.append(f"#{i}: an official https website is required")
        key = (e.get("canonical_name") or "").upper()
        if key in names:
            problems.append(f"#{i}: duplicate canonical_name")
        names.add(key)
    if problems:
        raise ValueError("invalid directory file:\n  " + "\n  ".join(problems))


async def seed(db, entries: list[dict[str, Any]], *, dry_run: bool = False) -> SeedReport:
    from sqlalchemy import func, or_, select

    from app.models.country import Country
    from app.models.entity import Entity

    validate(entries)
    countries = dict((await db.execute(select(Country.code, Country.id))).all())
    report = SeedReport()
    try:
        for e in entries:
            found = (await db.execute(select(Entity.id).where(
                Entity.deleted_at.is_(None),
                or_(func.upper(Entity.canonical_name) == e["canonical_name"].upper(),
                    func.upper(Entity.short_name) == e["short_name"].upper()),
            ))).first()
            if found:
                report.existing.append(e["short_name"])
                continue
            db.add(Entity(
                entity_class="financial_institution", entity_type=e["entity_type"], canonical_name=e["canonical_name"],
                short_name=e["short_name"], country_id=countries.get(e.get("country_code") or ""),
                website=e["website"], status="active",
                description=f"Annuaire de financement (Phase 20) — périmètre : {e.get('scope', 'non précisé')}. "
                            f"Enregistré depuis le site officiel {e['website']}.",
            ))
            report.created.append(e["short_name"])
        if dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Seed the financing directory (DFIs, guarantee funds)")
    parser.add_argument("--file", required=True)
    parser.add_argument("--expect-db", required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from app.core.config import database_url_source, get_settings
    from app.core.logging import configure_logging

    os.environ["DB_APPLICATION_NAME"] = "umoa_directory_seed"
    get_settings.cache_clear()
    configure_logging()
    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database

    engine.sync_engine.echo = False
    entries = json.loads(Path(args.file).read_text(encoding="utf-8"))["institutions"]
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(db, expect_db=args.expect_db,
                                                    url_source=database_url_source(get_settings()))
            print(verified.message(), flush=True)
            report = await seed(db, entries, dry_run=args.dry_run)
    except (TargetDatabaseError, ValueError) as err:
        print(err, flush=True)
        return 2
    print(json.dumps({"dry_run": args.dry_run, "created": report.created, "already_present": report.existing},
                     indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
