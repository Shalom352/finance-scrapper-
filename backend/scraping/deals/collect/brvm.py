"""
BRVM — first listings of bonds announced in the Bulletin Officiel de la Cote (BOC) -> deals.

The BRVM does not publish its bond listing notices systematically (/fr/avis is empty; only a few
"avis" PDFs appear among the issuers' releases). The daily BOC is the regular primary source: its
"OPERATIONS EN COURS" table names, for each upcoming first listing, the issuer ("Emetteur") and the
operation, e.g.

    SWAMI AGRI SAU
    Première cotation - GREEN BOND SWAMI AGRI 7,00 % 2026-2031 (SWAS.O1) - Première cotation le 17 novembre 2026

Read from it: the bond label, its BRVM symbol, the coupon printed in the label, the issuer and the
bulletin date (announcement). Not published there, hence left NULL: amount, ISIN, arranger, maturity
date, deal type (flag ``listing_notice_only``). Bond symbols end with ``.O<n>``; share listings are
ignored. The BRVM robots.txt asks for a 10 s crawl delay: honoured by the PoliteFetcher.
"""
from __future__ import annotations

import re
from datetime import date

import pymupdf

from scraping.deals.collect.amounts import parse_day, parse_rate
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
    in_window,
)
from scraping.universe.http import FetchResult

INDEX_URL = "https://www.brvm.org/fr/bulletins-officiels-de-la-cote"
BOC_RE = re.compile(r"https://www\.brvm\.org/sites/default/files/boc_(?P<d>\d{8})_\d+\.pdf")
MAX_INDEX_PAGES = 15
PUBLISHER = "BRVM"
OPERATION_START = "Première cotation -"
LISTING_RE = re.compile(
    r"^Première cotation - (?P<label>.+?) \((?P<symbol>[A-Z0-9]+\.O\d+)\)\s*-\s*"
    r"Première cotation le (?P<when>\d{1,2}(?:er)? \S+ \d{4})"
)
OPERATION_END_RE = re.compile(r"Première cotation le \d{1,2}(?:er)? \S+ \d{4}")
DAY_LINE_RE = re.compile(r"^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche) \d{1,2} \S+ \d{4}$", re.I)


def boc_day(url: str) -> date | None:
    m = BOC_RE.search(url)
    if not m:
        return None
    d = m.group("d")
    try:
        return date(int(d[:4]), int(d[4:6]), int(d[6:]))
    except ValueError:
        return None


def operations_section(lines: list[str]) -> list[str] | None:
    """Lines of the 'OPERATIONS EN COURS' table (header excluded), up to the 'AVIS' table."""
    try:
        start = lines.index("OPERATIONS EN COURS")
    except ValueError:
        return None
    out: list[str] = []
    for line in lines[start + 1:]:
        if line in ("AVIS", "COMMUNIQUES"):
            break
        if line in ("Emetteur", "Opération"):
            continue
        out.append(line)
    return out


def first_listings(section: list[str]) -> list[dict]:
    """[{issuer, label, symbol, listing_text, quotation}] of the bond first listings of the section.

    An operation may wrap over several lines; the issuer is the line just before it."""
    found: list[dict] = []
    i = 0
    while i < len(section):
        line = section[i]
        if line.startswith(OPERATION_START):
            # An operation may wrap; it ends with its own "Première cotation le <date>". It never
            # absorbs the next operation (a share listing must not lend its issuer to a bond).
            text, j = line, i + 1
            while not OPERATION_END_RE.search(text) and j < len(section) and j <= i + 3                     and not section[j].startswith(OPERATION_START):
                text = f"{text} {section[j]}"
                j += 1
            m = LISTING_RE.match(text)
            issuer = section[i - 1] if i > 0 and not section[i - 1].startswith(OPERATION_START) else None
            if m and issuer:
                found.append({"issuer": issuer, "label": " ".join(m.group("label").split()),
                              "symbol": m.group("symbol"), "listing_text": m.group("when"),
                              "quotation": f"{issuer} · {m.group(0)}"})
            i = j
            continue
        i += 1
    return found


