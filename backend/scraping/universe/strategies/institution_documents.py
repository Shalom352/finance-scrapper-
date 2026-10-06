"""
Phase 17 — institution-specific documents: BRVM filings discovery and extraction.

  brvm_issuer_filings              BRVM "rapports-societe-cotes" pages (official market source):
                                   issuer page → filings → PDF → entity attribution by EVIDENCE
                                   (the document text names the bank AND its country, or the page
                                   name carries an explicit UMOA country with a unique strong match).
                                   Unattributed issuers / documents are reported, never guessed.
  institution_document_extraction  every institution-specific document not yet analysed:
                                   text-layer gate → statements parser → observations with the
                                   Phase-16 scope guard (needs_review unless A/B) → provenance.
                                   Scanned / corrupted documents yield NO observation.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.models.discovery import DocumentEntity
from app.models.document import Document
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.pipeline import PROTECTED_STATUSES, scope_guard
from scraping.quality.checks import (
    cross_statement_flags,
    has_blocking_flag,
    merge_flags,
    value_flags,
)
from scraping.quality.scope import DocumentScopeContext
from scraping.quality.text_layer import assess_pdf_bytes
from scraping.universe.http import extract_links, html_to_text
from scraping.universe.institution_statements import InstitutionStatementParser
from scraping.universe.normalize import country_codes_in, normalize_name
from scraping.universe.strategies.base import DiscoveryContext, DiscoveryStrategy, StrategyResult
from scraping.universe.strategies.market_and_web import upsert_entity_source
from scraping.universe.strategies.reference_lists import get_source

BRVM = "https://www.brvm.org"
_REPORT_LINK = re.compile(r'<a href="(/fr/rapports-societe-cotes/[a-z0-9-]+)"[^>]*>([^<]+)</a>')
# Annual filings only (the extractor does not read interim statements).
_ANNUAL_FILING = re.compile(r"(etats?_financiers|rapport_annuel|rapport_des_commissaires_aux_comptes_sur_les_etats)",
                            re.IGNORECASE)
_INTERIM_FILING = re.compile(r"(semestre|trimestre|semestriel|trimestriel)", re.IGNORECASE)


def utcnow() -> datetime:
    return datetime.now(UTC)


def _year_in(text: str) -> int | None:
    years = {int(y) for y in re.findall(r"(?<!\d)(20\d{2})(?!\d)", text)}
    return years.pop() if len(years) == 1 else None


# ====================================================================== BRVM filings
class BrvmIssuerFilingsStrategy(DiscoveryStrategy):
    code = "brvm_issuer_filings"
    description = ("BRVM — listed issuers' filings pages (/fr/rapports-societe-cotes/<issuer>): annual financial "
                   "statements / auditors' reports, attributed to a bank only on documentary evidence")
    priority = 4
    handles = frozenset({"SOURCE_NOT_FOUND", "DOCUMENT_NOT_FOUND"})
    max_filings_per_issuer = 3

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        source = await get_source(ctx, "BRVM")
        if source is None:
            result.errors.append({"error": "BRVM source not registered"})
            return result
        issuers: dict[str, str] = {}
        page_no = 0
        while page_no < 30:  # every listing page (stops when a page brings nothing new)
            res = await ctx.fetcher.get(f"{BRVM}/fr/rapports-societes-cotees?field_secteur_emeteur_tid=All&page={page_no}")
            if not res.ok:
                result.errors.append({"url": res.url, "error": res.error})
                break
            found = dict(_REPORT_LINK.findall(res.text))
            new = {k: v for k, v in found.items() if k not in issuers}
            if not new:
                break
            issuers.update(new)
            page_no += 1
        result.details["listing_pages"] = page_no
        result.details["issuers_listed"] = len(issuers)
        attributed, unattributed, no_annual = [], [], []
        for path, raw_name in sorted(issuers.items()):
            name = html_to_text(raw_name)
            page = await ctx.fetcher.get(BRVM + path)
            if not page.ok:
                result.errors.append({"url": BRVM + path, "error": page.error})
                continue
            pdfs = [u for u, _a in extract_links(page.text, page.final_url or BRVM + path) if u.lower().endswith(".pdf")]
            annual = [u for u in pdfs if _ANNUAL_FILING.search(u) and not _INTERIM_FILING.search(u)]
            if not annual:
                no_annual.append(name)
                continue
            # Newest first (file names start with the BRVM publication date YYYYMMDD).
            annual = sorted(set(annual), key=lambda u: u.rsplit("/", 1)[-1], reverse=True)[: self.max_filings_per_issuer]
            for url in annual:
                outcome = await self._attribute(ctx, name, url, BRVM + path, source, result)
                (attributed if outcome.get("entity_id") else unattributed).append(outcome)
        result.details["attributed"] = attributed
        result.details["unattributed"] = unattributed
        result.details["issuers_without_annual_filings"] = len(no_annual)
        return result

    async def _attribute(self, ctx, issuer_name: str, url: str, issuer_page: str, source,
                         result: StrategyResult) -> dict:
        fetched = await ctx.fetcher.get(url)
        if not fetched.ok or not fetched.is_pdf:
            return {"issuer": issuer_name, "url": url, "reason": fetched.error or "not a PDF"}
        layer = assess_pdf_bytes(fetched.content)
        page1 = ""
        if layer.status != "not_machine_readable":
            import pymupdf

            with pymupdf.open(stream=fetched.content, filetype="pdf") as pdf:
                page1 = " ".join(pdf[i].get_text() for i in range(min(3, pdf.page_count)))
        entity_id, evidence = self._resolve(ctx, issuer_name, page1)
        if entity_id is None:
            # Only financial-services issuers matter; a non-bank issuer simply yields no candidate.
            return {"issuer": issuer_name, "url": url, "reason": evidence, "text_layer": layer.status}
        registered = await ctx.registrar.register_pdf(
            ctx.db, source=source, url=url, content=fetched.content,
            title=url.rsplit("/", 1)[-1].replace("_", " ")[:500], document_type="financial_statement",
            period_year=_year_in(url.rsplit("/", 1)[-1].replace("_-_", " ")), entity_id=entity_id,
            document_scope="institution_specific",
        )
        doc = registered.document
        doc.text_layer_status = layer.status
        doc.file_format = "pdf"
        result.new_documents += int(registered.is_new)
        link = (await ctx.db.execute(select(DocumentEntity).where(
            DocumentEntity.document_id == doc.id, DocumentEntity.entity_id == entity_id,
            DocumentEntity.link_type == "annual_report", DocumentEntity.deleted_at.is_(None)))).scalars().first()
        if link is None:
            ctx.db.add(DocumentEntity(document_id=doc.id, entity_id=entity_id, link_type="annual_report",
                                      label_in_document=issuer_name[:500], method=self.code, evidence=evidence))
            result.new_document_links += 1
        created = await upsert_entity_source(
            ctx, entity_id=entity_id, role="market_infrastructure", url=issuer_page, source_id=source.id,
            status="VERIFIED", method=self.code,
            evidence=f"BRVM filings of '{issuer_name}': {evidence}", http_status=200, document_id=doc.id,
        )
        result.sources_found += int(created)
        await ctx.db.flush()
        return {"issuer": issuer_name, "url": url, "entity_id": entity_id, "evidence": evidence,
                "text_layer": layer.status, "document_id": doc.id}

    def _resolve(self, ctx, issuer_name: str, text: str) -> tuple[str | None, str]:
        """Entity attribution on evidence only. Returns (entity_id, evidence or reason)."""
        resolver = ctx.resolver
        # 1. explicit UMOA country in the BRVM page name + unique strong match in that country
        named = country_codes_in(issuer_name)
        if len(named) == 1:
            (cc,) = tuple(named)
            r = resolver.resolve_label(country_code=cc, label=issuer_name)
            if r.status == "matched":
                return r.entity_id, f"page name '{issuer_name}' (country {cc}) → {r.method}"
        # 2. the document text names exactly one bank of the universe together with its country
        if text:
            norm = f" {normalize_name(text)} "
            hits = []
            for ent in resolver.entities.values():
                if not ent.country_code or ent.is_branch:
                    continue
                names = [k for k in ent.name_keys if len(k) >= 8] + [k for k in ent.acronym_keys if len(k) >= 4]
                if any(f" {k} " in norm for k in names) and ent.country_code in country_codes_in(text):
                    hits.append(ent)
            if len(hits) == 1:
                return hits[0].id, (f"document text names '{hits[0].canonical_name}' and its country "
                                    f"{hits[0].country_code}")
            if len(hits) > 1:
                return None, "document text names several banks: " + ", ".join(sorted(h.canonical_name for h in hits)[:4])
        return None, "no documentary evidence linking the issuer to one bank of the universe"


# ====================================================================== extraction
class InstitutionDocumentExtractionStrategy(DiscoveryStrategy):
    code = "institution_document_extraction"
    description = ("Institution-specific documents: text-layer gate, comparative statements parser (catalogue "
                   "metrics only), Phase-16 scope guard; scanned / corrupted pages yield no observation")
    priority = 2
    handles = frozenset({"DOCUMENT_FOUND_UNVERIFIED", "FINANCIAL_DATA"})

    async def run(self, ctx: DiscoveryContext, targets) -> StrategyResult:
        result = StrategyResult(targets=len(targets))
        docs = (await ctx.db.execute(select(Document).where(
            Document.document_scope == "institution_specific", Document.entity_id.is_not(None),
            Document.download_status == "downloaded", Document.extracted_at.is_(None),
            Document.deleted_at.is_(None)))).scalars().all()
        report = []
        for doc in docs:
            content = ctx.registrar.read_bytes(doc)
            if content is None:
                report.append({"document_id": doc.id, "status": "file missing from storage"})
                continue
            layer = assess_pdf_bytes(content)
            doc.text_layer_status = layer.status
            doc.file_format = doc.file_format or "pdf"
            parsed = InstitutionStatementParser().parse_bytes(content, doc.title or "")
            created = await self._store(ctx, doc, content, parsed)
            years = sorted({v.year for v in parsed.values})
            doc.reporting_year = _year_in(doc.title or "") or (years[-1] if years else None)
            doc.extracted_at = utcnow()
            doc.extraction_status = "extracted" if parsed.values else "skipped"
            doc.error_message = None if parsed.values else (
                "no catalogue line read: " + ("; ".join(f"p.{k}: {v}" for k, v in parsed.skipped_pages.items())
                                               or "no comparative statement page"))[:2000]
            result.new_observations += created
            if parsed.values:
                await self._activate_sources(ctx, doc)
            report.append({"document_id": doc.id, "text_layer": layer.status, "statement_pages": parsed.statement_pages,
                           "skipped_pages": parsed.skipped_pages, "values": len(parsed.values), "created": created})
        result.details["documents"] = report
        await ctx.db.flush()
        return result

    @staticmethod
    async def _activate_sources(ctx, doc: Document) -> None:
        """E2E proof source → document → download → parsing → provenance: the sources that led to this
        parsed document become ACTIVE (the website of the same domain included)."""
        from urllib.parse import urlparse

        from app.models.discovery import EntitySource

        links = (await ctx.db.execute(select(EntitySource).where(
            EntitySource.entity_id == doc.entity_id, EntitySource.deleted_at.is_(None)))).scalars().all()
        host = urlparse(doc.url or "").netloc.lower()
        for link in links:
            same_document = link.evidence_document_id == doc.id
            same_site = link.link_role == "official_website" and host and urlparse(link.url or "").netloc.lower() == host
            if (same_document or same_site) and link.lifecycle_status in ("VERIFIED", "ACTIVE"):
                link.lifecycle_status = "ACTIVE"
        await ctx.db.flush()

    async def _store(self, ctx, doc: Document, content: bytes, parsed) -> int:
        entity_id = doc.entity_id
        institution_id = (await ctx.db.execute(
            select(Institution.id).where(Institution.entity_id == entity_id))).scalar_one_or_none()
        scope_ctx = DocumentScopeContext.from_pdf_bytes(content)
        created = 0
        rows: list[FinancialData] = []
        for v in parsed.values:
            unit_flag = [] if v.unit and v.currency else [{
                "code": "unit_or_currency_not_stated",
                "detail": f"p.{v.page_number}: the statement does not state its unit / currency",
            }]
            assessment = scope_ctx.assess(v.page_number)
            status, notes = scope_guard(
                "extracted", f"institution document p.{v.page_number}: '{v.line_label}' col. {v.year}",
                assessment, unit_flag,
            )
            existing = (await ctx.db.execute(select(FinancialData).where(
                FinancialData.entity_id == entity_id, FinancialData.document_id == doc.id,
                FinancialData.metric_code == v.metric_code, FinancialData.period_year == v.year,
                FinancialData.period_type == "annual", FinancialData.observation_level == "entity",
                FinancialData.deleted_at.is_(None)))).scalars().first()
            if existing is not None:
                if existing.status not in PROTECTED_STATUSES:
                    rows.append(existing)
                continue  # an existing row of the same document keeps its value
            row = FinancialData(
                institution_id=institution_id, entity_id=entity_id, observation_level="entity",
                consolidation_scope=assessment.scope if assessment.promotable else "individual",
                scope=assessment.scope if assessment.promotable else "individual",
                source_id=doc.source_id, document_id=doc.id, metric_code=v.metric_code, period_type="annual",
                period_year=v.year, period_label=str(v.year), value_original=v.raw,
                unit_original=v.unit, currency_original=v.currency,
                # Normalized only when the document states its unit (DATA MISSING > DATA WRONG).
                value_normalized=(v.value * v.multiplier) if v.multiplier is not None else None,
                unit_normalized="absolute" if v.multiplier is not None else None,
                currency_normalized=v.currency, page_number=v.page_number, extraction_method="pdf_text",
                confidence_score=Decimal("0.900"), status=status, notes=notes, extracted_at=utcnow(),
                scope_evidence_class=assessment.evidence_class, scope_reason_code=assessment.reason_code,
                scope_evidence=assessment.evidence, quality_flags=unit_flag or None,
                source_location=f"p.{v.page_number} · {v.line_label} · col. {v.year}"[:500],
            )
            ctx.db.add(row)
            rows.append(row)
            created += 1
        await ctx.db.flush()
        await self._flags(ctx, entity_id, doc, rows, parsed)
        return created

    async def _flags(self, ctx, entity_id, doc, rows, parsed) -> None:
        checks = {year: value for (name, year), (value, _mult) in parsed.check_values.items()
                  if name == "balance_sheet_result"}
        found: dict[str, list[dict]] = defaultdict(list)
        for mapping in (value_flags(rows), cross_statement_flags(rows, checks)):
            for rid, flags in mapping.items():
                found[rid].extend(flags)
        # Same entity / metric / year read in another institution document with the same stated unit.
        others = (await ctx.db.execute(select(FinancialData).join(Document, Document.id == FinancialData.document_id)
                  .where(FinancialData.entity_id == entity_id, FinancialData.document_id != doc.id,
                         Document.document_scope == "institution_specific",
                         FinancialData.deleted_at.is_(None)))).scalars().all()
        index = defaultdict(list)
        for o in others:
            index[(o.metric_code, o.period_year, o.unit_original)].append(o)
        for r in rows:
            for o in index.get((r.metric_code, r.period_year, r.unit_original), []):
                if o.value_original.replace(" ", "") != r.value_original.replace(" ", ""):
                    detail = f"{r.metric_code} {r.period_year}: {r.value_original} vs {o.value_original} (other document)"
                    found[r.id].append({"code": "cross_document_mismatch", "detail": detail})
                    found[o.id].append({"code": "cross_document_mismatch", "detail": detail})
        for rid, flags in found.items():
            row = next((r for r in rows if r.id == rid), None) or await ctx.db.get(FinancialData, rid)
            if row is None or row.status in PROTECTED_STATUSES:
                continue
            row.quality_flags = merge_flags(row.quality_flags, flags)
            if row.status == "extracted" and has_blocking_flag(row.quality_flags):
                row.status = "needs_review"
        await ctx.db.flush()

