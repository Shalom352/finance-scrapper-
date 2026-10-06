"""
Pilot loader (Phase 19) — 28-deal pilot of audits/ape_amf/08_pilote.md, in CONTROLLED entry.

    python -m app.deals.pilot_load --manifest pilot/pilot_manifest.json --expect-db umoa_pilot \
        --files ../audits/ape_amf --actor analyste-1 [--dry-run]

The manifest lists, explicitly, the sources and documents of the pilot (official URLs), the deals
(importer records whose sources point to a document KEY) and the SGI -> bank links. Rules:
  - the target database is checked first (never ``umoa_banking``; Alembic 0016 minimum);
  - sources / documents are REGISTERED explicitly from the manifest (matched by URL, never guessed);
    with ``--files``, a local copy gives the SHA-256, the page count and lets every quotation be
    checked against the text of its page (a quotation that is not on its page refuses the run);
  - institutions are resolved by EXACT official name only; anything else stays "not in directory";
  - deals go through the Phase 13 importer: all ``needs_review``, field-level provenance, audit event;
  - idempotent: ``ingestion_key = pilot:<key>``; already imported deals / links are skipped.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

PILOT_APPLICATION_NAME = "umoa_pilot_load"
MIN_PILOT_REVISION = 16


def normalize_text(value: str) -> str:
    """Comparison key for quotations: NFKC, typographic apostrophes, hyphenation, spaces, case."""
    value = unicodedata.normalize("NFKC", value).replace("’", "'").replace(" ", " ")
    value = re.sub(r"-\s+", "", value)  # "investisse- ments" (line-break hyphenation)
    return re.sub(r"\s+", " ", value).strip().lower()


@dataclass
class PilotReport:
    sources_created: int = 0
    documents_created: int = 0
    quotations_checked: int = 0
    deals_created: list[str] = field(default_factory=list)
    deals_skipped: list[str] = field(default_factory=list)
    links_created: int = 0
    links_skipped: int = 0
    unresolved_names: list[str] = field(default_factory=list)


class PilotError(Exception):
    pass


def _page_texts(path: Path) -> list[str]:
    import pymupdf

    with pymupdf.open(path) as doc:
        return [normalize_text(page.get_text()) for page in doc]


def _html_text(path: Path) -> str:
    import html

    raw = path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", raw)
    return normalize_text(html.unescape(re.sub(r"<[^>]+>", " ", raw)))


def check_quotations(manifest: dict[str, Any], files_root: Path | None) -> int:
    """Every quotation whose document has a local copy must be found on its page (text reading only)."""
    if files_root is None:
        return 0
    docs = {d["key"]: d for d in manifest["documents"]}
    cache: dict[str, list[str]] = {}
    problems: list[str] = []
    checked = 0

    def text_of(doc_key: str, page: int) -> str | None:
        doc = docs[doc_key]
        local = doc.get("local_file")
        if not local:
            return None
        path = files_root / local
        if not path.is_file():
            raise PilotError(f"local copy not found: {path}")
        if doc_key not in cache:
            cache[doc_key] = _page_texts(path) if path.suffix.lower() == ".pdf" else [_html_text(path)]
        pages = cache[doc_key]
        return pages[page - 1] if 0 < page <= len(pages) else ""

    for deal in manifest["deals"]:
        srcs = {s["ref"]: s for s in deal["sources"]}
        quotes = [(s["document"], s["page"], s.get("excerpt"), "text", deal["key"]) for s in deal["sources"]]
        quotes += [
            (srcs[p["source_ref"]]["document"], p.get("page") or srcs[p["source_ref"]]["page"], p.get("excerpt"),
             p.get("extraction_method") or "text", deal["key"])
            for p in deal.get("participants", [])
        ]
        for doc_key, page, excerpt, method, key in quotes:
            if not excerpt or method != "text":
                continue  # visual readings are reviewed by a human from the page image
            page_text = text_of(doc_key, page)
            if page_text is None:
                continue
            checked += 1
            if normalize_text(excerpt) not in page_text:
                problems.append(f"{key}: quotation not found on {doc_key} p.{page}: {excerpt[:80]!r}")
    if problems:
        raise PilotError("quotation check failed:\n  " + "\n  ".join(problems))
    return checked


async def _register(db, manifest: dict[str, Any], files_root: Path | None, report: PilotReport) -> dict[str, tuple[str, str]]:
    """Sources and documents of the manifest (matched by URL). Returns doc key -> (document_id, source_id)."""
    from sqlalchemy import select

    from app.models.document import Document
    from app.models.source import Source

    source_ids: dict[str, str] = {}
    for s in manifest["sources"]:
        existing = (await db.execute(select(Source).where(Source.url == s["url"]))).scalars().first()
        if existing is None:
            existing = Source(name=s["name"], url=s["url"], source_type=s["source_type"],
                              priority=s.get("priority", 2), country_code=s.get("country_code"),
                              language=s.get("language", "fr"), publisher=s.get("publisher"),
                              description="Registered by the Phase 19 pilot loader (manifest).")
            db.add(existing)
            await db.flush()
            report.sources_created += 1
        source_ids[s["key"]] = existing.id

    out: dict[str, tuple[str, str]] = {}
    for d in manifest["documents"]:
        source_id = source_ids[d["source"]]
        existing = (
            await db.execute(select(Document).where(Document.url == d["url"], Document.deleted_at.is_(None)))
        ).scalars().first()
        if existing is None:
            file_hash = size = None
            page_count = d.get("page_count")
            if files_root is not None and d.get("local_file"):
                path = files_root / d["local_file"]
                data = path.read_bytes()
                file_hash, size = hashlib.sha256(data).hexdigest(), len(data)
                if path.suffix.lower() == ".pdf":
                    real = len(_page_texts(path))
                    if page_count is not None and page_count != real:
                        raise PilotError(f"{d['key']}: manifest page_count {page_count} != file {real}")
                    page_count = real
                same = (await db.execute(select(Document).where(Document.file_hash == file_hash))).scalars().first()
                if same is not None:  # same file already stored under another URL: reuse it
                    out[d["key"]] = (same.id, same.source_id)
                    continue
            existing = Document(
                title=d["title"], document_type=d["document_type"], source_id=source_id, url=d["url"],
                file_hash=file_hash, file_size=size, page_count=page_count,
                download_status="downloaded" if file_hash else "pending", extraction_status="skipped",
                published_at=date.fromisoformat(d["published_at"]) if d.get("published_at") else None,
                language=d.get("language", "fr"), document_scope=d.get("document_scope", "unknown"),
            )
            db.add(existing)
            await db.flush()
            report.documents_created += 1
        out[d["key"]] = (existing.id, existing.source_id)
    return out


async def _institutions_by_name(db, names: set[str]):
    """Exact names after typographic normalization (official, commercial, former names, acronyms)."""
    from app.directory.resolve import resolve_names

    return await resolve_names(db, names)


def _records(manifest: dict[str, Any], docs: dict[str, tuple[str, str]], insts: dict[str, str],
             skip: set[str], report: PilotReport) -> list[dict[str, Any]]:
    records = []
    for deal in manifest["deals"]:
        key = f"pilot:{deal['key']}"
        if key in skip:
            report.deals_skipped.append(deal["key"])
            continue
        rec = {k: v for k, v in deal.items() if k not in ("key", "sources", "participants", "case")}
        rec["ingestion_key"] = key
        rec["sources"] = []
        for s in deal["sources"]:
            doc_id, src_id = docs[s["document"]]
            rec["sources"].append({**{k: v for k, v in s.items() if k != "document"},
                                   "document_id": doc_id, "source_id": src_id})
        rec["participants"] = []
        for p in deal.get("participants", []):
            q = {k: v for k, v in p.items() if k != "institution_name"}
            if p.get("institution_name"):
                hit = insts.get(p["institution_name"])
                if hit and (hit.institution_id or hit.entity_id):
                    if hit.institution_id:
                        q["institution_id"] = hit.institution_id
                    if hit.entity_id:
                        q["entity_id"] = hit.entity_id
                else:
                    report.unresolved_names.append(p["institution_name"])
            rec["participants"].append(q)
        records.append(rec)
    return records


async def load(db, manifest: dict[str, Any], *, files_root: Path | None, actor: str, dry_run: bool) -> PilotReport:
    from sqlalchemy import select

    from app.models.deal import Deal, InstitutionLink
    from scraping.deals.importer import import_deals, validate_records

    report = PilotReport(quotations_checked=check_quotations(manifest, files_root))
    try:
        docs = await _register(db, manifest, files_root, report)
        names = {p["institution_name"] for d in manifest["deals"] for p in d.get("participants", [])
                 if p.get("institution_name")}
        names |= {link["to_institution_name"] for link in manifest.get("institution_links", [])
                  if link.get("to_institution_name")}
        insts = await _institutions_by_name(db, names)
        keys = [f"pilot:{d['key']}" for d in manifest["deals"]]
        done = set((await db.execute(select(Deal.ingestion_key).where(Deal.ingestion_key.in_(keys)))).scalars())

        for link in manifest.get("institution_links", []):
            exists = (await db.execute(select(InstitutionLink.id).where(
                InstitutionLink.from_name == link["from_name"], InstitutionLink.source_url == link["source_url"],
                InstitutionLink.deleted_at.is_(None)))).first()
            if exists:
                report.links_skipped += 1
                continue
            to_id = None
            if link["link_level"] == "documented_bank":
                hit = insts.get(link["to_institution_name"])
                to_id = hit.institution_id if hit else None
                if to_id is None:  # never attributed to a bank that is not found EXACTLY
                    report.unresolved_names.append(link["to_institution_name"])
                    report.links_skipped += 1
                    continue
            db.add(InstitutionLink(
                from_name=link["from_name"], link_level=link["link_level"], to_institution_id=to_id,
                group_label=link.get("group_label"), relation=link["relation"], pct=link.get("pct"),
                source_url=link["source_url"], excerpt=link["excerpt"],
                observed_at=date.fromisoformat(link["observed_at"]),
            ))
            report.links_created += 1
        await db.flush()

        records = _records(manifest, docs, insts, done, report)
        if records:
            # The importer commits (or rolls back on dry run) the whole pilot in one transaction.
            result = await import_deals(db, validate_records(records), actor=actor, origin="pilot manifest",
                                        dry_run=dry_run)
            report.deals_created = result.created_ids
        elif dry_run:
            await db.rollback()
        else:
            await db.commit()
    except Exception:
        await db.rollback()
        raise
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Phase 19 pilot loader (controlled entry, needs_review)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--expect-db", required=True, help="Expected current_database() (never umoa_banking)")
    parser.add_argument("--files", default=None, help="Folder holding the local copies (audits/ape_amf)")
    parser.add_argument("--actor", required=True)
    parser.add_argument("--dry-run", action="store_true")
    return parser


async def main_async() -> int:
    from app.core.config import database_url_source, get_settings
    from app.core.logging import configure_logging

    os.environ["DB_APPLICATION_NAME"] = PILOT_APPLICATION_NAME
    get_settings.cache_clear()
    configure_logging()
    args = build_parser().parse_args()

    from app.db.engine import engine
    from app.db.session import AsyncSessionLocal
    from app.deals.db_guard import TargetDatabaseError, revision_number, verify_target_database
    from scraping.deals.importer import DealImportError

    engine.sync_engine.echo = False
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    files_root = Path(args.files) if args.files else None
    try:
        async with AsyncSessionLocal() as db:
            verified = await verify_target_database(db, expect_db=args.expect_db,
                                                    url_source=database_url_source(get_settings()))
            if (revision_number(verified.alembic_version) or 0) < MIN_PILOT_REVISION:
                raise TargetDatabaseError(f"ABANDON: alembic {verified.alembic_version!r}, 0016 minimum requise.")
            print(verified.message(), flush=True)
            report = await load(db, manifest, files_root=files_root, actor=args.actor, dry_run=args.dry_run)
    except TargetDatabaseError as err:
        print(err, flush=True)
        return 2
    except (PilotError, DealImportError) as err:
        print(f"REFUSED (nothing written): {err}", flush=True)
        for issue in getattr(err, "issues", []):
            print(f"  record {issue.row} · {issue.field} · {issue.code} · {issue.message}", flush=True)
        return 2
    print(json.dumps({
        "dry_run": args.dry_run, "sources_created": report.sources_created,
        "documents_created": report.documents_created, "quotations_checked": report.quotations_checked,
        "deals_created": len(report.deals_created), "deals_skipped": report.deals_skipped,
        "links_created": report.links_created, "links_skipped": report.links_skipped,
        "names_not_in_directory": sorted(set(report.unresolved_names)),
    }, indent=2, ensure_ascii=False))
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(main_async()))


if __name__ == "__main__":
    main()
