"""
Rounds 4-7 — market infrastructure, official links, institution websites, secondary sources.

Official sources take priority. Optional search leads remain candidates until a person confirms ownership;
no URL is guessed from a bank name.
  - brvm_market_listings       : BRVM listed-company pages (market infrastructure, priority 4);
  - official_links_in_documents: website links printed in official documents / pages already
                                 collected for the entity (candidate → verified by content);
  - official_website_crawl     : bounded, robots.txt-aware crawl of VERIFIED websites for
                                 annual reports / financial statements (ACTIVE once a PDF is stored);
  - secondary_verified         : optional storage-rights-gated web-search leads (candidate only).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, unquote, urljoin, urlparse

from sqlalchemy import select

from app.constants.discovery import LINK_ROLE_PRIORITY
from app.models.country import Country
from app.models.discovery import DocumentEntity, EntitySource
from app.models.document import Document
from app.models.entity import Entity
from scraping.universe.http import extract_links, extract_sitemap_entries, html_to_text, is_pdf_url
from scraping.universe.normalize import core_key, country_codes_in, name_key, normalize_name
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult
from scraping.universe.strategies.reference_lists import get_source


def utcnow() -> datetime:
    return datetime.now(UTC)


async def upsert_entity_source(ctx: DiscoveryContext, *, entity_id: str, role: str, url: str | None,
                               source_id: str | None, status: str, method: str, evidence: str,
                               http_status: int | None = None, document_id: str | None = None) -> bool:
    """Create or update one entity ↔ source link. Returns True when a new link was created."""
    existing = (await ctx.db.execute(select(EntitySource).where(
        EntitySource.entity_id == entity_id, EntitySource.link_role == role, EntitySource.url == url,
        EntitySource.deleted_at.is_(None)))).scalars().first()
    now = utcnow()
    rank = {"RETIRED": 0, "BLOCKED": 1, "CANDIDATE": 2, "VERIFIED": 3, "ACTIVE": 4}
    if existing is not None:
        if existing.lifecycle_status == "RETIRED" and status == "CANDIDATE":
            # A human-retired search lead must not reappear as a candidate on the next scheduled run.
            existing.last_checked_at = now
            existing.last_http_status = http_status
            await ctx.db.flush()
            return False
        if rank[status] >= rank.get(existing.lifecycle_status, 0) or status == "BLOCKED":
            existing.lifecycle_status = status
        existing.last_checked_at = now
        existing.last_http_status = http_status
        existing.verification_evidence = evidence
        if status in ("VERIFIED", "ACTIVE") and existing.verified_at is None:
            existing.verified_at = now
        await ctx.db.flush()
        return False
    ctx.db.add(EntitySource(
        entity_id=entity_id, source_id=source_id, url=url, link_role=role, priority=LINK_ROLE_PRIORITY[role],
        lifecycle_status=status, discovery_method=method, discovery_run_id=ctx.run.id,
        evidence_document_id=document_id, verification_evidence=evidence,
        verified_at=now if status in ("VERIFIED", "ACTIVE") else None, last_checked_at=now,
        last_http_status=http_status,
    ))
    await ctx.db.flush()
    return True


async def entity_country_codes(ctx: DiscoveryContext) -> dict[str, str]:
    return {c.id: c.code for c in (await ctx.db.execute(select(Country))).scalars().all()}


# ====================================================================== BRVM
FINANCIAL_SECTORS = {"FINANCE", "FINANCES", "BANQUE", "BANQUES", "SERVICES FINANCIERS"}


def parse_brvm_profile(html: str) -> tuple[str | None, str | None, list[str]]:
    """(raison sociale, normalized sector, labels to resolve) of a BRVM listed-company page.

    Phase 17: the sector is read in any case ("FINANCE", "Banque" — the Coris BF page was missed
    because of an uppercase-only pattern); pages without a profile block are resolved on their title
    only (the country always comes from the official BRVM country listing, never from the name).
    """
    text = html_to_text(html)
    title = re.search(r"<title>([^<|]+)", html)
    m = re.search(r"Raison sociale\s*:\s*(.+?)\s+Secteur d.activit[ée]s\s*:\s*(.+?)\s+Date d", text, re.IGNORECASE)
    raison = m.group(1).strip() if m else None
    sector = normalize_name(m.group(2)) if m else None
    labels = [lbl for lbl in (raison, title.group(1).strip() if title else None) if lbl]
    return raison, sector, labels


class BrvmMarketListingsStrategy(DiscoveryStrategy):
    code = "brvm_market_listings"
    description = "BRVM — listed-company pages per country (market infrastructure source)"
    priority = 4
    handles = frozenset({"SOURCE_NOT_FOUND", "SOURCE_FOUND_UNVERIFIED"})
    BASE = "https://www.brvm.org"
    COUNTRY_PAGES = {
        "BJ": "benin", "BF": "burkina-faso", "CI": "cote-divoire", "GW": "guinee-bissau",
        "ML": "mali", "NE": "niger", "SN": "senegal", "TG": "togo",
    }
    ISSUER_RE = re.compile(r"/fr/emetteurs/societes-cotees/[a-z0-9-]+$")

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        source = await get_source(ctx, "BRVM")
        if source is None:
            result.errors.append({"error": "BRVM source not registered"})
            return result
        issuers: dict[str, str] = {}
        pages_read = 0
        for cc in ctx.country_codes:
            for page_no in range(20):  # Phase 17: every page of the country listing (was page 0 only)
                url = f"{self.BASE}/fr/pays-societes-cotees/{self.COUNTRY_PAGES[cc]}?page={page_no}"
                res = await ctx.fetcher.get(url)
                if not res.ok or res.redirected_to_homepage:
                    result.errors.append({"url": url, "error": res.error or "redirected to homepage"})
                    break
                pages_read += 1
                new = [link for link, _a in extract_links(res.text, res.final_url or url)
                       if self.ISSUER_RE.search(link) and link not in issuers]
                if not new:
                    break
                for link in new:
                    issuers[link] = cc
        result.details["listing_pages_read"] = pages_read
        matched, finance_unresolved = [], []
        for link, cc in sorted(issuers.items()):
            res = await ctx.fetcher.get(link)
            if not res.ok or res.redirected_to_homepage:
                result.errors.append({"url": link, "error": res.error or "redirected to homepage"})
                continue
            raison, sector, labels = parse_brvm_profile(res.text)
            if (sector is not None and sector not in FINANCIAL_SECTORS) or not labels:
                continue
            outcomes = [ctx.resolver.resolve_label(country_code=cc, label=lbl) for lbl in labels]
            ids = {o.entity_id for o in outcomes if o.status == "matched"}
            if len(ids) != 1:
                finance_unresolved.append({"country": cc, "raison_sociale": raison or labels[0], "url": link,
                                           "sector": sector,
                                           "candidates": [c for o in outcomes for c in o.candidates][:4]})
                continue
            entity_id = next(iter(ids))
            created = await upsert_entity_source(
                ctx, entity_id=entity_id, role="market_infrastructure", url=link, source_id=source.id,
                status="VERIFIED", method=self.code, http_status=res.status_code,
                evidence=f"BRVM listed company page, raison sociale '{raison}', sector FINANCE",
            )
            result.sources_found += int(created)
            matched.append({"country": cc, "raison_sociale": raison or labels[0], "entity_id": entity_id,
                            "url": link, "method": next(o.method for o in outcomes if o.status == "matched")})
            # Website links printed on the issuer page, if any: candidates verified by content.
            entity = await ctx.db.get(Entity, entity_id)
            for href, _a in extract_links(res.text, link):
                host = urlparse(href).netloc.lower()
                if not host or _is_platform(host):
                    continue
                site = f"{urlparse(href).scheme}://{host}/"
                verdict = await verify_website(ctx, entity, cc, site)
                result.sources_found += int(await upsert_entity_source(
                    ctx, entity_id=entity_id, role="official_website", url=site, source_id=None,
                    status=verdict["status"], method=self.code, evidence=verdict["evidence"],
                    http_status=verdict["http_status"],
                ))
                result.details.setdefault("website_candidates_on_brvm", []).append(site)
        result.details["issuers_scanned"] = len(issuers)
        result.details["finance_issuers_matched"] = matched
        result.details["finance_issuers_unresolved"] = finance_unresolved
        return result


_PLATFORM_HOSTS = ("facebook.", "twitter.", "x.com", "linkedin.", "youtube.", "instagram.", "google.", "apple.",
                   "bceao.int", "cb-umoa.org", "brvm.org", "umoatitres.org", "amf-umoa.org", "whatsapp.",
                   "wikipedia.", "gouv.", "w3.org", "adobe.", "microsoft.")


def _is_platform(host: str) -> bool:
    return any(p in host for p in _PLATFORM_HOSTS)


# ====================================================================== links in official documents
_URL_RE = re.compile(r"\b(?:https?://)?(?:www\.)[a-z0-9-]+(?:\.[a-z0-9-]+)+(?:/[^\s)\"'<>]*)?", re.IGNORECASE)


class OfficialLinksInDocumentsStrategy(DiscoveryStrategy):
    code = "official_links_in_documents"
    description = ("Website addresses printed in institution-specific official documents (own reports, BRVM "
                   "filings, group reports listing their network). A printed address is only a CANDIDATE: it is "
                   "attributed to a bank only when the printed country heading and the site content agree")
    priority = 2
    handles = frozenset({"SOURCE_NOT_FOUND", "SOURCE_FOUND_UNVERIFIED"})
    COUNTRY_WINDOW = 8  # a country heading applies to the next lines only

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        countries = await entity_country_codes(ctx)
        docs = (await ctx.db.execute(select(Document).where(
            Document.document_scope == "institution_specific", Document.download_status == "downloaded",
            Document.deleted_at.is_(None)))).scalars().all()
        candidates: dict[tuple[str, str], dict] = {}  # (country, site) → evidence
        scanned = 0
        for doc in docs:
            content = ctx.registrar.read_bytes(doc)
            if not content:
                continue
            scanned += 1
            owner = await ctx.db.get(Entity, doc.entity_id) if doc.entity_id else None
            owner_cc = countries.get(owner.country_id or "") if owner else None
            for page_number, line, cc in _urls_with_country(content, self.COUNTRY_WINDOW):
                for raw in _URL_RE.findall(line):
                    url = raw if raw.lower().startswith("http") else f"https://{raw}"
                    host = urlparse(url).netloc.lower().rstrip(".")
                    if not host or _is_platform(host):
                        continue
                    site = f"https://{host}/"
                    country = cc or owner_cc  # without a printed heading, only the document owner's country
                    if country is None or country not in ctx.country_codes:
                        continue
                    candidates.setdefault((country, site), {
                        "document_id": doc.id, "page": page_number, "heading": cc,
                        "owner": owner.canonical_name if owner else None,
                    })
        verified, unverified = [], []
        for (cc, site), ev in sorted(candidates.items()):
            pool = [e for e in ctx.resolver.entities.values() if e.country_code == cc]
            confirmed = []
            last = None
            for ent in pool:
                entity = await ctx.db.get(Entity, ent.id)
                verdict = await verify_website(ctx, entity, cc, site)
                last = verdict
                if verdict["status"] in ("BLOCKED", "CANDIDATE") and verdict["http_status"] != 200:
                    break  # the site itself is unreachable / blocked: same verdict for every bank
                if verdict["status"] == "VERIFIED":
                    confirmed.append((ent, verdict))
            evidence = (f"printed in document {ev['document_id']} p.{ev['page']}"
                        + (f" under country heading {ev['heading']}" if ev["heading"] else " (owner's country)"))
            if len(confirmed) == 1:
                ent, verdict = confirmed[0]
                result.sources_found += int(await upsert_entity_source(
                    ctx, entity_id=ent.id, role="official_website", url=site, source_id=None, status="VERIFIED",
                    method=self.code, evidence=f"{evidence}; {verdict['evidence']}", http_status=verdict["http_status"],
                    document_id=ev["document_id"]))
                verified.append({"country": cc, "site": site, "entity_id": ent.id, "evidence": evidence})
            elif ev["heading"] is None and ev["owner"]:
                # The owner's own document prints the address but the site does not confirm the name.
                owner_ent = next((e for e in pool if e.canonical_name == ev["owner"]), None)
                if owner_ent is not None and last is not None:
                    status = "BLOCKED" if last["status"] == "BLOCKED" else "CANDIDATE"
                    result.sources_found += int(await upsert_entity_source(
                        ctx, entity_id=owner_ent.id, role="official_website", url=site, source_id=None,
                        status=status, method=self.code, evidence=f"{evidence}; {last['evidence']}",
                        http_status=last["http_status"], document_id=ev["document_id"]))
                    if status == "BLOCKED":
                        result.blocked_entity_ids.add(owner_ent.id)
                unverified.append({"country": cc, "site": site, "reason": "not confirmed by the site content",
                                   "evidence": evidence})
            else:
                unverified.append({"country": cc, "site": site, "evidence": evidence,
                                   "reason": f"{len(confirmed)} banks confirmed by the site content"
                                   if confirmed else (last or {}).get("evidence", "not verified")})
        result.details.update(documents_scanned=scanned, candidate_sites=len(candidates), verified=verified,
                              unverified=unverified)
        return result


def _urls_with_country(content: bytes, window: int):
    """(page, line, country heading within the previous ``window`` lines) for lines holding an address."""
    import pymupdf

    from scraping.universe.normalize import country_code_for_label

    try:
        pdf = pymupdf.open(stream=content, filetype="pdf")
    except Exception:
        return
    with pdf:
        for pno in range(pdf.page_count):
            lines = [ln.strip() for ln in pdf[pno].get_text().splitlines() if ln.strip()]
            heading, distance = None, window + 1
            for line in lines:
                cc = country_code_for_label(line)
                if cc:
                    heading, distance = cc, 0
                    continue
                distance += 1
                if _URL_RE.search(line):
                    yield pno + 1, line, heading if distance <= window else None


def _pdf_text(content: bytes, max_pages: int = 6) -> str:
    import pymupdf

    try:
        with pymupdf.open(stream=content, filetype="pdf") as pdf:
            return " ".join(pdf[i].get_text() for i in range(min(max_pages, pdf.page_count)))
    except Exception:
        return ""


async def _fetch_site(ctx: DiscoveryContext, url: str) -> dict:
    """One fetch per site and per run (robots.txt first). Cached in the run context."""
    cache = ctx.options.setdefault("_site_cache", {})
    if url in cache:
        return cache[url]
    if not await ctx.fetcher.allowed_by_robots(url):
        out = {"status": "BLOCKED", "http_status": None, "evidence": "disallowed by robots.txt", "text": ""}
    else:
        res = await ctx.fetcher.get(url)
        if res.status_code in (401, 403, 429):
            out = {"status": "BLOCKED", "http_status": res.status_code, "evidence": f"HTTP {res.status_code}",
                   "text": ""}
        elif not res.ok:
            out = {"status": "CANDIDATE", "http_status": res.status_code, "evidence": f"unreachable: {res.error}",
                   "text": ""}
        else:
            out = {"status": "FETCHED", "http_status": res.status_code, "final_url": res.final_url,
                   "evidence": "", "text": f" {normalize_name(html_to_text(res.text))} "}
    cache[url] = out
    return out


async def verify_website(ctx: DiscoveryContext, entity: Entity, country_code: str | None, url: str) -> dict:
    """CANDIDATE → VERIFIED only if the page names the entity; BLOCKED on 401/403/429/robots."""
    site = await _fetch_site(ctx, url)
    if site["status"] != "FETCHED":
        return {"status": site["status"], "evidence": site["evidence"], "http_status": site["http_status"]}
    page = site["text"]
    full = name_key(entity.canonical_name)
    if full and len(full) >= 4 and f" {full} " in page:
        return {"status": "VERIFIED", "http_status": site["http_status"],
                "evidence": f"final URL {site['final_url']} mentions '{full}'"}
    # The name without its country ("ECOBANK", "SOCIETE GENERALE") is also printed by the group site and
    # by every sister bank (audit 22/10/2026, D3): it verifies the site only together with the entity's
    # country on the same page, and only if no OTHER UMOA country is named there.
    short = {core_key(entity.canonical_name)}
    if entity.short_name:
        short.add(normalize_name(entity.short_name))
    hit = next((n for n in short if n and len(n) >= 4 and f" {n} " in page), None)
    countries = country_codes_in(page)
    if hit and country_code and countries == {country_code}:
        return {"status": "VERIFIED", "http_status": site["http_status"],
                "evidence": f"final URL {site['final_url']} mentions '{hit}' and its country {country_code} only"}
    if hit:
        return {"status": "CANDIDATE", "http_status": site["http_status"],
                "evidence": f"final URL {site['final_url']} mentions '{hit}' but countries {sorted(countries) or '-'} "
                            f"(expected {country_code} alone): group or sister site, to confirm by a human"}
    return {"status": "CANDIDATE", "http_status": site["http_status"],
            "evidence": f"final URL {site['final_url']} does not mention the entity name"}


# ====================================================================== website crawl
_REPORT_WORDS = ("RAPPORT ANNUEL", "ANNUAL REPORT", "ETATS FINANCIERS", "FINANCIAL STATEMENTS", "COMPTES ANNUELS",
                 "PILIER 3", "PILLAR 3", "RESULTATS FINANCIERS", "BILAN")
_REPORT_KEYS = tuple(normalize_name(word) for word in _REPORT_WORDS)
_YEAR_RE = re.compile(r"(?<!\d)(?:19|20)\d{2}(?!\d)")


def _pdf_filename_hint(url: str) -> str:
    """Filename evidence only; never infer a reporting year from an upload directory."""
    parsed = urlparse(url)
    parts = [unquote(parsed.path.rsplit("/", 1)[-1])]
    parts.extend(unquote(value) for _key, value in parse_qsl(parsed.query) if ".pdf" in value.lower())
    return " ".join(part for part in parts if part)


def _is_report_candidate(label: str, url: str, years: set[str]) -> bool:
    evidence = normalize_name(f"{label} {_pdf_filename_hint(url)}")
    if not any(word in evidence for word in _REPORT_KEYS):
        return False
    years_in_evidence = set(_YEAR_RE.findall(evidence))
    # Yearless filenames remain eligible; the stored period stays unknown.
    return not years or not years_in_evidence or bool(years & years_in_evidence)


class OfficialWebsiteCrawlStrategy(DiscoveryStrategy):
    code = "official_website_crawl"
    description = ("Bounded crawl of VERIFIED / ACTIVE official websites (same domain, sitemaps, depth 2, keyword-guided "
                   "navigation, robots.txt, page / size caps) for annual reports and financial statements")
    priority = 3
    handles = frozenset({"DOCUMENT_NOT_FOUND"})
    max_pages_per_site = 30
    max_depth = 2
    max_pdfs_per_site = 12
    max_pdf_bytes = 30_000_000
    max_sitemaps_per_site = 8
    max_sitemap_urls_per_site = 5_000

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        target_ids = {g.entity_id for g in targets if g.entity_id}
        sites = (await ctx.db.execute(select(EntitySource).where(
            EntitySource.entity_id.in_(target_ids), EntitySource.link_role == "official_website",
            EntitySource.lifecycle_status.in_(("VERIFIED", "ACTIVE")), EntitySource.deleted_at.is_(None)
        ))).scalars().all()
        result.details["verified_websites"] = len(sites)
        per_site = []
        for site in sites:
            per_site.append(await self._crawl(ctx, site, result))
        result.details["sites"] = per_site
        return result

    async def _crawl(self, ctx, site: EntitySource, result: StrategyResult) -> dict[str, object]:
        years = {str(y) for y in ctx.target_years}
        host = urlparse(site.url).netloc.lower()

        def is_same_host(url: str) -> bool:
            parsed = urlparse(url)
            return parsed.scheme.lower() in ("http", "https") and parsed.netloc.lower() == host

        queue: list[tuple[str, int]] = [(site.url, 0)]
        seen: set[str] = set()
        pdfs: list[tuple[str, str]] = []
        sitemap_lookup = getattr(ctx.fetcher, "sitemap_urls", None)
        sitemap_queue = await sitemap_lookup(site.url) if sitemap_lookup else []
        sitemap_queue = [url for url in sitemap_queue if is_same_host(url)][:self.max_sitemaps_per_site]
        sitemap_requests = len(sitemap_queue)
        if sitemap_lookup and not sitemap_queue:
            sitemap_queue = [urljoin(site.url, "/sitemap.xml")]
            sitemap_requests = 1
        seen_sitemaps: set[str] = set()
        sitemap_url_count = 0
        sitemap_fetch_failures = 0
        sitemap_blocked = 0
        page_fetch_failures = 0
        page_non_html = 0
        page_blocked = 0

        # Sitemaps find reports that are not linked from the bounded home-page crawl.
        while sitemap_queue and len(seen_sitemaps) < self.max_sitemaps_per_site:
            sitemap_url = sitemap_queue.pop(0)
            if sitemap_url in seen_sitemaps or not is_same_host(sitemap_url):
                continue
            seen_sitemaps.add(sitemap_url)
            if not await ctx.fetcher.allowed_by_robots(sitemap_url):
                result.blocked_entity_ids.add(site.entity_id)
                sitemap_blocked += 1
                continue
            sitemap = await ctx.fetcher.get(sitemap_url)
            if not sitemap.ok:
                sitemap_fetch_failures += 1
                continue
            is_index, entries = extract_sitemap_entries(sitemap.content or b"", sitemap.final_url or sitemap_url)
            if is_index:
                sitemap_queue.extend(loc for loc, _title in entries
                                     if is_same_host(loc) and loc not in seen_sitemaps)
                continue
            for location, title in entries:
                sitemap_url_count += 1
                if sitemap_url_count > self.max_sitemap_urls_per_site:
                    break
                if is_same_host(location) and is_pdf_url(location) and _is_report_candidate(title, location, years):
                    filename = _pdf_filename_hint(location)
                    pdfs.append((location, title or filename))
            if sitemap_url_count > self.max_sitemap_urls_per_site:
                break

        while queue and len(seen) < self.max_pages_per_site:
            url, depth = queue.pop(0)
            if url in seen:
                continue
            seen.add(url)
            if not await ctx.fetcher.allowed_by_robots(url):
                result.blocked_entity_ids.add(site.entity_id)
                page_blocked += 1
                continue
            res = await ctx.fetcher.get(url)
            if not res.ok:
                page_fetch_failures += 1
                continue
            if "html" not in (res.content_type or "html"):
                page_non_html += 1
                continue
            for link, anchor in extract_links(res.text, res.final_url or url):
                if not is_same_host(link):
                    continue  # same domain only
                if is_pdf_url(link):
                    if _is_report_candidate(anchor, link, years):
                        pdfs.append((link, anchor))
                else:
                    label = normalize_name(unquote(f"{anchor} {link}"))
                    if depth < self.max_depth and any(w in label for w in _NAV_WORDS):
                        queue.append((link, depth + 1))
        stored = 0
        pdf_fetch_failures = 0
        invalid_pdfs = 0
        oversized_pdfs = 0
        pdf_blocked = 0
        pdfs_by_url: dict[str, str] = {}
        for link, title in pdfs:
            if link not in pdfs_by_url or len(title) > len(pdfs_by_url[link]):
                pdfs_by_url[link] = title
        unique_pdfs = list(pdfs_by_url.items())
        target_year_order = [str(year) for year in ctx.target_years]

        def candidate_priority(candidate: tuple[str, str]) -> tuple[int, int]:
            label = normalize_name(f"{candidate[1]} {_pdf_filename_hint(candidate[0])}")
            found_years = set(_YEAR_RE.findall(label))
            for index, year in enumerate(target_year_order):
                if year in found_years:
                    return 0, index
            return 1, 0  # Unknown-period candidates remain eligible after requested years.

        unique_pdfs.sort(key=candidate_priority)
        for link, anchor in unique_pdfs[: self.max_pdfs_per_site]:
            if not await ctx.fetcher.allowed_by_robots(link):
                result.blocked_entity_ids.add(site.entity_id)
                pdf_blocked += 1
                continue
            res = await ctx.fetcher.get(link)
            if not res.ok:
                pdf_fetch_failures += 1
                continue
            if not res.is_pdf:
                invalid_pdfs += 1
                continue
            if len(res.content or b"") > self.max_pdf_bytes:
                oversized_pdfs += 1
                continue
            own = await _own_publication_source(ctx, site)
            registered = await ctx.registrar.register_pdf(
                ctx.db, source=own, url=link, content=res.content,
                title=anchor or _pdf_filename_hint(link),
                document_type="annual_report", period_year=_year(f"{anchor} {_pdf_filename_hint(link)}"),
                entity_id=site.entity_id, document_scope="institution_specific",
            )
            result.new_documents += int(registered.is_new)
            existing = (await ctx.db.execute(select(DocumentEntity).where(
                DocumentEntity.document_id == registered.document.id, DocumentEntity.entity_id == site.entity_id,
                DocumentEntity.link_type == "annual_report", DocumentEntity.deleted_at.is_(None)))).scalars().first()
            if existing is None:
                ctx.db.add(DocumentEntity(document_id=registered.document.id, entity_id=site.entity_id,
                                          link_type="annual_report", label_in_document=(anchor or "")[:500],
                                          method=self.code, evidence=link))
                result.new_document_links += 1
            # VERIFIED only: the publication becomes ACTIVE once the document has been parsed into
            # observations (institution_document_extraction).
            await upsert_entity_source(
                ctx, entity_id=site.entity_id, role="official_publications", url=link, source_id=own.id,
                status="VERIFIED", method=self.code, evidence=f"PDF stored from {site.url}", http_status=200,
                document_id=registered.document.id,
            )
            stored += 1
        outcome = "downloaded" if stored else (
            "no_matching_pdf_links" if not unique_pdfs else
            "blocked_by_robots" if pdf_blocked and not (pdf_fetch_failures or invalid_pdfs or oversized_pdfs) else
            "pdf_fetch_or_validation_failed"
        )
        if len(unique_pdfs) > self.max_pdfs_per_site:
            outcome += "; pdf_limit_reached"
        return {
            "entity_id": site.entity_id, "site": site.url, "outcome": outcome,
            "pages_visited": len(seen), "page_limit_reached": bool(queue),
            "page_fetch_failures": page_fetch_failures, "page_non_html": page_non_html,
            "page_blocked": page_blocked,
            "sitemaps_requested": sitemap_requests, "sitemaps_checked": len(seen_sitemaps),
            "sitemap_url_count": sitemap_url_count, "sitemap_fetch_failures": sitemap_fetch_failures,
            "sitemap_blocked": sitemap_blocked, "candidate_pdfs": len(pdfs),
            "unique_candidate_pdfs": len(unique_pdfs), "pdfs_attempted": min(len(unique_pdfs), self.max_pdfs_per_site),
            "pdfs_stored": stored, "pdf_fetch_failures": pdf_fetch_failures,
            "invalid_pdfs": invalid_pdfs, "oversized_pdfs": oversized_pdfs, "pdf_blocked": pdf_blocked,
        }


_NAV_WORDS = ("RAPPORT", "FINANC", "INVESTISSEUR", "INVESTOR", "PUBLICATION", "DOCUMENT", "RESULTAT", "ANNUAL",
              "ETATS", "COMMUNIQUE", "ACTIONNAIRE", "GOUVERNANCE")


async def _own_publication_source(ctx, site: EntitySource):
    """Source row for an institution website (source_type 'bank'), created on first document."""
    from app.models.source import Source

    host = urlparse(site.url).netloc.lower()
    src = (await ctx.db.execute(select(Source).where(Source.url == site.url, Source.deleted_at.is_(None)))).scalars().first()
    if src is None:
        entity = await ctx.db.get(Entity, site.entity_id)
        src = Source(name=f"{entity.canonical_name} — site officiel"[:255], short_name=host[:50],
                     publisher=entity.canonical_name[:255], url=site.url, source_type="bank", priority=1,
                     description="Institution website verified by the discovery engine (name found on the page).",
                     is_active=True, lifecycle_status="ACTIVE")
        ctx.db.add(src)
        await ctx.db.flush()
    return src


def _year(text: str) -> int | None:
    """Year printed in the document name; upload folders (/2025/01/) are NOT used."""
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}
    return years.pop() if len(years) == 1 else None  # several different years: not guessed


# ====================================================================== secondary search candidates
class SecondaryVerifiedStrategy(DiscoveryStrategy):
    code = "secondary_verified"
    description = "Optional web-search leads; pages remain candidates until official ownership is confirmed"
    priority = 7
    handles = frozenset({"SOURCE_NOT_FOUND", "DOCUMENT_NOT_FOUND"})

    def __init__(self, provider=None, *, max_results: int = 5, max_entities: int = 20) -> None:
        self.provider = provider
        self.max_results = max_results
        self.max_entities = max_entities
        self.enabled = provider is not None
        self.disabled_reason = None if self.enabled else "no search provider configured; set provider and credentials"

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        if self.provider is None:
            return result
        entity_ids = list(dict.fromkeys(gap.entity_id for gap in targets if gap.entity_id))[:self.max_entities]
        known_site = set((await ctx.db.execute(select(EntitySource.entity_id).where(
            EntitySource.entity_id.in_(entity_ids), EntitySource.link_role == "official_website",
            EntitySource.lifecycle_status.in_(("CANDIDATE", "VERIFIED", "ACTIVE")),
            EntitySource.deleted_at.is_(None),
        ))).scalars().all()) if entity_ids else set()
        outcome = {"entities_queried": 0, "results_returned": 0, "pages_matching_name": 0,
                   "candidate_links_recorded": 0, "errors": 0, "human_officiality_review_required": True}
        for entity_id in entity_ids:
            if entity_id in known_site:
                continue
            indexed = ctx.resolver.entities.get(entity_id)
            if indexed is None:
                continue
            entity = await ctx.db.get(Entity, entity_id)
            if entity is None:
                continue
            query = f'"{indexed.canonical_name}" official website {indexed.country_code or ""}'
            outcome["entities_queried"] += 1
            try:
                candidates = await self.provider.search(query, country_code=indexed.country_code,
                                                        limit=self.max_results)
            except Exception as err:
                outcome["errors"] += 1
                result.errors.append({"entity_id": entity_id,
                                      "error": f"search provider {type(err).__name__}: {str(err)[:300]}"})
                continue
            outcome["results_returned"] += len(candidates)
            for url in candidates:
                if is_pdf_url(url) or not await ctx.fetcher.allowed_by_robots(url, follow_redirects=False):
                    continue
                # Do not follow a search-result redirect; it could cross into a different domain.
                fetched = await ctx.fetcher.get(url, follow_redirects=False)
                page = f" {normalize_name(html_to_text(fetched.text))} " if fetched.ok else ""
                labels = {normalize_name(entity.canonical_name), core_key(entity.canonical_name)}
                if not page or not any(label and len(label) >= 4 and f" {label} " in page for label in labels):
                    continue
                outcome["pages_matching_name"] += 1
                created = await upsert_entity_source(
                    ctx, entity_id=entity_id, role="official_website", url=url, source_id=None,
                    status="CANDIDATE", method=self.code,
                    evidence=("Web search lead; fetched page contains the institution name, but official domain "
                              "ownership still requires human confirmation; redirects were not followed."),
                    http_status=fetched.status_code,
                )
                outcome["candidate_links_recorded"] += int(created)
                result.sources_found += int(created)
        result.details["search"] = outcome
        return result
