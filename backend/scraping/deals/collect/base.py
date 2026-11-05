"""
Shared machinery of the automated deal collectors (migration 0020).

    discover() -> candidates (url, lastmod) -> polite fetch (robots.txt, crawl-delay per host)
    -> read() pure parser -> register the document -> import_deals(validate_records(...))

Rules enforced here for every source:
  - one outcome per candidate URL (the funnel always reconciles), stored as a checkpoint so a page is
    read again only when its published ``lastmod`` changes;
  - an access restriction (robots.txt, 401/402/403/451, login wall) is reported, never bypassed;
  - an existing ingestion key may fill NULL fields on a deal that still needs review; existing values
    and reviewed / verified deals are never overwritten;
  - the document and its deals are committed together, or not at all;
  - records are built twice: with a placeholder document id to decide, then with the real one.
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import time
from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from typing import Any, ClassVar, Protocol
from urllib.parse import urljoin, urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.deal import Deal, DealCollectionCheckpoint
from app.models.source import Source
from scraping.deals.importer import DealImportError, enrich_existing_deals, import_deals, validate_records
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.http import USER_AGENT, FetchResult

logger = get_logger(__name__)

EXCERPT_MAX = 500
PLACEHOLDER = "pending"
# Outcomes after which an unchanged page is not read again. Transient ones are retried next run.
FINAL_OUTCOMES = ("produced", "already_imported", "out_of_scope", "not_a_deal", "refused", "import_refused")
RESTRICTED_STATUS = (401, 402, 403, 407, 451)
LOGIN_RE = re.compile(r"/(user/)?(login|signin|sign-in|connexion)\b", re.IGNORECASE)


def utcnow() -> datetime:
    return datetime.now(UTC)


def stored_lastmod(lastmod: str | None) -> str | None:
    """The checkpoint column holds 40 characters: a longer marker is stored as its SHA-1 (still compared
    exactly), so its checkpoint never fails and the page is not re-read on every run."""
    if lastmod is None or len(lastmod) <= 40:
        return lastmod
    return hashlib.sha1(lastmod.encode()).hexdigest()


def quote(text: str, limit: int = EXCERPT_MAX) -> str:
    """A short quotation of the source (whitespace collapsed, never rewritten)."""
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


# =========================================================================== fetching
class Fetcher(Protocol):
    async def get(self, url: str) -> FetchResult: ...


class RobotsRules:
    """robots.txt with the ``*`` and ``$`` wildcards (RFC 9309), for our user agent or ``*``.

    The standard library parser ignores wildcards inside paths; a rule such as ``Disallow: */apps/*``
    would then never match. Longest matching rule wins; Allow wins a tie.
    """

    def __init__(self, text: str, agent: str = USER_AGENT) -> None:
        token = agent.split("/")[0].lower()
        groups: list[tuple[list[str], list[tuple[bool, str]], float | None]] = []
        agents: list[str] = []
        rules: list[tuple[bool, str]] = []
        delay: float | None = None
        last_was_agent = False
        for line in text.splitlines():
            line = line.split("#", 1)[0].strip()
            if ":" not in line:
                continue
            key, value = (p.strip() for p in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if not last_was_agent and agents:
                    groups.append((agents, rules, delay))
                    agents, rules, delay = [], [], None
                agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if key in ("allow", "disallow"):
                if value or key == "allow":
                    rules.append((key == "allow", value or "/"))
            elif key == "crawl-delay":
                try:
                    delay = float(value)
                except ValueError:
                    pass
        if agents:
            groups.append((agents, rules, delay))
        mine = [g for g in groups if any(a != "*" and a in token for a in g[0])]
        chosen = mine or [g for g in groups if "*" in g[0]]
        self.rules = [r for g in chosen for r in g[1]]
        delays = [g[2] for g in chosen if g[2] is not None]
        self.crawl_delay = max(delays) if delays else None

    @staticmethod
    def _regex(pattern: str) -> re.Pattern[str]:
        anchored = pattern.endswith("$")
        body = re.escape(pattern[:-1] if anchored else pattern).replace(r"\*", ".*")
        if not body.startswith("/") and not body.startswith(".*"):
            body = "/" + body
        return re.compile(body + ("$" if anchored else ""))

    def allowed(self, url: str) -> bool:
        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        best: tuple[int, bool] | None = None
        for allow, pattern in self.rules:
            if self._regex(pattern).match(path):
                key = (len(pattern), allow)
                if best is None or key > best:
                    best = key
        return True if best is None else best[1]


# robots.txt could not be read (network error, 5xx): its rules are unknown.
ROBOTS_UNKNOWN = RobotsRules("User-agent: *\nDisallow: /")


class PoliteFetcher:
    """robots.txt check + minimum spacing per host = max(configured delay, Crawl-delay)."""

    def __init__(self, inner: Fetcher, *, min_delay: float = 1.0, host_delays: dict[str, float] | None = None,
                 sleep: Callable[[float], Awaitable[Any]] = asyncio.sleep,
                 clock: Callable[[], float] = time.monotonic) -> None:
        self.inner = inner
        self.min_delay = min_delay
        self.host_delays = host_delays or {}  # stricter minimum for some hosts (press: 5 s)
        self._sleep = sleep
        self._clock = clock
        self._robots: dict[str, RobotsRules | None] = {}
        self._last: dict[str, float] = {}

    async def _wait(self, host: str, delay: float) -> None:
        last = self._last.get(host)
        if last is not None:
            remaining = last + delay - self._clock()
            if remaining > 0:
                await self._sleep(remaining)
        self._last[host] = self._clock()

    async def robots(self, url: str) -> RobotsRules | None:
        parsed = urlparse(url)
        root = f"{parsed.scheme}://{parsed.netloc}"
        if root not in self._robots:
            await self._wait(parsed.netloc, max(self.min_delay, self.host_delays.get(parsed.netloc, 0.0)))
            res = await self.inner.get(urljoin(root, "/robots.txt"))
            if res.ok:
                self._robots[root] = RobotsRules(res.text)
            elif res.status_code in (404, 410):
                self._robots[root] = None  # no robots.txt: nothing is disallowed
            else:
                # Unreachable or server error: the rules are unknown, so nothing is read on this host
                # in this run (retried next run) — never "everything allowed" (audit 22/10/2026, M3).
                self._robots[root] = ROBOTS_UNKNOWN
        return self._robots[root]

    async def get(self, url: str) -> FetchResult:
        rules = await self.robots(url)
        if rules is ROBOTS_UNKNOWN:
            return FetchResult(url=url, error="robots_unavailable")
        if rules is not None and not rules.allowed(url):
            return FetchResult(url=url, error="robots_disallowed")
        host = urlparse(url).netloc
        delay = max(self.min_delay, self.host_delays.get(host, 0.0), (rules.crawl_delay if rules else None) or 0.0)
        await self._wait(host, delay)
        return await self.inner.get(url)


def is_restricted(res: FetchResult) -> bool:
    if res.error == "robots_disallowed" or res.status_code in RESTRICTED_STATUS:
        return True
    return bool(res.final_url and res.final_url != res.url and LOGIN_RE.search(urlparse(res.final_url).path))


def parse_sitemap(xml: str) -> tuple[list[tuple[str, str | None]], list[str]]:
    """(urls with their lastmod, child sitemaps) of a sitemap or sitemap index (regex, no XML entities)."""
    urls: list[tuple[str, str | None]] = []
    for block in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = re.search(r"<loc>\s*([^<\s]+)\s*</loc>", block)
        if loc:
            mod = re.search(r"<lastmod>\s*([^<\s]+)\s*</lastmod>", block)
            urls.append((loc.group(1).replace("&amp;", "&"), mod.group(1) if mod else None))
    children = [m.replace("&amp;", "&") for m in
                re.findall(r"<sitemap>\s*<loc>\s*([^<\s]+)\s*</loc>", xml, re.S)]
    return urls, children


def lastmod_day(lastmod: str | None) -> date | None:
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", lastmod or "")
    return date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def in_window(day: date | None, since: date | None, until: date | None) -> bool:
    """A missing date is kept (decided by the parser), never excluded on a guess."""
    if day is None:
        return True
    return (since is None or day >= since) and (until is None or day <= until)


# =========================================================================== records
class Evidence:
    """One source reference of a record: the fields it attests, each with its own quotation."""

    def __init__(self, ref: str, *, source_class: str, page: int = 1, excerpt: str | None = None,
                 url: str | None = None, publisher: str | None = None, title: str | None = None,
                 published_at: date | None = None) -> None:
        self.ref = ref
        self.source_class = source_class
        self.page = page
        self.excerpt = excerpt
        self.url = url
        self.publisher = publisher
        self.title = title
        self.published_at = published_at
        self.values: dict[str, tuple[Any, str]] = {}

    def put(self, name: str, value: Any, quotation: str) -> Any:
        """Attest one field. A None value is simply not published: nothing is recorded."""
        if value is None or value == "" or value == []:
            return None
        self.values[name] = (value, quote(quotation))
        return value

    def source_ref(self, document_id: str, source_id: str) -> dict:
        ref: dict[str, Any] = {
            "ref": self.ref, "document_id": document_id, "source_id": source_id, "page": self.page,
            "source_class": self.source_class, "fields": list(self.values),
            "field_excerpts": {k: q for k, (_, q) in self.values.items()},
        }
        if self.excerpt:
            ref["excerpt"] = quote(self.excerpt)
        for key in ("url", "publisher", "title", "published_at"):
            if getattr(self, key) is not None:
                ref[key] = getattr(self, key)
        return ref


def assemble(evidences: list[Evidence], *, document_id: str, source_id: str, ingestion_key: str,
             participants: list[dict] | None = None, flags: list[dict] | None = None) -> dict:
    """An import record from the evidences. Two sources giving two values for one field -> error."""
    rec: dict[str, Any] = {}
    for ev in evidences:
        for name, (value, _) in ev.values.items():
            if name in rec and rec[name] != value:
                raise ValueError(f"contradiction on {name}: {rec[name]!r} vs {value!r}")
            rec[name] = value
    rec["ingestion_key"] = ingestion_key
    rec["sources"] = [ev.source_ref(document_id, source_id) for ev in evidences]
    rec["participants"] = participants or []
    if flags:
        rec["validation_flags"] = flags
    return rec


# =========================================================================== collector
@dataclass
class Candidate:
    url: str
    lastmod: str | None = None
    hint: dict[str, Any] = field(default_factory=dict)  # metadata of the listing (never a value by itself)


@dataclass
class DocumentToRegister:
    url: str
    content: bytes
    title: str
    file_format: str  # pdf | html | json
    document_type: str = "web_page"
    period_year: int | None = None
    original_filename: str | None = None


@dataclass
class Reading:
    """What a parser made of one page: an outcome, or a builder of import records."""

    outcome: str | None = None
    detail: str | None = None
    document: DocumentToRegister | None = None
    build: Callable[[str, str], list[dict]] | None = None  # (document_id, source_id) -> records
    flags: list[str] = field(default_factory=list)  # parser notes (reported, never a value)

    @classmethod
    def skip(cls, outcome: str, detail: str | None = None, flags: list[str] | None = None) -> Reading:
        return cls(outcome=outcome, detail=detail, flags=flags or [])


@dataclass
class CollectionReport:
    source_key: str
    since: date | None
    until: date | None
    candidates: int = 0
    skipped_unchanged: int = 0
    deferred: int = 0  # beyond the per-run limit: read on a next run
    outcomes: dict[str, tuple[str, str | None]] = field(default_factory=dict)
    deals_created: int = 0
    deals_enriched: int = 0
    fields_enriched: int = 0
    deal_ids: list[str] = field(default_factory=list)
    already_imported: int = 0
    duplicate_candidates: int = 0
    documents_registered: int = 0
    validation_flags: Counter = field(default_factory=Counter)
    parser_flags: list[tuple[str, str]] = field(default_factory=list)
    # Partial discovery failures (an index page, one feed of three): the run goes on, but they are
    # reported in the run errors, never silent (audit 22/10/2026, M3).
    discovery_warnings: list[str] = field(default_factory=list)

    def set(self, url: str, outcome: str, detail: str | None = None) -> None:
        self.outcomes[url] = (outcome, detail)

    def count(self, outcome: str) -> int:
        return sum(1 for o, _ in self.outcomes.values() if o == outcome)

    def summary(self) -> dict:
        return {
            "source": self.source_key,
            "since": self.since.isoformat() if self.since else None,
            "until": self.until.isoformat() if self.until else None,
            "candidates": self.candidates,
            "skipped_unchanged": self.skipped_unchanged,
            "deferred": self.deferred,
            "outcomes": dict(sorted(Counter(o for o, _ in self.outcomes.values()).items())),
            "discovery_warnings": list(self.discovery_warnings),
            "deals_created": self.deals_created,
            "deals_enriched": self.deals_enriched,
            "fields_enriched": self.fields_enriched,
            "already_imported": self.already_imported,
            "duplicate_candidates": self.duplicate_candidates,
            "documents_registered": self.documents_registered,
            "validation_flags": dict(sorted(self.validation_flags.items())),
            "parser_flags": dict(sorted(Counter(f for _, f in self.parser_flags).items())),
        }


class DealCollector(ABC):
    """Template of a source collector; subclasses only discover and parse."""

    source_key: ClassVar[str]
    source_short_name: ClassVar[str]  # sources.short_name
    actor: ClassVar[str]
    # Bumped when parsing or safe backfill behavior changes: earlier checkpoints are replayed once,
    # allowing older needs_review deals to receive newly extractable NULL fields.
    parser_version: ClassVar[int] = 3

    def __init__(self, fetcher: Fetcher, registrar: DocumentRegistrar | None = None) -> None:
        self.fetcher = fetcher
        self.registrar = registrar or DocumentRegistrar()
        self.discovery_warnings: list[str] = []  # filled by discover(), copied to the report

    @abstractmethod
    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        """Candidate pages, oldest first (the first page naming a deal sets its announcement)."""

    @abstractmethod
    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        """Pure parsing of one fetched page."""

    async def fetch(self, candidate: Candidate) -> FetchResult:
        return await self.fetcher.get(candidate.url)

    async def run(self, db: AsyncSession, *, since: date | None = None, until: date | None = None,
                  limit: int | None = None, recheck: bool = False,
                  on_progress: Callable[[CollectionReport], Awaitable[None]] | None = None) -> CollectionReport:
        """``recheck``: read every candidate again, whatever its checkpoint (after a parser fix)."""
        report = CollectionReport(self.source_key, since, until)
        source = (await db.execute(
            select(Source).where(Source.short_name == self.source_short_name, Source.deleted_at.is_(None))
        )).scalars().first()
        if source is None:
            raise RuntimeError(f"source '{self.source_short_name}' is not registered (run the migrations)")
        source_id = source.id
        checkpoints = {
            c.url: c for c in (await db.execute(
                select(DealCollectionCheckpoint).where(DealCollectionCheckpoint.source_key == self.source_key)
            )).scalars()
        }
        seen = {url: (c.lastmod, c.outcome, c.parser_version) for url, c in checkpoints.items()}
        await db.commit()  # no transaction kept open during the HTTP requests

        self.discovery_warnings = []
        candidates = await self.discover(since, until)
        report.discovery_warnings = list(self.discovery_warnings)
        report.candidates = len(candidates)
        processed = 0
        for c in candidates:
            previous = seen.get(c.url)
            if (not recheck and previous is not None and previous[1] in FINAL_OUTCOMES
                    and previous[0] == stored_lastmod(c.lastmod) and previous[2] == self.parser_version):
                report.skipped_unchanged += 1
                continue
            if limit is not None and processed >= limit:
                report.deferred += 1
                continue
            processed += 1
            try:
                outcome, detail = await self._one(db, c, source_id, report)
            except Exception as err:  # one page never stops the run; the failure is reported
                await db.rollback()
                logger.warning("deal_collection_page_failed", source=self.source_key, url=c.url, error=str(err))
                outcome, detail = "error", f"{type(err).__name__}: {str(err)[:300]}"
            report.set(c.url, outcome, detail)
            await self._checkpoint(db, c, outcome, detail)
            if on_progress:
                try:
                    await on_progress(report)
                except Exception as err:
                    logger.warning("deal_collection_progress_update_failed", source=self.source_key, error=str(err))
                    await db.rollback()
        return report

    async def _checkpoint(self, db: AsyncSession, c: Candidate, outcome: str, detail: str | None) -> None:
        try:
            row = (await db.execute(select(DealCollectionCheckpoint).where(
                DealCollectionCheckpoint.source_key == self.source_key, DealCollectionCheckpoint.url == c.url,
            ))).scalar_one_or_none()
            if row is None:
                row = DealCollectionCheckpoint(source_key=self.source_key, url=c.url)
                db.add(row)
            row.lastmod, row.outcome, row.detail, row.checked_at = stored_lastmod(c.lastmod), outcome, (detail or None), utcnow()
            row.parser_version = self.parser_version
            await db.commit()
        except Exception as err:  # a checkpoint failure only means the page is read again next time
            await db.rollback()
            logger.warning("deal_collection_checkpoint_failed", source=self.source_key, url=c.url, error=str(err))

    async def _one(self, db: AsyncSession, c: Candidate, source_id: str,
                   report: CollectionReport) -> tuple[str, str | None]:
        res = await self.fetch(c)
        if is_restricted(res):
            return "restricted", res.error or f"HTTP {res.status_code} -> {res.final_url}"
        if not res.ok:
            return "fetch_failed", res.error
        reading = self.read(c, res)
        report.parser_flags.extend((c.url, f) for f in reading.flags)
        if reading.build is None or reading.document is None:
            return reading.outcome or "not_a_deal", reading.detail
        try:
            draft = reading.build(PLACEHOLDER, source_id)
        except ValueError as err:
            return "refused", str(err)[:300]
        if not draft:
            return "not_a_deal", reading.detail
        keys = [r["ingestion_key"] for r in draft]
        existing_rows = (await db.execute(
            select(Deal).where(Deal.ingestion_key.in_(keys), Deal.deleted_at.is_(None))
        )).scalars().all()
        existing_by_key = {row.ingestion_key: row for row in existing_rows}
        existing = set(existing_by_key)
        report.already_imported += len(existing)

        source = await db.get(Source, source_id)
        doc = reading.document
        registered = await self.registrar.register_pdf(
            db, source=source, url=doc.url, content=doc.content, title=doc.title, document_type=doc.document_type,
            period_year=doc.period_year, period_type=None, document_scope="market",
            original_filename=doc.original_filename,
        )
        registered.document.file_format = doc.file_format
        if doc.file_format == "pdf":
            registered.document.text_layer_status = "machine_readable"
        records = validate_records(reading.build(registered.document.id, source_id))
        existing_records = [
            (existing_by_key[r.ingestion_key], r) for r in records if r.ingestion_key in existing_by_key
        ]
        new_records = [r for r in records if r.ingestion_key not in existing_by_key]
        try:
            enriched_deals, enriched_fields = await enrich_existing_deals(db, existing_records, actor=self.actor)
            if new_records:
                imported = await import_deals(db, new_records, actor=self.actor,
                                              origin=f"{self.source_short_name} {c.url}")
            else:
                imported = None
                await db.commit()
        except DealImportError as err:
            await db.rollback()
            return "import_refused", "; ".join(f"{i.field}:{i.code}" for i in err.issues)[:500]
        report.deals_enriched += enriched_deals
        report.fields_enriched += enriched_fields
        report.documents_registered += int(registered.is_new)
        if imported is not None:
            report.deals_created += len(imported.created_ids)
            report.deal_ids.extend(imported.created_ids)
            report.duplicate_candidates += len(imported.duplicate_candidates)
        for r in new_records:
            for flag in r.validation_flags:
                report.validation_flags[flag.code] += 1
        if (imported and imported.created_ids) or enriched_deals:
            return "produced", f"{len(imported.created_ids) if imported else 0} created; {enriched_deals} enriched"
        return "already_imported", f"{len(existing)} deal(s)"
