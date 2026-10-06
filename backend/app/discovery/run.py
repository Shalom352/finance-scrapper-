"""
UMOA Financial Intelligence — Entity & Source Discovery CLI (Phase 15).

    python -m app.discovery.run --universe UMOA.BANKING
    python -m app.discovery.run --universe UMOA.BANKING --countries CI,SN --historical-years 5
    python -m app.discovery.run --universe UMOA.BANKING --report-only --report-file coverage.md

The database is the one configured by DATABASE_URL / POSTGRES_* (see app.core.config).
"""

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.constants.discovery import UMOA_COUNTRY_CODES, UNIVERSE_BANKING
from app.core.logging import configure_logging, get_logger

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="UMOA Entity & Source Discovery Engine")
    parser.add_argument("--universe", default=UNIVERSE_BANKING, choices=[UNIVERSE_BANKING])
    parser.add_argument("--countries", default=",".join(UMOA_COUNTRY_CODES),
                        help="Comma-separated ISO codes (default: the 8 UMOA countries)")
    parser.add_argument("--historical-years", type=int, default=5,
                        help="Years searched for institution publications (current year + N)")
    parser.add_argument("--fascicle-editions", type=int, default=1,
                        help="Number of most recent BCEAO fascicle editions to process")
    parser.add_argument("--retry-now", action="store_true",
                        help="Reopen NOT_FOUND gaps before their retry date (e.g. after an extractor change)")
    parser.add_argument("--reference-editions", type=int, default=1,
                        help="Number of most recent BCEAO list communiqués to process")
    parser.add_argument("--max-rounds", type=int, default=30, help="Safety cap (never reported as complete)")
    parser.add_argument("--trigger-type", default="cli", choices=["cli", "manual", "scheduled"])
    parser.add_argument("--report-only", action="store_true", help="Only print the coverage report")
    parser.add_argument("--report-file", default=None, help="Also write the report (markdown) to this file")
    return parser


async def main_async() -> int:
    configure_logging()
    args = build_parser().parse_args()
    countries = tuple(c.strip().upper() for c in args.countries.split(",") if c.strip())
    unknown = set(countries) - set(UMOA_COUNTRY_CODES)
    if unknown:
        print(f"Unknown country codes: {sorted(unknown)}", file=sys.stderr)
        return 2

    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from scraping.universe.engine import DiscoveryEngine
    from scraping.universe.report import build_report

    engine.sync_engine.echo = False  # the SQL echo of development mode would drown the report

    async with AsyncSessionLocal() as session:
        run_id = None
        if not args.report_only:
            year = datetime.now(UTC).year
            run = await DiscoveryEngine(max_rounds=args.max_rounds).run(
                session,
                universe_code=args.universe,
                trigger_type=args.trigger_type,
                country_codes=countries,
                target_years=[year - i for i in range(args.historical_years + 1)],
                options={"fascicle_editions": args.fascicle_editions,
                         "reference_editions": args.reference_editions, "retry_now": args.retry_now},
            )
            run_id = run.id
            print(f"Run {run.id}: {run.stop_condition} — {run.stop_reason}")
        report = await build_report(session, args.universe, run_id)
    print(report)
    if args.report_file:
        Path(args.report_file).write_text(report, encoding="utf-8")
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
