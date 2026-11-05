"""BIDC official financing announcements -> DFI deal records.

Discovery reads the bank's French official news archive. An article with an explicit list of
approved/signature operations produces one deal per listed operation; an article-level aggregate is
never copied onto each project. Only explicit amounts, currencies, countries, counterparties, dates,
sectors and objectives are recorded, with the official HTML page as field provenance.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import re
from datetime import date
from urllib.parse import urljoin, urlparse

from scraping.deals.collect.amounts import Money, fold, parse_day, parse_money
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
    in_window,
)
from scraping.deals.umoa_titres_auctions import norm
from scraping.universe.http import FetchResult

BASE_URL = "https://www.bidc-ebid.org"
NEWS_URL = BASE_URL + "/fr/category/actualites/"
PUBLISHER = "Banque d'Investissement et de Développement de la CEDEAO (BIDC)"
MAX_ARCHIVE_PAGES = 24
UMOA_COUNTRY_CODES = frozenset({"BJ", "BF", "CI", "GW", "ML", "NE", "SN", "TG"})

ARTICLE_RE = re.compile(r"<article\b[^>]*>.*?</article>", re.IGNORECASE | re.DOTALL)
HREF_RE = re.compile(r"<a\b[^>]*href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
DATE_RE = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")
FINANCING_RE = re.compile(
    r"facilit[eé]|ligne de cr[eé]dit|cr[eé]dit|pr[eê]t|financement|financ(?:e|ing)|loan|"
    r"approved operation|op[eé]ration approuv[eé]e|investment|investissement|obligat|bond|garantie|equity",
    re.IGNORECASE,
)
OPERATION_RE = re.compile(
    r"facilit[eé]|ligne de cr[eé]dit|cr[eé]dit|pr[eê]t|financement|financ(?:e|ing)|loan|"
    r"investissement|investment|obligat|bond|garantie|equity|capital",
    re.IGNORECASE,
)
MONEY_CUE_RE = re.compile(r"\d[\d\s .,]*\s*(?:millions?|milliards?|mds?|M)?\s*(?:USD|US\$|EUR|€|FCFA|F\s*CFA|XOF)", re.I)

# ECOWAS member countries, written explicitly in BIDC announcements. Full-word matching keeps
# Nigeria distinct from Niger and Guinea distinct from Guinea-Bissau.
COUNTRIES = (
    ("GUINEE BISSAU", "GW"), ("GUINEA BISSAU", "GW"),
    ("COTE D IVOIRE", "CI"), ("IVORY COAST", "CI"), ("CAPE VERDE", "CV"), ("CAP VERT", "CV"),
    ("BURKINA FASO", "BF"), ("SIERRA LEONE", "SL"), ("NIGERIA", "NG"), ("LIBERIA", "LR"),
    ("GAMBIA", "GM"), ("GAMBIE", "GM"), ("GHANA", "GH"), ("GUINEA", "GN"), ("GUINEE", "GN"),
    ("SENEGAL", "SN"), ("BENIN", "BJ"), ("MALI", "ML"), ("NIGER", "NE"),
    ("TOGO", "TG"),
)

SECTORS = (
    (re.compile(r"agricultur|agriculture|agricole", re.I), "agriculture"),
    (re.compile(r"climat|climate|r[eé]silien", re.I), "climate"),
    (re.compile(r"[ée]nergie|energy|p[eé]trol|electricit[eé]", re.I), "energy"),
    (re.compile(r"manufactur|industrie|industrial", re.I), "industry"),
    (re.compile(r"t[eé]l[eé]com|num[eé]rique|digital", re.I), "telecom_media_tech"),
    (re.compile(r"transport|chemin de fer|railway|route|port\b", re.I), "infrastructure_public"),
    (re.compile(r"banque|financial institution|microfinance|assurance", re.I), "financial_services"),
    (re.compile(r"sant[eé]|health|[ée]ducation|education", re.I), "health_education"),
)


def clean(fragment: str) -> str:
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", fragment or "", flags=re.I | re.S)
    text = re.sub(r"</(?:p|li|h[1-6]|div|section|br|tr)>|<br\s*/?>", "\n", text, flags=re.I)
    text = html_lib.unescape(re.sub(r"<[^>]+>", " ", text))
    return " ".join(text.replace("\xa0", " ").split())


def country_codes(text: str) -> list[str]:
    normalized = f" {norm(text)} "
    found: list[tuple[int, str]] = []
    occupied: list[tuple[int, int]] = []
    for name, code in sorted(COUNTRIES, key=lambda item: len(item[0]), reverse=True):
        for m in re.finditer(rf"(?<![A-Z0-9]){re.escape(name)}(?![A-Z0-9])", normalized):
            if any(m.start() < end and m.end() > start for start, end in occupied):
                continue
            found.append((m.start(), code))
            occupied.append((m.start(), m.end()))
    out: list[str] = []
    for _, code in sorted(found):
        if code not in out:
            out.append(code)
    return out


def canonical_article_url(href: str) -> str | None:
    url = urljoin(BASE_URL, html_lib.unescape(href)).split("#", 1)[0]
    parsed = urlparse(url)
    if parsed.netloc.lower() not in {"www.bidc-ebid.org", "bidc-ebid.org"}:
        return None
    if not parsed.path.startswith("/fr/") or any(
        part in parsed.path for part in ("/category/", "/page/", "/projects-operations/", "/wp-content/")
    ):
        return None
    if parsed.path.rstrip("/") == "/fr":
        return None
    return f"{BASE_URL}{parsed.path.rstrip('/')}/"


def archive_items(page_html: str) -> list[dict]:
    blocks = ARTICLE_RE.findall(page_html)
    if not blocks:
        # WordPress themes sometimes use cards without <article>; still restrict the links to French
        # article URLs and use a small surrounding snippet for their dates.
        blocks = []
        for m in HREF_RE.finditer(page_html):
            if canonical_article_url(m.group(1)):
                blocks.append(page_html[max(0, m.start() - 450):m.end() + 450])
    out: dict[str, dict] = {}
    for block in blocks:
        page_text = clean(block)
        day_match = DATE_RE.search(page_text)
        published = parse_day(day_match.group(1)) if day_match else None
        for href, link_text in HREF_RE.findall(block):
            url = canonical_article_url(href)
            if not url:
                continue
            title = clean(link_text)
            if title and url not in out:
                out[url] = {"url": url, "title": title, "published": published, "summary": page_text[:1000]}
    return list(out.values())


def article_fragment(page_html: str) -> str:
    match = ARTICLE_RE.search(page_html)
    if match:
        return match.group(0)
    match = re.search(
        r"<(?:div|section)[^>]+class=[\"'][^\"']*(?:entry-content|post-content|article-content)[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
        page_html, re.I | re.S,
    )
    return match.group(1) if match else page_html


def article_title(page_html: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", page_html, re.I | re.S)
    return clean(match.group(1)) if match else ""


def article_day(page_html: str, fallback: date | None) -> date | None:
    for raw in (
        (m.group(1) if (m := re.search(r"<meta[^>]+(?:property|name)=[\"']article:published_time[\"'][^>]+content=[\"']([^\"']+)", page_html, re.I)) else None),
        (m.group(1) if (m := re.search(r"<time[^>]+datetime=[\"']([^\"']+)", page_html, re.I)) else None),
    ):
        if raw and (day := parse_day(raw)):
            return day
    return fallback


def list_lines(fragment: str, tag: str) -> list[str]:
    return [clean(value) for value in re.findall(rf"<{tag}\b[^>]*>(.*?)</{tag}\s*>", fragment, re.I | re.S)
            if clean(value)]


def operation_type(text: str) -> tuple[str | None, str | None, str | None]:
    value = fold(text)
    if re.search(r"garantie|guarantee", value):
        return "guarantee", "guarantor", "guarantee"
    if re.search(r"ligne de credit|facilite de credit|credit renouvelable|credit line|revolving credit", value):
        return "credit_line", "lender", "credit_line"
    if re.search(r"pret|loan", value):
        return "term_loan", "lender", None
    if re.search(r"prise de participation|equity|capital investissement", value):
        return "equity", "investor", None
    if re.search(r"obligation|bond|sukuk", value):
        return "bond", "lender", "bond"
    return None, None, None


def counterparty(text: str) -> str | None:
    patterns = (
        r"\ben faveur de\s+(?:la\s+|le\s+|l['’])?(?P<name>[A-ZÀ-Ý0-9][^,.;]+)",
        r"\bavec\s+(?P<name>[A-ZÀ-Ý0-9][^,.;]+?)(?=\s+(?:afin|pour|en vue|dans|en|to|for)\b|[,.;]|$)",
    )
    for pattern in patterns:
        if match := re.search(pattern, text, re.I):
            name = re.split(r"\s+(?:destin[ée]e?|visant|afin|pour|to)\b", match.group("name"), maxsplit=1,
                            flags=re.I)[0].strip(" ,.;:")
            if name and len(name) > 1:
                return name[:255]
    return None


def signing_day(text: str) -> date | None:
    match = re.search(
        r"(?:sign[ée]|signature|conclu(?:e)?)\s+(?:le\s+)?(\d{1,2}(?:er)?\s+[A-Za-zÀ-ÿ]+\s+\d{4}|\d{2}/\d{2}/\d{4})",
        text, re.I,
    )
    return parse_day(match.group(1)) if match else None


def sector_for(text: str) -> str | None:
    found = {sector for pattern, sector in SECTORS if pattern.search(text)}
    return next(iter(found)) if len(found) == 1 else None


def objective(text: str) -> str | None:
    match = re.search(r"(?:destin[ée]e? à|afin de|en vue de)\s+(.+?)(?:[.;]|$)", text, re.I)
    return match.group(1).strip(" ,.;")[:1000] if match else None


def operation_rows(fragment: str, title: str) -> list[str]:
    bullets = list_lines(fragment, "li")
    explicit = [line for line in bullets if MONEY_CUE_RE.search(line) and OPERATION_RE.search(line)]
    if explicit:
        return explicit
    # A single financing announced in the heading is safe to read from the heading itself.
    if MONEY_CUE_RE.search(title) and FINANCING_RE.search(title):
        return [title]
    for paragraph in list_lines(fragment, "p"):
        if MONEY_CUE_RE.search(paragraph) and OPERATION_RE.search(paragraph):
            return [paragraph]
    return []


class BidcCollector(DealCollector):
    source_key = "bidc"
    parser_version = 1
    source_short_name = "BIDC"
    actor = "bidc_official_news_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        out: dict[str, Candidate] = {}
        for page in range(1, MAX_ARCHIVE_PAGES + 1):
            url = NEWS_URL if page == 1 else f"{NEWS_URL}page/{page}/"
            res = await self.fetcher.get(url)
            if not res.ok:
                if page == 1:
                    raise RuntimeError(f"BIDC news archive unavailable: {res.error}")
                self.discovery_warnings.append(f"BIDC news archive page {page} unavailable: {res.error}")
                break
            items = archive_items(res.text)
            if page == 1 and not items:
                raise RuntimeError("BIDC news archive: no article cards found (layout changed?)")
            page_days = [it["published"] for it in items if it["published"]]
            if since and page_days and max(page_days) < since:
                break
            for item in items:
                published = item["published"]
                if not in_window(published, since, until):
                    continue
                if not FINANCING_RE.search(item["title"]):
                    continue
                out.setdefault(item["url"], Candidate(
                    url=item["url"], lastmod=published.isoformat() if published else None,
                    hint={"title": item["title"], "published": published.isoformat() if published else None},
                ))
        return sorted(out.values(), key=lambda c: (c.lastmod or "", c.url))

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_announcement(candidate.url, res.content or b"", candidate.hint.get("published"))


def read_announcement(url: str, content: bytes, fallback_day: str | None = None) -> Reading:
    page_html = content.decode("utf-8", errors="replace")
    fragment = article_fragment(page_html)
    title = article_title(page_html)
    if not title and (match := re.search(r"<title[^>]*>(.*?)</title>", page_html, re.I | re.S)):
        title = clean(match.group(1))
    if not title or not FINANCING_RE.search(title):
        return Reading.skip("not_a_deal", "not an explicit financing announcement")
    published = article_day(page_html, parse_day(fallback_day or ""))
    rows = operation_rows(fragment, title)
    if not rows:
        return Reading.skip("not_a_deal", "no explicit operation amount found in the official announcement")
    published_text = published.isoformat() if published else fallback_day
    operations: list[dict] = []
    for row in rows:
        money = parse_money(row, allow_cfa=True)
        if money is None:
            continue
        codes = country_codes(row)
        # A single country can be stored directly. Multi-country facilities remain unassigned rather
        # than being attributed to an arbitrary member state.
        country = codes[0] if len(codes) == 1 and codes[0] in UMOA_COUNTRY_CODES else None
        borrower = counterparty(row)
        deal_type, bidc_role, debt_type = operation_type(row)
        sector = sector_for(row)
        operation_title = f"BIDC — {row[:220]}"
        fingerprint = hashlib.sha1(f"{url}|{row}".encode("utf-8")).hexdigest()[:20]
        flags = [{"code": "dfi_own_commitment_only",
                  "detail": "amount = montant explicite de l'opération annoncé par la BIDC; "
                            "aucun coût total de projet n'est déduit"}]
        if len(codes) != 1 or codes[0] not in UMOA_COUNTRY_CODES:
            flags.append({
                "code": "bidc_country_not_in_umoa_reference",
                "detail": f"pays publié : {', '.join(codes) if codes else 'non déterminé'}; le référentiel pays "
                          "de la plateforme ne contient que les huit pays de l'UMOA, donc aucun pays n'est attribué",
            })
        operations.append({
            "row": row, "money": money, "country": country, "borrower": borrower,
            "deal_type": deal_type, "bidc_role": bidc_role, "debt_type": debt_type, "sector": sector,
            "title": operation_title[:500], "key": f"bidc:announcement:{fingerprint}", "flags": flags,
        })
    if not operations:
        return Reading.skip("not_a_deal", "the announcement has no unambiguous amount and currency")
    signed = signing_day(clean(fragment))

    def build(document_id: str, source_id: str) -> list[dict]:
        records: list[dict] = []
        for op in operations:
            row = op["row"]
            money: Money = op["money"]
            ev = Evidence("bidc_announcement", source_class="dfi_official", url=url, publisher=PUBLISHER,
                          title=title, published_at=published,
                          excerpt=f"web_html · annonce officielle BIDC {url} · {row[:500]}")
            ev.put("title", op["title"], f"annonce BIDC : « {row} »")
            ev.put("project_name", row[:500], f"opération publiée : « {row} »")
            ev.put("deal_type", op["deal_type"], f"nature de l'opération : « {row} »")
            ev.put("debt_type", op["debt_type"], f"instrument publié : « {row} »")
            ev.put("country_code", op["country"], f"pays explicitement cité : « {row} »")
            ev.put("sector", op["sector"], f"secteur explicitement cité : « {row} »")
            ev.put("amount", money.figure, f"montant : « {money.original} »")
            ev.put("amount_original", money.original, f"montant : « {money.original} »")
            ev.put("currency", money.currency, f"devise : « {money.original} »")
            ev.put("unit", money.unit, f"unité publiée : « {money.original} »")
            ev.put("announcement_date", published, f"date de publication BIDC : {published_text or 'non publiée'}")
            ev.put("signing_date", signed, f"date de signature publiée : « {clean(fragment)[:1200]} »")
            ev.put("use_of_proceeds", objective(row), f"objectif publié : « {row} »")
            participants = []
            if op["bidc_role"]:
                participants.append({
                    "role": op["bidc_role"], "name": PUBLISHER, "source_ref": ev.ref,
                    "excerpt": f"opération de financement publiée par la BIDC : « {row} »",
                    "extraction_method": "text",
                    "commitment_amount": money.amount, "commitment_currency": money.currency,
                })
            if op["borrower"]:
                participants.append({
                    "role": "borrower", "name": op["borrower"], "source_ref": ev.ref,
                    "excerpt": f"contrepartie nommée dans l'annonce : « {row} »", "extraction_method": "text",
                })
            records.append(assemble([ev], document_id=document_id, source_id=source_id,
                                    ingestion_key=op["key"], participants=participants,
                                    flags=op["flags"]))
        return records

    document = DocumentToRegister(
        url=url, content=content, title=f"BIDC — {title}"[:500], file_format="html",
        period_year=published.year if published else None, original_filename="bidc_announcement.html",
    )
    return Reading(document=document, build=build)
