"""
BOAD (Banque Ouest Africaine de Développement) — approved projects -> deals.

Source: https://www.boad.org/fr/nos-publications/nos-projets-approuves (Laravel / Inertia: each page
carries its data as JSON in the ``data-page`` attribute; the list is paginated, 30 per page).

Only what the project page DISPLAYS in its header is read: title, approval date (``acf.date``),
countries, intervention domain, and the amount label (e.g. "10 Mds FCFA"). The amount is BOAD's
own approved financing: the deal is BOAD's financing operation (flag ``dfi_own_commitment_only``).

Fields of the CMS that the page does not display reliably are ignored on purpose: on 21/10/2026
the list data of several projects carried placeholder content ("Laravel has wonderful
documentation...", impacts "TEST", a beneficiary and a financing split unrelated to the title).
The "graph" financing split is therefore never read, even when present.
"""
from __future__ import annotations

import hashlib
import html as html_lib
import json
import re
from datetime import date
from typing import Any

from scraping.deals.collect.amounts import fold, parse_day, parse_money, umoa_countries
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
)
from scraping.universe.http import FetchResult

BASE_URL = "https://www.boad.org"
LIST_URL = BASE_URL + "/fr/nos-publications/nos-projets-approuves"
PROJECT_PREFIX = "/fr/nos-publications/nos-projets-approuves/"
PUBLISHER = "BOAD"
MAX_LIST_PAGES = 20

# Intervention domains as published by BOAD -> closed sector list. Unlisted -> NULL (never guessed).
DOMAIN_SECTORS = {
    "agriculture et securite alimentaire": "agriculture",
    "developpement rural et securite alimentaire": "agriculture",
    "energie": "energy",
    "energie et ressources naturelles": "energy",
    "environnement et finance climat": "climate",
    "environnement et finance climatique": "climate",
    "sante et education": "health_education",
    "tourisme": "tourism",
    "industrie": "industry",
    "immobilier et habitat social": "real_estate",
    "infrastructures et economies numeriques": "infrastructure_public",
    "economie numerique": "telecom_media_tech",
}
# Explicit words of the title -> (deal_type, BOAD role, debt_type). Checked in this order. Without
# one of them the instrument is not published: BOAD gets no role (never deduced from "approved").
TITLE_NATURE = (
    (re.compile(r"\bprise de participation\b"), "equity", "investor", None),
    (re.compile(r"\bcontre-garantie\b|\bgarantie\b"), "guarantee", "guarantor", "guarantee"),
    (re.compile(r"\bligne[s]? de (?:refinancement|credit)\b"), "credit_line", "lender", "credit_line"),
    (re.compile(r"\bpret\b"), "term_loan", "lender", None),
)
# "... en faveur de X" names the counterpart of a line / facility (the borrower of BOAD).
BENEFICIARY_RE = re.compile(r"\ben faveur de (?:la |le |l['’])?(?P<name>.+?)(?: pour | au | en | dans |$)",
                            re.IGNORECASE)


def data_page(page_html: str) -> dict[str, Any] | None:
    m = re.search(r'data-page="([^"]*)"', page_html)
    if not m:
        return None
    try:
        return json.loads(html_lib.unescape(m.group(1)))
    except ValueError:
        return None


def list_items(page_html: str) -> tuple[list[dict], int | None]:
    """(project items, last page) of a list page; ([], None) when the structure is not found."""
    d = data_page(page_html)
    if not d:
        return [], None
    for block in d.get("props", {}).get("blocks") or []:
        projects = block.get("projects") if isinstance(block, dict) else None
        if isinstance(projects, dict) and isinstance(projects.get("data"), list):
            return projects["data"], projects.get("last_page")
    return [], None


