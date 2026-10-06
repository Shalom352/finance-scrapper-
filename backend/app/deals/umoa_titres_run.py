"""
UMOA-Titres auction results -> sovereign_bond deals (OAT), through the Phase 13 importer.

    python -m app.deals.umoa_titres_run --since 2025-01-01
    python -m app.deals.umoa_titres_run --urls URL1,URL2 --since 2025-01-01   # controlled sample
    python -m app.deals.umoa_titres_run --since 2025-01-01 --expect-db umoa_discovery_e2e --report-file report.json

Every created deal is needs_review. Re-running is idempotent (ingestion_key).
The database is the one configured by DATABASE_URL / POSTGRES_* (see app.core.config). Before any
request, app.deals.db_guard checks current_database(), the Alembic revision and the connection's
application_name ("umoa_titres_run"; the lock connection is "umoa_titres_run:lock") (exit code 2 if refused),
then app.deals.run_lock takes an advisory lock: only one runner per database (exit code 3 if another
umoa_titres_run is already active).
"""

import argparse
import asyncio
import json
import os
from datetime import date
from pathlib import Path

from app.core.logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UMOA-Titres OAT auction results ingestion")
    parser.add_argument("--since", type=date.fromisoformat, required=True, help="First auction date (YYYY-MM-DD)")
    parser.add_argument("--until", type=date.fromisoformat, default=None, help="Last auction date (YYYY-MM-DD)")
    parser.add_argument("--urls", default=None, help="Comma-separated emission page URLs (default: the full index)")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between two requests to umoatitres.org")
    parser.add_argument("--report-file", default=None, help="Write the full report (JSON) to this file")
    parser.add_argument("--expect-db", default=None,
                        help="Expected current_database(); the run stops before any request if it differs")
    return parser


async def main_async() -> int:
    from app.core.config import database_url_source, get_settings
    from app.deals.db_guard import RUNNER_APPLICATION_NAME

    # Every connection of this process announces the runner (pg_stat_activity). Set before the
    # settings are read and before app.db.engine is imported (the engine is built at import).
    os.environ["DB_APPLICATION_NAME"] = RUNNER_APPLICATION_NAME
    get_settings.cache_clear()
    configure_logging()
    args = build_parser().parse_args()

    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, verify_target_database
    from app.deals.run_lock import single_run_lock
    from scraping.deals.umoa_titres_ingest import UmoaTitresAuctionIngestor
    from scraping.universe.http import OfficialFetcher

    engine.sync_engine.echo = False
    # Guard first: no HTTP request and no write before the target database is verified.
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(
                db,
                expect_db=args.expect_db,
                url_source=database_url_source(get_settings()),
                expect_application_name=RUNNER_APPLICATION_NAME,
            )
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    print(verified.message(), flush=True)

    urls = [u.strip() for u in args.urls.split(",") if u.strip()] if args.urls else None
    async with single_run_lock(engine) as lock:
        if not lock.acquired:
            print(lock.refusal(verified.name), flush=True)
            return 3
        async with OfficialFetcher(delay_seconds=args.delay) as fetcher, AsyncSessionLocal() as db:
            report = await UmoaTitresAuctionIngestor(fetcher).run(
                db, since=args.since, until=args.until, urls=urls
            )

    summary = report.summary()
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    if args.report_file:
        full = {
            **summary,
            "deal_ids": report.deal_ids,
            "outcomes": {url: {"outcome": o, "detail": d} for url, (o, d) in report.outcomes.items()},
            "refusals": [
                {"url": r.url, "country": r.country, "auction_date": str(r.auction_date) if r.auction_date else None,
                 "references": r.references, "issue": r.issue, "conflict": r.conflict}
                for r in report.refusals
            ],
            "parser_flags_detail": report.flags,
        }
        Path(args.report_file).write_text(json.dumps(full, indent=2, ensure_ascii=False), encoding="utf-8")
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
