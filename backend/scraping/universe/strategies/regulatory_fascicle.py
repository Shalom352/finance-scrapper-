"""
Round 3 — BCEAO regulatory publication "Bilans et comptes de résultat des banques et
établissements financiers de l'UMOA" (per-institution financial statements).

  1. find the editions through the official BCEAO site search;
  2. download the most recent edition(s) (content-addressed storage);
  3. group the per-institution pages by (country, code) and resolve them to entities of the
     official universe — a group is linked only when its labels resolve to ONE entity;
  4. link document ↔ entity (financial_statement, page range);
  5. extract the catalogue metrics printed 1:1 (see scraping.universe.fascicle) as
     financial_data with the Phase-13 scope guard: status needs_review + "scope not detected".
     Reviewed / verified / rejected rows are never touched.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import unquote

from sqlalchemy import select

from app.constants.discovery import LINK_ROLE_PRIORITY
from app.constants.quality import FASCICLE_CONVENTION_REASON
from app.models.discovery import DocumentEntity, EntitySource
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.pipeline import PROTECTED_STATUSES, scope_guard
from scraping.quality.checks import (
    cross_edition_flags,
    cross_statement_flags,
    has_blocking_flag,
    merge_flags,
    value_flags,
)
from scraping.quality.scope import DocumentScopeContext, ScopeAssessment
from scraping.universe.fascicle import FasciclePage, FascicleParser
from scraping.universe.http import extract_links
from scraping.universe.normalize import normalize_name
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult
from scraping.universe.strategies.reference_lists import get_source

MILLION = Decimal(1_000_000)
FASCICLE_CONVENTION_EVIDENCE = (
    "BCEAO fascicle: one statement page per licensed credit institution; the document does not "
    "state individual / consolidated"
)
# Used when the document text is not available to the caller (documented convention only → C).
CONVENTION_ASSESSMENT = ScopeAssessment("C", FASCICLE_CONVENTION_REASON, evidence=FASCICLE_CONVENTION_EVIDENCE)


def utcnow() -> datetime:
    return datetime.now(UTC)


class BceaoFascicleStrategy(DiscoveryStrategy):
    code = "bceao_regulatory_fascicle"
    description = ("BCEAO — fascicle 'Bilans et comptes de résultat des banques et établissements financiers "
                   "de l'UMOA' (per-institution statements, regulatory source)")
    priority = 1
    handles = frozenset({"FINANCIAL_DOCUMENT", "FINANCIAL_DATA"})
    SEARCH_URL = ("https://www.bceao.int/fr/search/node?keys=bilans+et+comptes+de+r%C3%A9sultats+des+banques"
                  "+et+%C3%A9tablissements+financiers")
    EDITION_RE = re.compile(r"/publications/bilans-et-comptes-de-resultats?-des-banques-et-etablissements-financiers"
                            r"[a-z-]*?-(\d{4})(?:-\d+)?$")

    async def locate(self, ctx: DiscoveryContext, result: StrategyResult) -> list[tuple[int, str]]:
        editions: dict[int, str] = {}
        for page in range(3):
            res = await ctx.fetcher.get(f"{self.SEARCH_URL}&page={page}")
            if not res.ok:
                result.errors.append({"url": res.url, "error": res.error})
                continue
            for url, _anchor in extract_links(res.text, res.final_url or res.url):
                m = self.EDITION_RE.search(url.split("?")[0])
                if m:
                    editions.setdefault(int(m.group(1)), url.split("?")[0])
        result.details["editions_found"] = {str(k): v for k, v in sorted(editions.items())}
        wanted = max(1, int(ctx.options.get("fascicle_editions", 1)))
        return sorted(editions.items(), reverse=True)[:wanted]

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        source = await get_source(ctx, "BCEAO")
        if source is None:
            result.errors.append({"error": "BCEAO source not registered"})
            return result
        editions = await self.locate(ctx, result)
        if not editions:
            result.errors.append({"error": "no fascicle edition found through the BCEAO site search"})
            return result
        report: list[dict] = []
        for year, page_url in editions:
            page = await ctx.fetcher.get(page_url)
            if not page.ok or page.redirected_to_homepage:
                result.errors.append({"url": page_url, "error": page.error or "redirected to homepage"})
                continue
            pdfs = [u for u, _a in extract_links(page.text, page.final_url or page_url)
                    if u.lower().endswith(".pdf") and "BILAN" in normalize_name(unquote(u.rsplit("/", 1)[-1]))]
            if not pdfs:
                result.errors.append({"url": page_url, "error": "no fascicle PDF on the publication page"})
                continue
            fetched = await ctx.fetcher.get(pdfs[0])
            if not fetched.ok or not fetched.is_pdf:
                result.errors.append({"url": pdfs[0], "error": fetched.error or "not a PDF"})
                continue
            registered = await ctx.registrar.register_pdf(
                ctx.db, source=source, url=pdfs[0], content=fetched.content,
                title=f"Bilans et comptes de résultat des banques et établissements financiers de l'UMOA {year}",
                document_type="financial_statement", period_year=year, period_type="annual",
                document_scope="regulatory_aggregate",
            )
            result.new_documents += int(registered.is_new)
            report.append(await self._process(ctx, registered.document, fetched.content, source, result))
        result.details["editions"] = report
        await ctx.db.flush()
        return result

    # ------------------------------------------------------------------ one edition
    async def _process(self, ctx, document, content: bytes, source, result: StrategyResult) -> dict:
        parsed = FascicleParser().parse_bytes(content)
        # Documentary scope evidence; the convention only applies when the pages say nothing (→ C).
        scope_ctx = DocumentScopeContext.from_pdf_bytes(
            content, convention_reason=FASCICLE_CONVENTION_REASON, convention_evidence=FASCICLE_CONVENTION_EVIDENCE)
        groups: dict[tuple[str, str], list[FasciclePage]] = defaultdict(list)
        for p in parsed.pages:
            if p.country_code in ctx.country_codes:
                groups[(p.country_code, normalize_name(p.code))].append(p)

        linked, unresolved, ambiguous = [], [], []
        for (cc, _code), pages in sorted(groups.items()):
            labels = sorted({p.label for p in pages if p.label})
            outcomes = [ctx.resolver.resolve_label(country_code=cc, label=lbl, code=pages[0].code) for lbl in labels]
            matched = {o.entity_id for o in outcomes if o.status == "matched"}
            label_text = " / ".join(labels) or pages[0].code
            consistent = len(matched) == 1 and all(
                o.status == "matched" or (
                    o.status == "ambiguous" and [c["entity_id"] for c in o.candidates] == list(matched)
                )
                for o in outcomes
            )
            if consistent:
                entity_id = next(iter(matched))
                method = next(o.method for o in outcomes if o.status == "matched")
                result.new_document_links += await self._link(ctx, document, entity_id, pages, label_text, method)
                result.new_observations += await self._store_values(ctx, document, source, entity_id, pages,
                                                                    scope_ctx)
                await self._regulatory_publication_source(ctx, entity_id, source, document, pages)
                linked.append({"country": cc, "label": label_text, "entity_id": entity_id, "method": method,
                               "pages": [p.page_number for p in pages]})
            elif matched or any(o.status == "ambiguous" for o in outcomes):
                ambiguous.append({"country": cc, "label": label_text, "pages": [p.page_number for p in pages],
                                  "candidates": [c for o in outcomes for c in o.candidates] or sorted(matched)})
            else:
                unresolved.append({"country": cc, "label": label_text, "pages": [p.page_number for p in pages]})
        return {
            "document_id": document.id, "url": document.url, "institution_pages": len(parsed.pages),
            "aggregate_pages": parsed.aggregate_pages, "institutions_in_document": len(groups),
            "linked": linked, "ambiguous": ambiguous,
            # Not in the bank universe (financial establishments, closed banks) or name not resolvable.
            "unresolved": unresolved,
        }

    async def _link(self, ctx, document, entity_id, pages, label, method) -> int:
        existing = (await ctx.db.execute(select(DocumentEntity).where(
            DocumentEntity.document_id == document.id, DocumentEntity.entity_id == entity_id,
            DocumentEntity.link_type == "financial_statement", DocumentEntity.deleted_at.is_(None)))).scalars().first()
        numbers = sorted(p.page_number for p in pages)
        if existing is not None:
            return 0
        ctx.db.add(DocumentEntity(
            document_id=document.id, entity_id=entity_id, link_type="financial_statement",
            page_from=numbers[0], page_to=numbers[-1], label_in_document=label[:500], method=method,
            evidence=f"pages {numbers}",
        ))
        await ctx.db.flush()
        return 1

    async def _regulatory_publication_source(self, ctx, entity_id, source, document, pages) -> None:
        """The regulator publishes this entity's statements: a regulatory source for the entity (ACTIVE)."""
        existing = (await ctx.db.execute(select(EntitySource).where(
            EntitySource.entity_id == entity_id, EntitySource.link_role == "regulatory_listing",
            EntitySource.source_id == source.id, EntitySource.deleted_at.is_(None)))).scalars().first()
        if existing is None:
            ctx.db.add(EntitySource(
                entity_id=entity_id, source_id=source.id, url=document.url, link_role="regulatory_listing",
                priority=LINK_ROLE_PRIORITY["regulatory_listing"], lifecycle_status="ACTIVE",
                discovery_method=self.code, discovery_run_id=ctx.run.id, evidence_document_id=document.id,
                evidence_page=min(p.page_number for p in pages), verified_at=utcnow(), last_checked_at=utcnow(),
                last_http_status=200,
                verification_evidence="per-institution statements published by the BCEAO",
            ))
            await ctx.db.flush()

    async def _store_values(self, ctx, document, source, entity_id, pages, scope_ctx=None) -> int:
        """Store the printed values. Existing rows of this (content-addressed) document keep their
        values: only scope evidence, location and quality flags are (re)written; protected statuses
        (reviewed / verified / rejected) are never touched."""
        institution_id = (await ctx.db.execute(
            select(Institution.id).where(Institution.entity_id == entity_id))).scalar_one_or_none()
        created = 0
        touched: list[FinancialData] = []
        for page in pages:
            assessment = scope_ctx.assess(page.page_number) if scope_ctx is not None else CONVENTION_ASSESSMENT
            for v in page.values:
                existing = (await ctx.db.execute(select(FinancialData).where(
                    FinancialData.entity_id == entity_id, FinancialData.document_id == document.id,
                    FinancialData.metric_code == v.metric_code, FinancialData.period_year == v.year,
                    FinancialData.period_type == "annual", FinancialData.observation_level == "entity",
                    FinancialData.deleted_at.is_(None)))).scalars().first()
                status, notes = scope_guard(
                    "extracted",
                    f"BCEAO fascicle p.{page.page_number}: '{v.line_label}' ({page.label}); millions de francs CFA",
                    assessment,
                )
                evidence = dict(
                    scope_evidence_class=assessment.evidence_class, scope_reason_code=assessment.reason_code,
                    scope_evidence=assessment.evidence,
                    source_location=f"p.{page.page_number} · {v.line_label} · col. {v.year}"[:500],
                )
                if existing is not None:
                    if existing.status in PROTECTED_STATUSES:
                        continue  # a human decision is never overwritten
                    for k, val in evidence.items():
                        setattr(existing, k, val)
                    if existing.status != status:
                        existing.status, existing.notes = status, notes
                    touched.append(existing)
                    continue
                row = FinancialData(
                    institution_id=institution_id, entity_id=entity_id, observation_level="entity",
                    consolidation_scope="individual", scope="individual", source_id=source.id,
                    document_id=document.id, metric_code=v.metric_code, period_type="annual",
                    period_year=v.year, period_label=str(v.year), status=status, notes=notes,
                    extracted_at=utcnow(), value_original=v.raw, unit_original="millions",
                    currency_original="XOF", value_normalized=v.value_millions * MILLION,
                    unit_normalized="absolute", currency_normalized="XOF", page_number=page.page_number,
                    extraction_method="pdf_text", confidence_score=Decimal("0.900"), **evidence,
                )
                ctx.db.add(row)
                touched.append(row)
                created += 1
        await ctx.db.flush()
        await self._apply_quality_flags(ctx, entity_id, touched, pages)
        return created

    async def _apply_quality_flags(self, ctx, entity_id, rows: list[FinancialData], pages) -> None:
        """Informative flags; never a value change. A blocking flag only holds back an automatic 'extracted'."""
        checks: dict[int, Decimal] = {}
        for page in pages:
            for (name, year), value in page.check_values.items():
                if name == "balance_sheet_result":
                    checks[year] = value
        found: dict[str, list[dict]] = defaultdict(list)
        for mapping in (value_flags(rows), cross_statement_flags(rows, checks),
                        await cross_edition_flags(ctx.db, entity_id)):
            for row_id, flags in mapping.items():
                found[row_id].extend(flags)
        by_id = {r.id: r for r in rows}
        for row_id, flags in found.items():
            row = by_id.get(row_id) or await ctx.db.get(FinancialData, row_id)
            if row is None:
                continue
            row.quality_flags = merge_flags(row.quality_flags, flags)
            if row.status == "extracted" and has_blocking_flag(row.quality_flags):
                row.status = "needs_review"
        await ctx.db.flush()
