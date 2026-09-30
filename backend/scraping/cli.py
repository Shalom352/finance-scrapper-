"""
UMOA Banking Intelligence — Scraping CLI Interface

Allows running discovery, downloading, and pipeline tasks from the terminal:
    python -m scraping discover --source bceao --limit 10
    python -m scraping download --source bceao --limit 5
    python -m scraping run --source all --limit 10
    python -m scraping import-deals --file deals.json --actor analyst-1 [--dry-run]
"""
import argparse
import asyncio
import sys

from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from scraping.pipeline import ScrapingPipeline

logger = get_logger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="python -m scraping",
        description="UMOA Banking Intelligence — Document Collection & Discovery CLI",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # ------------------------------------------------------------------
    # Discover command
    # ------------------------------------------------------------------
    discover_p = subparsers.add_parser("discover", help="Discover documents from official sources")
    discover_p.add_argument(
        "--source",
        choices=["bceao", "cb-umoa", "all"],
        default="bceao",
        help="Official source to inspect (default: bceao)",
    )
    discover_p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum documents to discover per source",
    )
    discover_p.add_argument(
        "--no-db",
        action="store_true",
        help="Dry run: print discovered documents without database write",
    )

    # ------------------------------------------------------------------
    # Download command
    # ------------------------------------------------------------------
    download_p = subparsers.add_parser("download", help="Download pending documents from database")
    download_p.add_argument(
        "--source",
        choices=["bceao", "cb-umoa", "all"],
        default="all",
        help="Filter pending documents by source (default: all)",
    )
    download_p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum documents to download in this batch",
    )

    # ------------------------------------------------------------------
    # Run command (discover + download)
    # ------------------------------------------------------------------
    run_p = subparsers.add_parser("run", help="Run full discovery and download pipeline")
    run_p.add_argument(
        "--source",
        choices=["bceao", "cb-umoa", "all"],
        default="bceao",
        help="Official source connector (default: bceao)",
    )
    run_p.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Maximum documents to process (default: 10)",
    )

    # ------------------------------------------------------------------
    # Parse command (PDF extraction & classification)
    # ------------------------------------------------------------------
    parse_p = subparsers.add_parser("parse", help="Parse downloaded PDF documents")
    parse_p.add_argument(
        "--file",
        type=str,
        default=None,
        help="Parse a standalone PDF file directly from path",
    )
    parse_p.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Specific document ID to parse from database",
    )
    parse_p.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum downloaded documents to parse (default: 5)",
    )

    # ------------------------------------------------------------------
    # Extract command (Financial table extraction & metric mapping)
    # ------------------------------------------------------------------
    extract_p = subparsers.add_parser("extract", help="Extract tabular financial metrics from PDF documents")
    extract_p.add_argument(
        "--file",
        type=str,
        default=None,
        help="Extract financial metrics from a standalone PDF file directly from path",
    )
    extract_p.add_argument(
        "--doc-id",
        type=str,
        default=None,
        help="Specific document ID to extract from database",
    )
    extract_p.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum documents to extract financial data from (default: 5)",
    )

    # ------------------------------------------------------------------
    # Import deals (Phase 13): structured import only, no extraction
    # ------------------------------------------------------------------
    deals_p = subparsers.add_parser(
        "import-deals",
        help="Import deals from a JSON or CSV file (provenance required; every deal starts as needs_review)",
    )
    deals_p.add_argument("--file", type=str, required=True, help="Path to a .json or .csv file")
    deals_p.add_argument("--actor", type=str, required=True, help="Person responsible for the import (audit trail)")
    deals_p.add_argument("--dry-run", action="store_true", help="Validate everything, write nothing")

    return parser


async def run_import_deals(args: argparse.Namespace) -> int:
    """All-or-nothing import. Exit code 0 = imported (or dry run OK), 2 = refused, nothing written."""
    from pathlib import Path

    from scraping.deals.importer import DealImportError, import_file

    path = Path(args.file)
    try:
        text = path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeDecodeError) as err:
        print(f"[!] Cannot read {path.name}: {err.__class__.__name__}")
        return 2
    async with AsyncSessionLocal() as session:
        try:
            report = await import_file(session, path.name, text, actor=args.actor, dry_run=args.dry_run)
        except DealImportError as err:
            print(f"[!] Import refused ({len(err.issues)} issue(s)); nothing was written:")
            for issue in err.issues:
                where = f"record {issue.row}" if issue.row else "file"
                print(f"    - {where} / {issue.field}: [{issue.code}] {issue.message}")
            return 2
    verb = "validated (dry run, nothing written)" if report.dry_run else "imported as needs_review"
    print(f"[+] {len(report.created_ids)} deal(s) {verb}.")
    for new_id, other_id, criteria in report.duplicate_candidates:
        print(f"    duplicate candidate: {new_id} <-> {other_id} ({', '.join(criteria)}) -> human review required")
    return 0


