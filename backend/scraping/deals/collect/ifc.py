"""
IFC (International Finance Corporation) — Summary of Investment Information (SII) -> deals.

Discovery: the public sitemap of https://disclosures.ifc.org (index -> chunks, per-URL ``lastmod``),
``/project-detail/SII/<number>/<slug>`` pages only. The search API of the site requires a subscription
key embedded in its JavaScript: it is NOT used (restricted access is never bypassed), hence the
sitemap + checkpoints approach (an unchanged page is never read twice).

An SII page is server-rendered: a summary grid (``<strong>Label</strong><p class="esrs-value">``),
an "IFC's Investment as Approved by the Board" panel ("79.29 million (USD)" + product lines) and
free-text panels. Only the grid and the investment panel are read; free text (e.g. "a capex plan of
about 122 million" without currency) is never parsed for amounts.

The deal is IFC's investment (flag ``dfi_own_commitment_only``). For trade / risk-sharing PROGRAMMES
(GTFP, GTLP, GWFP, GTSF, GCPF, RSF ...) the approved figure is the programme envelope, not the line of
the named bank: the amount is then left NULL (flag ``program_level_amount``).
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

SITEMAP_URL = "https://disclosures.ifc.org/sitemap.xml"
SII_RE = re.compile(r"^https://disclosures\.ifc\.org/project-detail/SII/(?P<num>\d+)/[^/?#]+$")
PUBLISHER = "IFC"
IFC = "International Finance Corporation (IFC)"
PROGRAMME_RE = re.compile(r"^(gtfp|gtlp|gwfp|gtsf|gcpf|gafsp|rsf|slgp|gtsp|crf|bgf)\b")
PRODUCT_ROLES = {"loan": ("lender", "term_loan"), "equity": ("investor", "equity"),
                 "guarantee": ("guarantor", "guarantee"), "risk management": ("guarantor", None)}
INDUSTRY_SECTORS = {
    "telecommunications and technology": "telecom_media_tech",
    "financial markets": "financial_services",
    "financial institutions": "financial_services",
    "agribusiness and forestry": "agriculture",
    "manufacturing": "industry",
    "power": "energy",
    "oil, gas and mining": "energy",
}


def clean(fragment: str) -> str:
    return " ".join(html_lib.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def summary_grid(page_html: str) -> dict[str, str]:
    return {clean(k): clean(v) for k, v in
            re.findall(r"<strong>(.*?)</strong>\s*<p class=\"esrs-value\">(.*?)</p>", page_html, re.S)}


def investment_panel(page_html: str) -> tuple[str | None, list[tuple[str, str]]]:
    """('79.29 million (USD)', [('Loan', '79.29'), ...]) of the board-approved investment panel."""
    i = page_html.find("Investment as Approved by the Board")
    if i < 0:
        return None, []
    panel = page_html[i:]
    m = re.search(r'cmp-accordion__panel[^>]*>(.*?)</div>', panel, re.S)
    if not m:
        return None, []
    body = m.group(1)
    header = clean(body.split("<table", 1)[0]) or None
    rows = [(clean(a), clean(b)) for a, b in re.findall(r"<td>(.*?)</td>\s*<td>(.*?)</td>", body, re.S)]
    return header, rows


def page_title(page_html: str) -> str:
    m = re.search(r"<title>(.*?)</title>", page_html, re.S)
    return re.sub(r"^\d+\s*-\s*", "", clean(m.group(1))) if m else ""


class IfcCollector(DealCollector):
    source_key = "ifc"
    parser_version = 3  # safe backfill for records already imported by earlier parser versions
    source_short_name = "IFC"
    actor = "ifc_disclosure_collector"

    async def discover(self, since: date | None, until: date | None) -> list[Candidate]:
        res = await self.fetcher.get(SITEMAP_URL)
        if not res.ok:
            raise RuntimeError(f"IFC sitemap unavailable: {res.error}")
        urls, children = parse_sitemap(res.text)
        for child in children:
            sub = await self.fetcher.get(child)
            if not sub.ok:
                raise RuntimeError(f"IFC sitemap {child} unavailable: {sub.error}")
            urls += parse_sitemap(sub.text)[0]
        # Sitemap lastmod is a page-edit timestamp, not the deal's announcement date. Keep all SII
        # pages and apply the requested year after reading the official disclosure date.
        out = [Candidate(url=u, lastmod=m, hint={"since": since, "until": until}) for u, m in dict(urls).items()
               if SII_RE.match(u)]
        return sorted(out, key=lambda c: c.lastmod or "")

    def read(self, candidate: Candidate, res: FetchResult) -> Reading:
        return read_sii(candidate.url, res.content or b"", since=candidate.hint.get("since"),
                        until=candidate.hint.get("until"))


def read_sii(url: str, content: bytes, *, since: date | None = None, until: date | None = None) -> Reading:
    page_html = content.decode("utf-8", errors="replace")
    grid = summary_grid(page_html)
    number = grid.get("Project Number")
    company = grid.get("Company Name")
    if not number or not company:
        return Reading.skip("not_a_deal", "no SII summary grid (Project Number / Company Name)")
    country_text = grid.get("Country", "")
    codes = umoa_countries(country_text)
    if not codes:
        return Reading.skip("out_of_scope", f"country not in UMOA ({country_text or 'not published'})")
    name = page_title(page_html) or company
    flags: list[str] = []
    disclosed = parse_day(grid.get("Date SPI Disclosed", ""))
    events = grid.get("Previous Events", "")
    approved_m = re.search(r"Approved\s*:\s*([A-Za-z]{3,9}\.? \d{1,2}, \d{4})", events)
    signed_m = re.search(r"Signed\s*:\s*([A-Za-z]{3,9}\.? \d{1,2}, \d{4})", events)
    signed = parse_day(signed_m.group(1)) if signed_m else None
    if not in_window(disclosed or signed, since, until):
        return Reading.skip("out_of_scope", f"disclosure date {disclosed or signed} is outside the requested period")
    programme = bool(PROGRAMME_RE.match(fold(name)))
    header, rows = investment_panel(page_html)
    # The panel prints XOF for UMOA-currency commitments (audit 22/10/2026, M6): accepted as XOF.
    total = parse_money(header, allow_cfa=True) if header else None
    lines: list[tuple[str, str | None, object]] = []  # (role, deal_type, amount in USD)
    unit_m = re.search(r"\(million (?P<cur>[A-Z]{3})\)", page_html)
    line_currency = unit_m.group("cur") if unit_m else None
    for product, value in rows:
        kind = PRODUCT_ROLES.get(fold(product))
        number_value = parse_number(value) if value else None
        if kind is None or number_value is None or number_value <= 0:
            continue
        lines.append((kind[0], kind[1], number_value * 1_000_000 if line_currency else None))
    if header and total is None:
        flags.append("ifc_total_not_explicit")
    deal_types = {dt for _, dt, _ in lines if dt}
    deal_type = deal_types.pop() if len(deal_types) == 1 and len(lines) == 1 else None
    industry = grid.get("Industry", "")
    sector = INDUSTRY_SECTORS.get(fold(industry))
    status = grid.get("Status", "")
    validation_flags = []
    if total is not None and not programme:
        validation_flags.append({"code": "dfi_own_commitment_only",
                                 "detail": "amount = IFC's investment as approved by the Board (indicative, as "
                                           "published); the project cost and the other financiers are not read"})
    if programme:
        validation_flags.append({"code": "program_level_amount",
                                 "detail": f"'{name}' is a programme participation: the approved figure "
                                           f"({header}) is the programme envelope, not this counterpart's line"})
    if approved_m is None:
        validation_flags.append({"code": "pre_approval_disclosure",
                                 "detail": f"no Board approval published (status: {status or 'not published'})"})

    def build(document_id: str, source_id: str) -> list[dict]:
        ev = Evidence("ifc_sii", source_class="dfi_official", url=url, publisher=PUBLISHER, title=name,
                      published_at=disclosed,
                      excerpt=f"web_html · IFC Summary of Investment Information {url} · Project {number} · "
                              f"{company} · status {status}")
        ev.put("title", f"IFC {number} — {name}", f"Project Number {number} · « {name} »")
        ev.put("project_name", name, f"« {name} »")
        ev.put("deal_type", deal_type, f"Product Line : {', '.join(p for p, v in rows if v)}")
        ev.put("country_code", codes[0] if len(codes) == 1 else None, f"Country : {country_text}")
        ev.put("sector", sector, f"Industry : {industry}")
        ev.put("announcement_date", disclosed, f"Date SPI Disclosed : {grid.get('Date SPI Disclosed')}")
        ev.put("signing_date", signed, f"Previous Events : {events}")
        if total is not None and not programme:
            ev.put("amount", total.figure, f"IFC's Investment as Approved by the Board : {header}")
            ev.put("amount_original", header, f"IFC's Investment as Approved by the Board : {header}")
            ev.put("currency", total.currency, f"IFC's Investment as Approved by the Board : {header}")
            ev.put("unit", total.unit, f"IFC's Investment as Approved by the Board : {header}")
        participants: list[dict] = []
        for role, _dt, amount in lines:
            participants.append({
                "role": role, "name": IFC, "source_ref": ev.ref, "extraction_method": "text",
                "excerpt": f"IFC's Investment as Approved by the Board · {role} line",
                **({"commitment_amount": amount, "commitment_currency": line_currency}
                   if amount is not None and not programme else {}),
            })
        roles = {r for r, _, _ in lines}
        company_role = "borrower" if "lender" in roles else ("issuer" if roles == {"investor"} else None)
        if company_role:
            participants.append({"role": company_role, "name": company[:255], "source_ref": ev.ref,
                                 "excerpt": f"Company Name : {company}", "extraction_method": "text"})
        return [assemble([ev], document_id=document_id, source_id=source_id, ingestion_key=f"ifc:sii:{number}",
                         participants=participants, flags=validation_flags or None)]

    document = DocumentToRegister(url=url, content=content, title=f"IFC SII {number} — {name}"[:500],
                                  file_format="html", period_year=disclosed.year if disclosed else None,
                                  original_filename=f"ifc_sii_{number}.html")
    return Reading(document=document, build=build, flags=flags)
