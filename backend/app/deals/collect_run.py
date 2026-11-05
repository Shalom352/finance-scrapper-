"""
Automated deal collection for one or several sources, outside the ingestion run (controlled runs).

    python -m app.deals.collect_run --source boad --since 2025-01-01
    python -m app.deals.collect_run --source ifc,proparco --since 2024-01-01 --limit 50 --report-file r.json
    python -m app.deals.collect_run --source all --expect-db umoa_discovery_e2e

Sources: umoa-titres, brvm, amf-umoa, ifc, boad, proparco, press (or "all" = DEAL_COLLECTION_SOURCES).
Every created deal is needs_review; re-running is idempotent (ingestion_key + checkpoints). Before any
request, app.deals.db_guard checks current_database(), the Alembic revision (0021 at least) and the
connection's application_name ("deal_collect_run") — exit code 2 if refused. Each source then takes
its own advisory lock (UMOA-Titres shares the lock of app.deals.umoa_titres_run); a source whose lock
is held is reported as skipped.
"""

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

from app.core.logging import configure_logging

APPLICATION_NAME = "deal_collect_run"
MIN_REVISION = 21  # 0021_press_source (0020_deal_collection + the press source)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automated deal collection (needs_review, never merged)")
    parser.add_argument("--source", required=True, help="Comma-separated source keys, or 'all'")
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="First publication / modification date (default: configured lookback)")
    parser.add_argument("--until", type=date.fromisoformat, default=None, help="Last publication date")
    parser.add_argument("--limit", type=int, default=None, help="Pages read per source at most")
    parser.add_argument("--recheck", action="store_true",
                        help="Read every page again whatever its checkpoint (after a parser fix)")
    parser.add_argument("--report-file", default=None, help="Write the full report (JSON) to this file")
    parser.add_argument("--expect-db", default=None,
                        help="Expected current_database(); the run stops before any request if it differs")
    return parser


async def main_async() -> int:
    from app.core.config import database_url_source, get_settings

    os.environ["DB_APPLICATION_NAME"] = APPLICATION_NAME
    get_settings.cache_clear()
    configure_logging()
    args = build_parser().parse_args()

    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database
    from app.services.deal_collection import DEAL_SOURCES, collect, configured_sources

    sources = configured_sources() if args.source == "all" else [s.strip() for s in args.source.split(",") if s.strip()]
    unknown = [s for s in sources if s not in DEAL_SOURCES]
    if unknown:
        print(f"ABANDON: source(s) inconnue(s) {unknown}; attendu: {', '.join(DEAL_SOURCES)}", flush=True)
        return 2
    engine.sync_engine.echo = False
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(
                db, expect_db=args.expect_db, url_source=database_url_source(get_settings()),
                expect_application_name=APPLICATION_NAME, min_revision=MIN_REVISION,
            )
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    print(verified.message(), flush=True)

    async with AsyncSessionLocal() as db:
        result = await collect(db, sources, since=args.since, until=args.until, limit=args.limit,
                               recheck=args.recheck)

    print(json.dumps(result.as_json(), indent=2, ensure_ascii=False, default=str))
    if args.report_file:
        Path(args.report_file).write_text(json.dumps(result.as_json(), indent=2, ensure_ascii=False, default=str),
                                          encoding="utf-8")
    # Any failed source fails the command (a partial failure is never reported as a success).
    return 1 if result.errors else 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
