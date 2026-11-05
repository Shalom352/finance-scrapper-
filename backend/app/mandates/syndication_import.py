"""
Syndication tracker import from the command line (migration 0022, docs/syndication.md).

    python -m app.mandates.syndication_import --file backend/data/private/suivi.xlsx --actor <id> \
        --expect-db <db> --dry-run
    python -m app.mandates.syndication_import --file ... --actor <id> --expect-db <db> \
        --map-sheet "Cité Admnisitrative (1)=TOG | Etat du Togo - Cité Administrative" \
        [--keep platform | --keep excel | --decide <conflict id>=excel ...]

--dry-run prints the plan (creations, updates, conflicts, names to link) and writes nothing but the
preview record. Without it, every conflict needs a decision (--keep for all, or --decide per conflict).
Same guard as the other runners (app.deals.db_guard): checked before anything is read or written.
"""
import argparse
import asyncio
import json
import os
from pathlib import Path

from app.core.logging import configure_logging

APPLICATION_NAME = "syndication_import"
MIN_REVISION = 22  # 0022_syndication


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Import the TOMASTEED syndication tracker (Excel)")
    p.add_argument("--file", required=True, help="The .xlsx workbook (keep it in backend/data/private/)")
    p.add_argument("--actor", required=True, help="Who imports (recorded on every row)")
    p.add_argument("--expect-db", default=None, help="Expected current_database()")
    p.add_argument("--map-sheet", action="append", default=[],
                   help='Detail sheet -> deal: "<sheet title>=<deal label or code>" (repeatable)')
    p.add_argument("--keep", choices=["platform", "excel"], default=None, help="Decision for EVERY conflict")
    p.add_argument("--decide", action="append", default=[], help='"<conflict id>=excel|platform" (repeatable)')
    p.add_argument("--dry-run", action="store_true", help="Preview only")
    return p


async def main_async() -> int:
    from app.core.config import database_url_source, get_settings

    os.environ["DB_APPLICATION_NAME"] = APPLICATION_NAME
    get_settings.cache_clear()
    configure_logging()
    args = build_parser().parse_args()

    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database
    from app.services import syndication as svc

    path = Path(args.file)
    if not path.is_file():
        print(f"ABANDON: file not found: {path}", flush=True)
        return 2
    mapping = {}
    for item in args.map_sheet:
        sheet, _, target = item.partition("=")
        if not sheet or not target:
            print(f"ABANDON: --map-sheet expects 'sheet=deal', got {item!r}", flush=True)
            return 2
        mapping[sheet.strip()] = target.strip()
    engine.sync_engine.echo = False
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(
                db, expect_db=args.expect_db, url_source=database_url_source(get_settings()),
                expect_application_name=APPLICATION_NAME, min_revision=MIN_REVISION)
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    print(verified.message(), flush=True)

    async with AsyncSessionLocal() as db:
        try:
            row = await svc.preview(db, path.read_bytes(), path.name, actor=args.actor, sheet_mapping=mapping)
        except svc.SyndicationError as err:
            print(f"REFUSED: {err} {json.dumps(err.detail, default=str) if err.detail else ''}", flush=True)
            return 1
        plan = row.plan
        print(json.dumps({"import_id": row.id, "file_updated_on": plan["file_updated_on"], "counts": plan["counts"],
                          "unresolved_names": plan["unresolved_names"], "detail_sheets": plan["detail_sheets"],
                          "ignored_sheets": plan["ignored_sheets"], "warnings": plan["warnings"],
                          "conflicts": [{"id": c["id"], "platform": c["platform"], "excel_now": c["excel_now"]}
                                        for c in plan["conflicts"]]}, indent=2, ensure_ascii=False, default=str))
        if args.dry_run:
            print("Dry run: nothing written (the preview is kept in syndication_imports).", flush=True)
            return 0
        decisions = {c["id"]: args.keep for c in plan["conflicts"]} if args.keep else {}
        for item in args.decide:
            cid, _, choice = item.rpartition("=")
            decisions[cid] = choice
        try:
            applied = await svc.apply(db, row.id, actor=args.actor, decisions=decisions)
        except svc.SyndicationError as err:
            print(f"REFUSED: {err}", flush=True)
            return 1
    print(json.dumps({"applied": applied.id, "counts": applied.counts}, indent=2, default=str), flush=True)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