class BrvmBondListingCollector(DealCollector):
    source_key = "brvm"
    source_short_name = "BRVM"
    actor = "brvm_boc_listing_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        out: dict[str, Candidate] = {}
        for page in range(MAX_INDEX_PAGES):
            res = await self.fetcher.get(INDEX_URL if page == 0 else f"{INDEX_URL}?page={page}")
            if not res.ok:
                if page == 0:
                    raise RuntimeError(f"BRVM BOC index unavailable: {res.error}")
                if res.status_code != 404:  # 404 = past the last index page; anything else is a failure
                    self.discovery_warnings.append(f"BOC index page {page} unavailable ({res.error or res.status_code}):"
                                                   " older bulletins not listed this run")
                break
            urls = [m.group(0) for m in BOC_RE.finditer(res.text)]
            if not urls:
                break
            days = [boc_day(u) for u in urls]
            for u, d in zip(urls, days, strict=True):
                if in_window(d, since, until):
                    out.setdefault(u, Candidate(url=u, lastmod=None, hint={"day": d.isoformat() if d else None}))
            dated = [d for d in days if d is not None]
            if since is None or (dated and min(dated) < since):
                break  # without a window only the first index page is read
        else:
            self.discovery_warnings.append(
                f"BRVM BOC index reached its {MAX_INDEX_PAGES}-page scan limit; older bulletins may be missing"
            )
        return sorted(out.values(), key=lambda c: c.hint.get("day") or "")

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_boc(candidate.url, res.content or b"")


def read_boc(url: str, content: bytes) -> Reading:
    if content[:5] != b"%PDF-":
        return Reading.skip("not_a_deal", "not a PDF")
    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            pages = [p.get_text() for p in pdf]
    except Exception as err:
        return Reading.skip("refused", f"unreadable PDF: {err}")
    page_no, listings, bulletin_day, day_line = None, [], None, None
    for n, text in enumerate(pages, start=1):
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        section = operations_section(lines)
        if section is None:
            continue
        page_no = n
        listings = first_listings(section)
        day_line = next((ln for ln in reversed(lines) if DAY_LINE_RE.match(ln)), None)
        bulletin_day = parse_day(day_line) if day_line else None
        break
    if page_no is None:
        return Reading.skip("not_a_deal", "no 'OPERATIONS EN COURS' table", flags=["boc_operations_table_missing"])
    if not listings:
        return Reading.skip("not_a_deal", "no bond first listing announced")
    file_day = boc_day(url)
    if bulletin_day and file_day and bulletin_day != file_day:
        return Reading.skip("refused", f"bulletin date {bulletin_day} differs from file name date {file_day}")
    day = bulletin_day or file_day

    def build(document_id: str, source_id: str) -> list[dict]:
        records = []
        for it in listings:
            ev = Evidence("boc", source_class="primary_market", page=page_no, url=url, publisher=PUBLISHER,
                          title=f"Bulletin Officiel de la Cote du {day.strftime('%d/%m/%Y') if day else '?'}",
                          published_at=day,
                          excerpt=f"pdf_text · BOC {url} p.{page_no} · OPERATIONS EN COURS · {it['quotation']}")
            ev.put("title", f"{it['label']} ({it['symbol']})", it["quotation"])
            ev.put("interest_rate", parse_rate(it["label"]), it["quotation"])
            ev.put("announcement_date", day, f"date du bulletin : {day_line}" if day_line
                   else f"date du fichier : {url.rsplit('/', 1)[-1]}")
            participants = [{"role": "issuer", "name": it["issuer"][:255], "source_ref": ev.ref, "page": page_no,
                             "excerpt": f"Emetteur : {it['issuer']}", "extraction_method": "text"}]
            records.append(assemble(
                [ev], document_id=document_id, source_id=source_id,
                ingestion_key=f"brvm:first_listing:{it['symbol']}", participants=participants,
                flags=[{"code": "listing_notice_only",
                        "detail": f"BOC first-listing line (listing on {it['listing_text']}): amount, ISIN, "
                                  f"arranger and maturity date are not published there"}],
            ))
        return records

    document = DocumentToRegister(url=url, content=content, file_format="pdf", document_type="regulatory_report",
                                  title=f"BRVM — Bulletin Officiel de la Cote — {day}"[:500],
                                  period_year=day.year if day else None, original_filename=url.rsplit("/", 1)[-1])
    return Reading(document=document, build=build)
