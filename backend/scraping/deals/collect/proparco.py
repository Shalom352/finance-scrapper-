"""
Proparco (groupe AFD) — "carte des projets" sheets -> deals.

Discovery: the public sitemap (https://www.proparco.fr/sitemap.xml, per-URL ``lastmod``), French
sheets ``/fr/carte-des-projets/<slug>`` only. Each sheet is a definition list (``<dt>`` / ``<dd>``):
"Date de signature", "Localisation", "Outils de financement", "Montant du financement (€)",
"Détails du financement", "Client", "Nature du client", "Numéro de projet"...

The published amount is Proparco's own financing (EUR as printed in the "(€)" field); the deal is
Proparco's financing operation (flag ``dfi_own_commitment_only``). Each instrument of "Détails du
financement" becomes a Proparco participation with its own commitment ONLY when that segment carries
one explicit amount and currency; grants and technical assistance carry no financing role.
"""
from __future__ import annotations

import html as html_lib
import re
from datetime import date

from scraping.deals.collect.amounts import (
    fold,
    parse_day,
    parse_money,
    parse_number,
    umoa_countries,
)
from scraping.deals.collect.base import (
    Candidate,
    DealCollector,
    DocumentToRegister,
    Evidence,
    Reading,
    assemble,
    in_window,
    parse_sitemap,
)
from scraping.universe.http import FetchResult

SITEMAP_URL = "https://www.proparco.fr/sitemap.xml"
SHEET_RE = re.compile(r"^https://www\.proparco\.fr/fr/carte-des-projets/[a-z0-9-]+/?$")
PUBLISHER = "Proparco"
PROPARCO = "Proparco"

CLIENT_NATURE_SECTORS = {"microfinance": "financial_services", "institution financiere": "financial_services"}
# One segment of "Détails du financement" -> (Proparco role, debt_type). Grants / TA -> no role.
SEGMENT_KINDS = (
    (re.compile(r"\bgarantie"), "guarantor", "guarantee"),
    (re.compile(r"\bprise[s]? de participation|\bfonds propres|\bequity\b|\bcapital\b"), "investor", None),
    (re.compile(r"\bpret[s]? senior"), "lender", "senior_loan"),
    (re.compile(r"\bpret[s]? subordonne"), "lender", "subordinated_loan"),
    (re.compile(r"\bmezzanine"), "lender", "mezzanine"),
    (re.compile(r"\bconvertible"), "lender", "convertible"),
    (re.compile(r"\bligne[s]? de credit"), "lender", "credit_line"),
    (re.compile(r"\bpret"), "lender", None),
    (re.compile(r"\bsubvention|\baccompagnement technique|\bassistance technique"), None, None),
)