def strip_tags(text: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", text or "")).split())


class BoadCollector(DealCollector):
    source_key = "boad"
    parser_version = 3  # safe backfill for records already imported by earlier parser versions
    source_short_name = "BOAD"
    actor = "boad_project_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        candidates: list[Candidate] = []
        page, last = 1, 1
        while page <= min(last, MAX_LIST_PAGES):
            res = await self.fetcher.get(f"{LIST_URL}?page={page}")
            if not res.ok:
                raise RuntimeError(f"BOAD project list page {page} unavailable: {res.error}")
            items, last_page = list_items(res.text)
            if last_page is None:
                raise RuntimeError("BOAD project list: data structure not found (layout changed?)")
            last = int(last_page)
            for it in items:
                link = it.get("link") or ""
                if not link.startswith(PROJECT_PREFIX):
                    continue
                approved = parse_day((it.get("acf") or {}).get("date") or "")
                if approved is not None and ((since and approved < since) or (until and approved > until)):
                    continue
                # No modification date is published: the listed values stand for it.
                # Include every published list field so country/domain/objective/amount corrections trigger rereads.
                stamp = json.dumps(it, ensure_ascii=False, sort_keys=True, default=str)
                candidates.append(Candidate(url=BASE_URL + link, lastmod=hashlib.sha1(stamp.encode()).hexdigest(),
                                            hint={"approved": approved.isoformat() if approved else None}))
            page += 1
        if last > MAX_LIST_PAGES:
            self.discovery_warnings.append(
                f"BOAD project index has {last} pages; only the first {MAX_LIST_PAGES} were queried"
            )
        candidates.sort(key=lambda c: c.hint.get("approved") or "")
        return candidates

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_project(candidate.url, res.content or b"")


def read_project(url: str, content: bytes) -> Reading:
    page_html = content.decode("utf-8", errors="replace")
    d = data_page(page_html)
    if not d or d.get("component") != "Project":
        return Reading.skip("not_a_deal", "not a BOAD project page")
    props = d.get("props") or {}
    page = props.get("page") or {}
    blocks = props.get("blocks") or []
    header = next((b for b in blocks if isinstance(b, dict) and b.get("acf_fc_layout") == "project_header_block"), {})
    tags = (header.get("data") or {}).get("tags") or {}
    title = strip_tags(page.get("title") or (header.get("data") or {}).get("title") or "")
    if not title:
        return Reading.skip("not_a_deal", "project page without a title")
    flags: list[str] = []
    graph = next((b.get("graph") for b in blocks if isinstance(b, dict) and b.get("graph")), None)
    if graph:
        flags.append("boad_graph_ignored")

    approved = parse_day((page.get("acf") or {}).get("date") or "")
    country_names = [c.get("name", "") for c in tags.get("countries") or [] if isinstance(c, dict)]
    codes = umoa_countries(", ".join(country_names)) if country_names else umoa_countries(title)
    if not codes:
        return Reading.skip("out_of_scope", f"no UMOA country ({', '.join(country_names) or 'none published'})")
    domains = [c.get("name", "") for c in tags.get("domains") or [] if isinstance(c, dict)]
    mapped_domains = {DOMAIN_SECTORS.get(fold(domain)) for domain in domains}
    sector = next(iter(mapped_domains)) if domains and None not in mapped_domains and len(mapped_domains) == 1 else None
    price = (tags.get("price") or "").strip()
    money = parse_money(price, allow_cfa=True) if price else None
    if price and money is None:
        flags.append("boad_amount_not_explicit")
    objective_items = next((b.get("objectives") for b in blocks if isinstance(b, dict) and b.get("objectives")), [])
    objectives = " ".join(strip_tags(o.get("objectif", "")) for o in objective_items if isinstance(o, dict))
    folded = fold(title)
    deal_type, boad_role, debt_type = next(
        ((dt, role, debt) for rx, dt, role, debt in TITLE_NATURE if rx.search(folded)), (None, None, None)
    )
    if boad_role is None:
        flags.append("boad_instrument_not_published")
    beneficiary = None
    if m := BENEFICIARY_RE.search(title):
        beneficiary = m.group("name").strip(" ,.;")

    def build(document_id: str, source_id: str) -> list[dict]:
        ev = Evidence("boad_project", source_class="dfi_official", url=url, publisher=PUBLISHER, title=title,
                      published_at=approved,
                      excerpt=f"web_html · BOAD, projet approuvé {url} · « {title} »"
                              + (f" · {price}" if price else ""))
        ev.put("title", f"BOAD — {title}", f"titre : « {title} »")
        ev.put("project_name", title, f"titre : « {title} »")
        ev.put("deal_type", deal_type, f"titre : « {title} »")
        ev.put("debt_type", debt_type, f"titre : « {title} »")
        if len(codes) == 1:
            ev.put("country_code", codes[0], f"pays : {', '.join(country_names) or title}")
        ev.put("sector", sector, f"domaine d'intervention : {', '.join(domains)}")
        ev.put("announcement_date", approved, f"date : {(page.get('acf') or {}).get('date')}")
        if money is not None:
            ev.put("amount", money.figure, f"montant : {price}")
            ev.put("amount_original", price, f"montant : {price}")
            ev.put("currency", money.currency, f"montant : {price}")
            ev.put("unit", money.unit, f"montant : {price}")
        ev.put("use_of_proceeds", objectives or None, f"objectifs : {objectives}")
        participants = []
        if boad_role is not None:
            participants.append({
                "role": boad_role, "name": "Banque Ouest Africaine de Développement (BOAD)", "source_ref": ev.ref,
                "excerpt": f"projet approuvé publié par la BOAD : « {title} »", "extraction_method": "text",
                **({"commitment_amount": money.amount, "commitment_currency": money.currency} if money else {}),
            })
        if beneficiary:
            participants.append({"role": "borrower", "name": beneficiary[:255], "source_ref": ev.ref,
                                 "excerpt": f"« ... en faveur de {beneficiary} »", "extraction_method": "text"})
        key = f"boad:project:{url.rstrip('/').rsplit('/', 1)[-1]}"[:255]
        return [assemble([ev], document_id=document_id, source_id=source_id, ingestion_key=key,
                         participants=participants,
                         flags=[{"code": "dfi_own_commitment_only",
                                 "detail": "amount = BOAD's approved financing as published; the total cost of the "
                                           "project is not published on this page"}] if money else None)]

    document = DocumentToRegister(url=url, content=content, title=f"BOAD — projet approuvé — {title}"[:500],
                                  file_format="html", period_year=approved.year if approved else None,
                                  original_filename="boad_project.html")
    return Reading(document=document, build=build, flags=flags)
