"""
Automatic validation (Phase 21) — command line.

    python -m app.validation.run --expect-db <db> [--target all|financial_data|deals] [--dry-run]
                                 [--scope-classes A,B,C] [--storage-root data/downloads]
    python -m app.validation.run --expect-db <db> --revoke-all --actor <id> --reason "<motif>"

Every automatic decision is traced (audit event ``auto_validate``) and can be withdrawn by a human,
row by row in the Review Center or all at once with ``--revoke-all``.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Automatic validation (reversible)")
    parser.add_argument("--expect-db", required=True)
    parser.add_argument("--target", choices=["all", "financial_data", "deals"], default="all")
    parser.add_argument("--scope-classes", default=None)
    parser.add_argument("--storage-root", default=None)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--revoke-all", action="store_true")
    parser.add_argument("--actor", default=None)
    parser.add_argument("--reason", default=None)
    args = parser.parse_args()

    from app.core.config import database_url_source, get_settings
    from app.core.logging import configure_logging

    os.environ["DB_APPLICATION_NAME"] = "umoa_auto_validation"
    get_settings.cache_clear()
    configure_logging()
    settings = get_settings()
    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database
    from scraping.validation.automatic import (
        RevokeError,
        revoke_all,
        validate_deals,
        validate_financial_data,
    )

    engine.sync_engine.echo = False
    classes = tuple(c.strip() for c in (args.scope_classes or settings.auto_validation_scope_classes).split(",")
                    if c.strip())
    root = Path(args.storage_root or settings.documents_storage_path)
    out: dict = {"dry_run": args.dry_run}
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(db, expect_db=args.expect_db,
                                                    url_source=database_url_source(settings))
            print(verified.message(), flush=True)
            if args.revoke_all:
                out["revoked"] = await revoke_all(db, actor=args.actor or "", reason=args.reason or "",
                                                  dry_run=args.dry_run)
            else:
                if args.target in ("all", "financial_data"):
                    out["financial_data"] = (await validate_financial_data(
                        db, storage_root=root, scope_classes=classes, dry_run=args.dry_run)).summary()
                if args.target in ("all", "deals"):
                    out["deals"] = (await validate_deals(db, dry_run=args.dry_run)).summary()
    except (TargetDatabaseError, RevokeError) as err:
        print(err, flush=True)
        return 2
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