def clean(fragment: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def sheet_fields(page_html: str) -> dict[str, str]:
    return {clean(dt): clean(dd) for dt, dd in
            re.findall(r"<dt[^>]*>(.*?)</dt>\s*<dd[^>]*>(.*?)</dd>", page_html, re.S)}


def detail_segments(text: str) -> list[str]:
    """'Prêt senior de 45,9 MEUR, subvention de 6,6 MEUR et 150 KEUR d'Accompagnement technique'
    -> three segments. Decimal commas ('45,9') are not separators."""
    parts = re.split(r",(?!\d)|\bet\b", text)
    return [p.strip() for p in parts if p.strip()]


class ProparcoCollector(DealCollector):
    source_key = "proparco"
    source_short_name = "Proparco"
    actor = "proparco_project_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        res = await self.fetcher.get(SITEMAP_URL)
        if not res.ok:
            raise RuntimeError(f"Proparco sitemap unavailable: {res.error}")
        urls, children = parse_sitemap(res.text)
        for child in children:
            sub = await self.fetcher.get(child)
            if not sub.ok:
                raise RuntimeError(f"Proparco sitemap {child} unavailable: {sub.error}")
            urls += parse_sitemap(sub.text)[0]
        # Sitemap lastmod reflects edits to the web page, not the deal's signing year. Apply the
        # requested period to the actual signing date extracted from each official project sheet.
        out = [Candidate(url=u, lastmod=m, hint={"since": since, "until": until}) for u, m in dict(urls).items()
               if SHEET_RE.match(u)]
        return sorted(out, key=lambda c: c.lastmod or "")

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_sheet(candidate.url, res.content or b"", since=candidate.hint.get("since"),
                          until=candidate.hint.get("until"))


def read_sheet(url: str, content: bytes, *, since: date | None = None, until: date | None = None) -> Reading:
    page_html = content.decode("utf-8", errors="replace")
    fields = sheet_fields(page_html)
    if "Localisation" not in fields or "Client" not in fields:
        return Reading.skip("not_a_deal", "not a Proparco project sheet (no Localisation / Client)")
    location = fields["Localisation"]
    codes = umoa_countries(location)
    if not codes:
        return Reading.skip("out_of_scope", f"no UMOA country ({location})")
    listed = [p.strip() for p in location.split(",") if p.strip()]
    h1 = clean(m.group(1)) if (m := re.search(r"<h1[^>]*>(.*?)</h1>", page_html, re.S)) else ""
    client = fields["Client"]
    number = fields.get("Numéro de projet")
    signed_text = fields.get("Date de signature", "")
    signed = parse_day(signed_text)
    if not in_window(signed, since, until):
        return Reading.skip("out_of_scope", f"signing date {signed} is outside the requested period")
    eur_text = fields.get("Montant du financement (€)", "")
    eur = parse_number(eur_text) if eur_text else None
    details = fields.get("Détails du financement", "")
    tools = fields.get("Outils de financement", "")
    flags: list[str] = []

    commitments: list[tuple[str, str | None, object, str]] = []  # (role, debt_type, Money, segment)
    roles: set[str] = set()
    for seg in detail_segments(details):
        kind = next(((role, debt) for rx, role, debt in SEGMENT_KINDS if rx.search(fold(seg))), None)
        if kind is None:
            flags.append("proparco_detail_segment_not_read")
            continue
        role, debt = kind
        if role is None:
            continue
        roles.add(role)
        money = parse_money(seg)
        if money is None:
            flags.append("proparco_segment_without_explicit_amount")
        commitments.append((role, debt, money, seg))
    if not commitments and not details:
        folded_tools = fold(tools)
        for rx, role, debt in SEGMENT_KINDS:
            if role and rx.search(folded_tools):
                roles.add(role)
                commitments.append((role, None, None, tools))
                break
    debt_types = {d for r, d, _, _ in commitments if r in ("lender", "guarantor") and d}
    debt_type = debt_types.pop() if len(debt_types) == 1 and len([c for c in commitments if c[0] != "investor"]) == 1 \
        else None
    deal_type = {frozenset({"lender"}): "term_loan", frozenset({"guarantor"}): "guarantee",
                 frozenset({"investor"}): "equity"}.get(frozenset(roles))
    nature = fields.get("Nature du client", "")
    sector = CLIENT_NATURE_SECTORS.get(fold(nature))
    title = f"Proparco — {client}" + (f" — {h1}" if h1 else "")

    def build(document_id: str, source_id: str) -> list[dict]:
        ev = Evidence("proparco_sheet", source_class="dfi_official", url=url, publisher=PUBLISHER,
                      title=h1 or client, published_at=signed,
                      excerpt=f"web_html · fiche projet Proparco {url}" + (f" · n° {number}" if number else ""))
        ev.put("title", title, f"Client : {client}" + (f" · « {h1} »" if h1 else ""))
        ev.put("deal_type", deal_type, f"Détails du financement : {details or tools}")
        ev.put("debt_type", debt_type, f"Détails du financement : {details}")
        if len(listed) == 1:
            ev.put("country_code", codes[0], f"Localisation : {location}")
        ev.put("sector", sector, f"Nature du client : {nature}")
        ev.put("signing_date", signed, f"Date de signature : {signed_text}")
        if eur is not None and eur > 0:
            ev.put("amount", eur, f"Montant du financement (€) : {eur_text}")
            ev.put("amount_original", f"{eur_text} €", f"Montant du financement (€) : {eur_text}")
            ev.put("currency", "EUR", f"Montant du financement (€) : {eur_text}")
            ev.put("unit", "units", f"Montant du financement (€) : {eur_text}")
        participants: list[dict] = []
        for role, _debt, money, seg in commitments:
            participants.append({
                "role": role, "name": PROPARCO, "source_ref": ev.ref, "excerpt": f"Détails du financement : {seg}",
                "extraction_method": "text",
                **({"commitment_amount": money.amount, "commitment_currency": money.currency} if money else {}),
            })
        client_role = "borrower" if "lender" in roles else ("issuer" if roles == {"investor"} else None)
        if client_role:
            participants.append({"role": client_role, "name": client[:255], "source_ref": ev.ref,
                                 "excerpt": f"Client : {client}", "extraction_method": "text"})
        key = f"proparco:project:{number or url.rstrip('/').rsplit('/', 1)[-1]}"
        return [assemble([ev], document_id=document_id, source_id=source_id, ingestion_key=key,
                         participants=participants,
                         flags=[{"code": "dfi_own_commitment_only",
                                 "detail": "amount = Proparco's financing as published (EUR field of the sheet); "
                                           "the other financiers and the project cost are not published there"}]
                         if eur else None)]

    document = DocumentToRegister(url=url, content=content, title=f"Proparco — fiche projet — {client}"[:500],
                                  file_format="html", period_year=signed.year if signed else None,
                                  original_filename="proparco_project.html")
    return Reading(document=document, build=build, flags=flags)
