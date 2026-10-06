"""
Re-read the stated unit of already-extracted institution statements (dry run by default).

    python -m app.validation.reread_units --expect-db <db> --storage-root data/discovery_e2e [--apply]

Corrects only rows that are not human-protected; never changes a status or a raw value.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Re-read stated units of institution statements")
    parser.add_argument("--expect-db", required=True)
    parser.add_argument("--storage-root", default=None)
    parser.add_argument("--apply", action="store_true", help="Write the corrections (default: dry run)")
    args = parser.parse_args()

    from app.core.config import database_url_source, get_settings
    from app.core.logging import configure_logging

    os.environ["DB_APPLICATION_NAME"] = "umoa_unit_reread"
    get_settings.cache_clear()
    configure_logging()
    settings = get_settings()
    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database
    from scraping.storage.manager import StorageManager
    from scraping.universe.documents import DocumentRegistrar
    from scraping.universe.unit_repair import reread_units

    engine.sync_engine.echo = False
    registrar = DocumentRegistrar(StorageManager(args.storage_root or settings.documents_storage_path))
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(db, expect_db=args.expect_db,
                                                    url_source=database_url_source(settings))
            print(verified.message(), flush=True)
            report = await reread_units(db, registrar, dry_run=not args.apply)
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    print(json.dumps({"dry_run": not args.apply, **report.summary()}, indent=2, ensure_ascii=False, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
