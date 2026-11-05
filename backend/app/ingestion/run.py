"""
UMOA Banking Intelligence — CLI Ingestion Runner Entrypoint

Enables execution via:
    python -m app.ingestion.run [--year 2026] [--historical-years 5] [--source bceao] [--limit 10] [--force]
    python -m app.ingestion.run --source boad --scope deals --since 2025-01-01
"""

import argparse
import asyncio
import sys
from datetime import date

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.services.ingestion import IngestionService, get_target_years

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="UMOA Banking Intelligence — Automated Ingestion Pipeline Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--source",
        choices=["all", "bceao", "cb-umoa", "brvm", "umoa-titres", "amf-umoa", "ifc", "boad", "proparco", "bidc", "press"],
        default="all",
        help="Official data source to ingest from",
    )
    parser.add_argument(
        "--scope",
        choices=["all", "financial", "deals"],
        default="all",
        help="Phases to run: bank statements (financial), deal collection (deals) or both",
    )
    parser.add_argument("--since", type=date.fromisoformat, default=None,
                        help="Deals: first publication / modification date (default: configured lookback)")
    parser.add_argument("--until", type=date.fromisoformat, default=None,
                        help="Deals: last publication / modification date")
    parser.add_argument(
        "--year",
        type=int,
        default=None,
        help="Single target calendar year to ingest (default: scans current + historical years)",
    )
    parser.add_argument(
        "--historical-years",
        type=int,
        default=None,
        help="Number of historical years to scan (default: from Settings.ingestion_historical_years)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max documents to process per source (useful for testing/dry-runs)",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass active run concurrency checks and force execution",
    )
    parser.add_argument(
        "--trigger-type",
        choices=["cli", "manual", "scheduled"],
        default="cli",
        help="Trigger type metadata recorded in the run log",
    )
    return parser


async def main_async() -> int:
    configure_logging()
    parser = build_parser()
    args = parser.parse_args()

    sources = None if args.source == "all" else [args.source]
    # --year wins; else --historical-years (else the setting) gives current year + N previous years.
    target_years = [args.year] if args.year else get_target_years(historical_years=args.historical_years)

    print("\n================================================================================")
    print("UMOA Banking Intelligence — Ingestion Pipeline (app.ingestion.run)")
    print("================================================================================")
    print(f"Source(s)       : {args.source.upper()} (scope: {args.scope})")
    print(f"Target year(s)  : {', '.join(str(y) for y in target_years)}")
    print(f"Limit/source    : {args.limit or 'Unlimited'}")
    print(f"Trigger type    : {args.trigger_type}")
    print(f"Force execution : {args.force}\n")

    service = IngestionService()
    async with AsyncSessionLocal() as session:
        run = await service.execute_run(
            db=session,
            trigger_type=args.trigger_type,
            target_years=target_years,
            sources=sources,
            limit_per_source=args.limit,
            force=args.force,
            scope=args.scope,
            deal_since=args.since,
            deal_until=args.until,
        )

    print(f"\n[+] Status      : {run.status.upper()}")
    print(f"[+] Run ID      : {run.id}")
    print(f"[+] Target Years: {run.target_years}")
    print(f"[+] Duration    : {run.duration_seconds or 0:.2f}s")
    print(f"[+] Discovered  : {run.documents_found}")
    print(f"[+] Downloaded  : {run.documents_downloaded}")
    print(f"[+] Extracted   : {run.data_points_extracted}")
    print(f"[+] Summary     : {run.summary_text}")
    for key, summary in (run.deal_summary or {}).items():
        if not key.startswith("_"):
            print(f"[+] Deals {key:<11}: created {summary.get('deals_created', 0)}, "
                  f"already imported {summary.get('already_imported', 0)}, "
                  f"duplicate candidates {summary.get('duplicate_candidates', 0)}")

    if run.errors:
        print(f"\n[!] Errors ({len(run.errors)}):")
        for err in run.errors:
            print(f"    - [{err.get('source', 'unknown')}] {err.get('phase')}: {err.get('error')}")

    if run.status in ("completed", "partial_failure"):
        return 0
    if run.status == "skipped_concurrent":
        print("\n[!] Execution skipped: another ingestion run is currently in progress.")
        return 0
    return 1


def main() -> None:
    code = asyncio.run(main_async())
    sys.exit(code)


if __name__ == "__main__":
    main()
