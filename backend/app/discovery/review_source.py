"""Human decision for an official-website candidate found by external search."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime

from sqlalchemy import select

from app.core.logging import configure_logging
from app.db.session import AsyncSessionLocal
from app.models.discovery import EntitySource


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Confirm or retire a candidate institution website")
    parser.add_argument("--entity-id", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--actor", required=True)
    parser.add_argument("--evidence", required=True,
                        help="Short evidence confirming official ownership or explaining retirement")
    parser.add_argument("--decision", choices=("confirm", "retire"), required=True)
    return parser


async def main_async() -> int:
    configure_logging()
    args = build_parser().parse_args()
    if not args.actor.strip() or not args.evidence.strip():
        print("actor and evidence must not be blank", file=sys.stderr)
        return 2
    async with AsyncSessionLocal() as db:
        candidate = (await db.execute(select(EntitySource).where(
            EntitySource.entity_id == args.entity_id, EntitySource.url == args.url,
            EntitySource.link_role == "official_website", EntitySource.lifecycle_status == "CANDIDATE",
            EntitySource.deleted_at.is_(None),
        ))).scalars().first()
        if candidate is None:
            print("candidate official website not found", file=sys.stderr)
            return 1
        now = datetime.now(UTC)
        if args.decision == "confirm":
            candidate.lifecycle_status = "VERIFIED"
            candidate.verified_at = now
            candidate.verification_evidence = f"Human confirmation by {args.actor.strip()}: {args.evidence.strip()}"[:4000]
        else:
            candidate.lifecycle_status = "RETIRED"
            candidate.verification_evidence = f"Human retirement by {args.actor.strip()}: {args.evidence.strip()}"[:4000]
        candidate.last_checked_at = now
        await db.commit()
    action = "confirmed" if args.decision == "confirm" else "retired"
    print(f"Candidate {action}: {args.url}")
    return 0


def main() -> None:
    sys.exit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