async def run_cli(args: argparse.Namespace) -> int:
    """Execute the parsed CLI command."""
    configure_logging()
    if args.command == "import-deals":
        return await run_import_deals(args)
    pipeline = ScrapingPipeline()

    sources = ["bceao", "cb-umoa"] if getattr(args, "source", None) == "all" else [getattr(args, "source", "bceao")]

    # Command: discover
    if args.command == "discover":
        for src in sources:
            print(f"\n[*] Starting discovery for {src.upper()}...")
            if args.no_db:
                docs = await pipeline.discover_source(src, db=None, limit=args.limit)
            else:
                async with AsyncSessionLocal() as session:
                    docs = await pipeline.discover_source(src, db=session, limit=args.limit)

            print(f"[+] Found {len(docs)} document(s) for {src.upper()}:")
            for idx, doc in enumerate(docs, 1):
                year_str = f" ({doc.period_year})" if doc.period_year else ""
                print(f"  {idx}. [{doc.document_type}] {doc.title}{year_str}")
                print(f"     URL: {doc.url}")

        return 0

    # Command: download
    if args.command == "download":
        filter_source = None if args.source == "all" else args.source.upper()
        print(f"\n[*] Starting download of pending documents (source: {filter_source or 'ALL'})...")
        async with AsyncSessionLocal() as session:
            results = await pipeline.download_pending_documents(
                session,
                source_short_name=filter_source,
                limit=args.limit,
            )

        success_count = sum(1 for _, res, _ in results if res.success)
        print(f"[+] Download batch completed: {success_count}/{len(results)} successful.")
        return 0

    # Command: run (discover + download)
    if args.command == "run":
        for src in sources:
            print(f"\n[*] Running pipeline for {src.upper()} (limit: {args.limit})...")
            async with AsyncSessionLocal() as session:
                discovered = await pipeline.discover_source(src, db=session, limit=args.limit)
                print(f"[+] Discovered {len(discovered)} documents. Starting download...")
                downloads = await pipeline.download_pending_documents(
                    session,
                    source_short_name=src.upper(),
                    limit=args.limit,
                )
                success_count = sum(1 for _, res, _ in downloads if res.success)
                print(f"[+] Pipeline completed for {src.upper()}: {success_count}/{len(downloads)} downloaded.")

        return 0

    # Command: parse
    if args.command == "parse":
        if args.file:
            from scraping.parsing.pdf_parser import PDFParser

            parser = PDFParser()
            print(f"\n[*] Parsing standalone PDF: {args.file}...")
            parsed = await parser.parse(args.file)
            print(f"[+] Pages: {parsed.page_count}")
            print(f"[+] Scan status: {parsed.scan_status}")
            print(f"[+] Total characters: {parsed.total_char_count}")
            print(f"[+] Classification: {parsed.document_classification} (confidence: {parsed.classification_confidence})")
            print("[+] Financial statement candidate pages:")
            for st, pages_list in parsed.financial_statement_candidates.items():
                if pages_list:
                    print(f"    - {st}: {pages_list}")
            return 0

        print("\n[*] Starting parsing of downloaded documents from database...")
        async with AsyncSessionLocal() as session:
            results = await pipeline.parse_downloaded_documents(
                session,
                document_id=args.doc_id,
                limit=args.limit,
            )
        success_count = sum(1 for _, parsed_item in results if parsed_item is not None)
        print(f"[+] Parsing batch completed: {success_count}/{len(results)} successful.")
        return 0

    # Command: extract
    if args.command == "extract":
        if args.file:
            from scraping.parsing.financial_extractor import FinancialExtractor
            from scraping.parsing.pdf_parser import PDFParser

            parser = PDFParser()
            extractor = FinancialExtractor()
            print(f"\n[*] Extracting financial data from standalone PDF: {args.file}...")
            parsed = await parser.parse(args.file)
            points = await extractor.extract_from_parsed_document(parsed, args.file)
            print(f"[+] Total metrics extracted: {len(points)}")
            for pt in points:
                status_str = f"[{pt.status.upper()}]"
                val_norm = f"{pt.value_normalized:,.2f}" if pt.value_normalized is not None else "N/A"
                print(f"  {status_str} {pt.metric_code} ({pt.period_year}): {pt.value_original} -> {val_norm} {pt.currency_normalized or ''} (confidence: {pt.confidence_score})")
                if pt.notes:
                    print(f"      notes: {pt.notes}")
            return 0

        print("\n[*] Starting financial data extraction from database...")
        async with AsyncSessionLocal() as session:
            results = await pipeline.extract_financial_data(
                session,
                document_id=args.doc_id,
                limit=args.limit,
            )
        total_pts = sum(len(pts) for _, pts in results)
        print(f"[+] Extraction completed across {len(results)} document(s): {total_pts} data points.")
        return 0

    return 1


def main() -> None:
    """Entry point for the CLI script."""
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    parser = build_parser()
    args = parser.parse_args()
    code = asyncio.run(run_cli(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
