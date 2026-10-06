"""
Official reference list strategies (rounds 1-2): BCEAO and Commission Bancaire de l'UMOA.

The seed pages below are sections of the two official sites already registered as sources
(migration 0004); they are configuration, not data. The list itself, its date and every
count are read from the downloaded official PDF.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from urllib.parse import unquote

from sqlalchemy import select

from app.core.logging import get_logger
from app.models.source import Source
from scraping.universe.http import extract_links
from scraping.universe.materializer import UniverseMaterializer, refresh_current_snapshot
from scraping.universe.normalize import normalize_name
from scraping.universe.reference_list import FRENCH_MONTHS, ReferenceListParser
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult

logger = get_logger(__name__)


def utcnow() -> datetime:
    return datetime.now(UTC)


async def get_source(ctx: DiscoveryContext, short_name: str) -> Source | None:
    return (await ctx.db.execute(
        select(Source).where(Source.short_name == short_name, Source.deleted_at.is_(None)))).scalar_one_or_none()


class ReferenceListStrategy(DiscoveryStrategy):
    priority = 1
    always_run = True
    source_short_name: str

    async def locate(self, ctx: DiscoveryContext, result: StrategyResult) -> list[tuple[str, str]]:
        raise NotImplementedError

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult()
        source = await get_source(ctx, self.source_short_name)
        if source is None:
            result.reference_unavailable = True
            result.reference_reason = f"source {self.source_short_name} not registered"
            return result
        candidates = await self.locate(ctx, result)
        source.last_checked_at = utcnow()
        result.details["candidates"] = [u for u, _ in candidates]
        if not candidates:
            result.reference_unavailable = True
            result.reference_reason = "official list not found on the source"
            source.last_error = result.reference_reason
            return result

        parser = ReferenceListParser()
        materializer = UniverseMaterializer(ctx.resolver, ctx.universe_code)
        snapshots = []
        for url, title in candidates:
            fetched = await ctx.fetcher.get(url)
            source.last_http_status = fetched.status_code
            if not fetched.ok or not fetched.is_pdf:
                reason = fetched.error or f"not a PDF (content-type {fetched.content_type})"
                result.errors.append({"url": url, "error": reason})
                source.last_error = reason
                continue
            parsed = parser.parse_bytes(fetched.content)
            registered = await ctx.registrar.register_pdf(
                ctx.db, source=source, url=url, content=fetched.content,
                title=parsed.title or title, document_type="regulatory_report",
                period_year=parsed.reference_date.year if parsed.reference_date else None, period_type=None,
                document_scope="reference_listing",
            )
            result.new_documents += int(registered.is_new)
            source.lifecycle_status = "ACTIVE"  # the source produced a downloaded official document
            source.last_error = None
            mat = await materializer.materialize(
                ctx.db, parsed=parsed, document=registered.document, source=source, run_id=ctx.run.id,
                country_codes=ctx.country_codes,
            )
            result.new_entities += mat.entities_created
            result.sources_found += mat.entities_created  # one regulatory listing per new entity
            snapshots.append({
                "url": url, "document_id": registered.document.id, "reference_date": str(parsed.reference_date),
                "layout": parsed.layout, "status": mat.snapshot_status, "members": mat.members,
                "created": mat.entities_created, "matched": mat.entities_matched, "ambiguous": mat.ambiguous,
                "branch_relationships": mat.relationships_created, "self_check_issues": mat.issues,
            })
        current = await refresh_current_snapshot(ctx.db, ctx.universe_code)
        result.details["snapshots"] = snapshots
        result.details["current_reference_date"] = str(current.reference_date) if current else None
        if not any(s["status"] != "AMBIGUOUS" for s in snapshots):
            result.reference_unavailable = True
            result.reference_reason = (
                "no self-consistent official list obtained from this source"
                + (f": {snapshots[0]['self_check_issues'][:3]}" if snapshots else "")
            )
        await ctx.db.flush()
        return result


class BceaoReferenceListStrategy(ReferenceListStrategy):
    code = "bceao_reference_list"
    description = ("BCEAO — communiqué 'Liste des établissements de crédit agréés dans l'UMOA' "
                   "(latest edition found through the official site search)")
    source_short_name = "BCEAO"
    SEARCH_URL = "https://www.bceao.int/fr/search/node?keys=liste+des+%C3%A9tablissements+de+cr%C3%A9dit+agr%C3%A9%C3%A9s"
    COMMUNIQUE_RE = re.compile(
        r"/communique-presse/liste-des-etablissements-de-credit-agrees-dans-lumoa-au-(\d{1,2})-([a-z]+)-(\d{4})"
    )

    async def locate(self, ctx, result) -> list[tuple[str, str]]:
        found: dict[str, tuple[int, int, int]] = {}
        for page in range(3):
            res = await ctx.fetcher.get(f"{self.SEARCH_URL}&page={page}")
            if not res.ok:
                result.errors.append({"url": res.url, "error": res.error})
                continue
            for url, _anchor in extract_links(res.text, res.final_url or res.url):
                m = self.COMMUNIQUE_RE.search(url)
                month = FRENCH_MONTHS.get(normalize_name(m.group(2))) if m else None
                if m and month:
                    found[url.split("?")[0]] = (int(m.group(3)), month, int(m.group(1)))
        if not found:
            return []
        editions = max(1, int(ctx.options.get("reference_editions", 1)))
        out: list[tuple[str, str]] = []
        for page_url, _date in sorted(found.items(), key=lambda kv: kv[1], reverse=True)[:editions]:
            res = await ctx.fetcher.get(page_url)
            if not res.ok or res.redirected_to_homepage:
                result.errors.append({"url": page_url, "error": res.error or "redirected to homepage"})
                continue
            for url, anchor in extract_links(res.text, res.final_url or page_url):
                name = normalize_name(unquote(url.rsplit("/", 1)[-1]))
                if url.lower().endswith(".pdf") and "LISTE DES ETABLISSEMENTS DE CREDIT" in name:
                    out.append((url, anchor or name))
        return list(dict.fromkeys(out))


class CbUmoaReferenceListStrategy(ReferenceListStrategy):
    code = "cb_umoa_reference_list"
    description = ("Commission Bancaire de l'UMOA — consolidated list of credit institutions from the page "
                   "'Établissements assujettis au contrôle de la Commission Bancaire'")
    source_short_name = "CB-UMOA"
    PAGE_URL = "https://www.cb-umoa.org/fr/etablissements-assujettis-au-controle-de-la-commission-bancaire-de-lumoa"

    async def locate(self, ctx, result) -> list[tuple[str, str]]:
        res = await ctx.fetcher.get(self.PAGE_URL)
        if not res.ok or res.redirected_to_homepage:
            result.errors.append({"url": self.PAGE_URL, "error": res.error or "redirected to homepage"})
            return []
        out = []
        for url, anchor in extract_links(res.text, res.final_url or self.PAGE_URL):
            name = normalize_name(unquote(url.rsplit("/", 1)[-1]))
            # Consolidated UMOA list only (per-country files are split views of the same list).
            if url.lower().endswith(".pdf") and "LISTE DES ETABLISSEMENTS DE CREDIT DE L UMOA" in name:
                out.append((url, anchor or name))
        return list(dict.fromkeys(out))
