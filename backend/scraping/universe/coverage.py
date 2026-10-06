"""
Coverage computation (Phase 15) — everything is read from PostgreSQL.

Scope: the CURRENT official snapshot of a universe (most recent self-consistent official list).
Only entities linked from that snapshot's member lines are counted: an entity that is not in
the official universe (demo data, legacy rows) can never raise any coverage figure.

Levels:
  ENTITY      matched official lines / expected count stated by the document (UNKNOWN if not stated)
  SOURCE      regulatory listing | institution-owned official source (website / publications) | market
  DOCUMENT    ≥ 1 downloaded financial document linked to the entity
  DATA        ≥ 1 non-rejected observation on a banking catalogue metric
  VALIDATION  observation counts by status (verified / reviewed / needs_review / extracted / rejected)
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import FINANCIAL_DOCUMENT_LINK_TYPES, UMOA_COUNTRY_CODES
from app.models.country import Country
from app.models.discovery import (
    DiscoveryGap,
    DocumentEntity,
    EntityIdentifier,
    EntitySource,
    ReferenceUniverse,
    ReferenceUniverseMember,
)
from app.models.document import Document
from app.models.entity import Entity
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from app.models.metric_definition import MetricDefinition
from app.models.source import Source

_STATUS_RANK = {"ACTIVE": 5, "VERIFIED": 4, "CANDIDATE": 3, "BLOCKED": 2, "RETIRED": 1}
OBS_STATUSES = ("verified", "reviewed", "needs_review", "extracted", "rejected")


def ratio(num: int, den: int | None) -> float | None:
    if den is None or den == 0:
        return None
    return round(num / den, 4)


@dataclass
class EntityCoverage:
    entity_id: str
    name: str
    country_code: str
    registration_number: str | None
    form: str
    regulatory_listing: bool = False
    website_status: str = "UNKNOWN"  # ACTIVE | VERIFIED | FOUND | BLOCKED | NOT_FOUND | UNKNOWN
    website_url: str | None = None
    own_publications: bool = False
    market_listing: bool = False
    source_count: int = 0
    financial_documents: int = 0
    # Phase 16: a regulatory publication covering many institutions is never the institution's own document.
    regulatory_documents: int = 0
    institution_documents: int = 0
    own_annual_report: bool = False
    observations: dict[str, int] = field(default_factory=dict)
    # Phase 17 — institution-specific matrix
    website_candidates: int = 0  # CANDIDATE websites (found, not verified)
    website_blocked: int = 0
    market_filings: bool = False  # BRVM filings source (official market source)
    parent_name: str | None = None  # parent bank of a branch (official list)
    parent_has_source: bool = False  # the parent has a verified institutional source
    machine_readable_documents: int = 0
    analysed_documents: int = 0  # institution documents already processed by the extractor
    latest_document_year: int | None = None
    institution_document_urls: list[str] = field(default_factory=list)
    ambiguities: list[dict] = field(default_factory=list)  # {"type", "label", "evidence"}
    gaps: list[str] = field(default_factory=list)
    last_attempt_at: str | None = None
    next_attempt_at: str | None = None

    @property
    def official_own_source(self) -> bool:
        return self.website_status in ("ACTIVE", "VERIFIED") or self.own_publications

    @property
    def institutional_source(self) -> bool:
        """Official institution / market source verified or active (website, publications, BRVM)."""
        return self.official_own_source or self.market_listing or self.market_filings

    @property
    def has_financial_document(self) -> bool:
        return self.financial_documents > 0

    @property
    def has_financial_data(self) -> bool:
        return sum(v for k, v in self.observations.items() if k != "rejected") > 0

    @property
    def has_verified_data(self) -> bool:
        return self.observations.get("verified", 0) > 0


@dataclass
class MissingMember:
    member_id: str
    country_code: str
    official_name: str
    registration_number: str | None
    resolution_status: str
    notes: str | None
    candidates: list[dict] | None


@dataclass
class CountryCoverage:
    country_code: str
    expected: int | None
    expected_evidence: str | None
    discovered: int
    matched: int
    status: str
    missing: list[MissingMember] = field(default_factory=list)

    @property
    def entity_ratio(self) -> float | None:
        return ratio(min(self.matched, self.expected), self.expected) if self.expected is not None else None


@dataclass
class CoverageSnapshot:
    universe_code: str
    computed_at: datetime
    reference_available: bool
    reference_status: str | None = None
    reference_title: str | None = None
    reference_date: date | None = None
    reference_source: str | None = None
    reference_url: str | None = None
    reference_document_id: str | None = None
    expected_total: int | None = None
    expected_evidence: str | None = None
    discovered_total: int = 0
    matched_total: int = 0
    countries: dict[str, CountryCoverage] = field(default_factory=dict)
    entities: list[EntityCoverage] = field(default_factory=list)
    observation_status_counts: dict[str, int] = field(default_factory=dict)
    # Phase 16 breakdowns of the observations of the current universe
    scope_class_counts: dict[str, int] = field(default_factory=dict)
    reason_code_counts: dict[str, int] = field(default_factory=dict)
    quality_flag_counts: dict[str, int] = field(default_factory=dict)
    observations_by_document_scope: dict[str, int] = field(default_factory=dict)
    metric_table: list[dict[str, Any]] = field(default_factory=list)
    provenance: dict[str, int] = field(default_factory=dict)
    orphan_institutions: list[dict[str, Any]] = field(default_factory=list)
    snapshots: list[dict[str, Any]] = field(default_factory=list)

    # ------------------------------------------------------------------ headline numbers
    @property
    def entity_ratio(self) -> float | None:
        if self.expected_total is None:
            return None
        return ratio(min(self.matched_total, self.expected_total), self.expected_total)

    def _count(self, predicate) -> int:
        return sum(1 for e in self.entities if predicate(e))

    def level(self, name: str) -> dict[str, Any]:
        n = len(self.entities)
        predicates = {
            "regulatory_source": lambda e: e.regulatory_listing,
            "official_own_source": lambda e: e.official_own_source,
            "website_verified": lambda e: e.website_status in ("ACTIVE", "VERIFIED"),
            "market_listing": lambda e: e.market_listing,
            "financial_document": lambda e: e.has_financial_document,
            "financial_data": lambda e: e.has_financial_data,
            "verified_data": lambda e: e.has_verified_data,
            # Phase 16 — reported separately, never merged
            "regulatory_document": lambda e: e.regulatory_documents > 0,
            "institution_specific_document": lambda e: e.institution_documents > 0,
            "financial_observation": lambda e: e.has_financial_data,
            "financial_validation": lambda e: e.has_verified_data,
            # Phase 17
            "official_source_found": lambda e: e.institutional_source or e.website_candidates > 0
            or e.website_blocked > 0,
            "verified_source": lambda e: e.institutional_source,
            "machine_readable_document": lambda e: e.machine_readable_documents > 0,
            "needs_review_data": lambda e: e.observations.get("needs_review", 0) > 0,
            "reviewed_data": lambda e: e.observations.get("reviewed", 0) > 0,
            "extracted_data": lambda e: e.observations.get("extracted", 0) > 0,
        }
        found = self._count(predicates[name])
        return {"entities": n, "found": found, "missing": n - found, "ratio": ratio(found, n)}

    def summary(self) -> dict[str, Any]:
        """Compact JSON-able summary stored on runs / rounds."""
        return {
            "computed_at": self.computed_at.isoformat(),
            "reference_available": self.reference_available,
            "reference_date": self.reference_date.isoformat() if self.reference_date else None,
            "reference_status": self.reference_status,
            "expected": self.expected_total,
            "discovered": self.discovered_total,
            "matched": self.matched_total,
            "entity_ratio": self.entity_ratio,
            "levels": {k: self.level(k) for k in (
                "regulatory_source", "official_own_source", "website_verified", "market_listing",
                "financial_document", "financial_data", "verified_data", "regulatory_document",
                "institution_specific_document", "financial_observation", "financial_validation",
                "official_source_found", "verified_source", "machine_readable_document", "needs_review_data",
                "reviewed_data", "extracted_data")},
            "observations": dict(self.observation_status_counts),
            "scope_classes": dict(self.scope_class_counts),
            "reason_codes": dict(self.reason_code_counts),
            "quality_flags": dict(self.quality_flag_counts),
            "countries": {
                cc: {"expected": c.expected, "discovered": c.discovered, "matched": c.matched,
                     "ratio": c.entity_ratio, "status": c.status}
                for cc, c in self.countries.items()
            },
        }


async def compute_coverage(db: AsyncSession, universe_code: str) -> CoverageSnapshot:
    now = datetime.now(UTC)
    countries = {c.id: c.code for c in (await db.execute(select(Country))).scalars().all()}
    rows = (
        await db.execute(
            select(ReferenceUniverse).where(
                ReferenceUniverse.universe_code == universe_code, ReferenceUniverse.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    snap = CoverageSnapshot(universe_code=universe_code, computed_at=now, reference_available=False)
    for r in sorted((r for r in rows if r.country_id is None), key=lambda r: (r.reference_date or date.min)):
        src = await db.get(Source, r.reference_source_id) if r.reference_source_id else None
        doc = await db.get(Document, r.reference_document_id) if r.reference_document_id else None
        snap.snapshots.append({
            "reference_date": r.reference_date.isoformat() if r.reference_date else None,
            "source": src.short_name if src else None, "title": doc.title if doc else None,
            "url": doc.url if doc else None, "expected": r.expected_count, "discovered": r.discovered_count,
            "matched": r.matched_count, "status": r.status, "is_current": r.is_current,
            "status_reason": r.status_reason,
        })
    current = [r for r in rows if r.is_current]
    umoa = next((r for r in current if r.country_id is None), None)
    snap.orphan_institutions = await _orphans(db, countries)
    if umoa is None:
        return snap

    src = await db.get(Source, umoa.reference_source_id) if umoa.reference_source_id else None
    doc = await db.get(Document, umoa.reference_document_id) if umoa.reference_document_id else None
    snap.reference_available = True
    snap.reference_status = umoa.status
    snap.reference_title = doc.title if doc else None
    snap.reference_date = umoa.reference_date
    snap.reference_source = src.short_name if src else None
    snap.reference_url = doc.url if doc else None
    snap.reference_document_id = umoa.reference_document_id
    snap.expected_total = umoa.expected_count
    snap.expected_evidence = umoa.expected_count_evidence

    # ------------------------------------------------------------------ entity level
    country_rows = {countries[r.country_id]: r for r in current if r.country_id}
    members = (
        await db.execute(
            select(ReferenceUniverseMember).where(
                ReferenceUniverseMember.universe_id.in_([r.id for r in country_rows.values()]),
                ReferenceUniverseMember.category == "bank",
                ReferenceUniverseMember.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    by_universe = defaultdict(list)
    for m in members:
        by_universe[m.universe_id].append(m)
    for cc in UMOA_COUNTRY_CODES:
        row = country_rows.get(cc)
        if row is None:
            continue
        ms = by_universe[row.id]
        linked = [m for m in ms if m.entity_id and m.resolution_status in ("matched", "created")]
        snap.countries[cc] = CountryCoverage(
            country_code=cc, expected=row.expected_count, expected_evidence=row.expected_count_evidence,
            discovered=len(ms), matched=len(linked), status=row.status,
            missing=[
                MissingMember(m.id, cc, m.official_name, m.registration_number, m.resolution_status,
                              m.resolution_notes, m.candidate_entity_ids)
                for m in ms if m not in linked
            ],
        )
    snap.discovered_total = sum(c.discovered for c in snap.countries.values())
    snap.matched_total = sum(c.matched for c in snap.countries.values())

    linked_members = {m.entity_id: m for m in members if m.entity_id and m.resolution_status in ("matched", "created")}
    entity_ids = list(linked_members)
    if not entity_ids:
        return snap
    entities = {e.id: e for e in (await db.execute(select(Entity).where(Entity.id.in_(entity_ids)))).scalars().all()}
    idents = defaultdict(list)
    for i in (await db.execute(select(EntityIdentifier).where(
            EntityIdentifier.entity_id.in_(entity_ids), EntityIdentifier.deleted_at.is_(None)))).scalars().all():
        idents[i.entity_id].append(i.value)

    cov: dict[str, EntityCoverage] = {}
    for eid, m in linked_members.items():
        e = entities[eid]
        cov[eid] = EntityCoverage(
            entity_id=eid, name=e.canonical_name, country_code=countries.get(e.country_id or "", "?"),
            registration_number=m.registration_number or (idents[eid][0] if idents[eid] else None),
            form=m.member_form,
        )

    # ------------------------------------------------------------------ sources
    links = (await db.execute(select(EntitySource).where(
        EntitySource.entity_id.in_(entity_ids), EntitySource.deleted_at.is_(None)))).scalars().all()
    for link in links:
        c = cov[link.entity_id]
        if link.lifecycle_status in ("ACTIVE", "VERIFIED"):
            c.source_count += 1
        if link.link_role == "regulatory_listing" and link.lifecycle_status in ("ACTIVE", "VERIFIED"):
            c.regulatory_listing = True
        elif link.link_role == "official_website":
            c.website_candidates += int(link.lifecycle_status == "CANDIDATE")
            c.website_blocked += int(link.lifecycle_status == "BLOCKED")
            label = "FOUND" if link.lifecycle_status == "CANDIDATE" else link.lifecycle_status
            current_rank = _STATUS_RANK.get("CANDIDATE" if c.website_status == "FOUND" else c.website_status, 0)
            if _STATUS_RANK.get(link.lifecycle_status, 0) > current_rank:
                c.website_status, c.website_url = label, link.url
        elif link.link_role == "official_publications" and link.lifecycle_status in ("ACTIVE", "VERIFIED"):
            c.own_publications = True
        elif link.link_role == "market_infrastructure" and link.lifecycle_status in ("ACTIVE", "VERIFIED"):
            c.market_listing = True
            if "rapports-societe-cotes" in (link.url or ""):
                c.market_filings = True
    not_found = (await db.execute(select(DiscoveryGap.entity_id).where(
        DiscoveryGap.entity_id.in_(entity_ids), DiscoveryGap.gap_type == "OFFICIAL_WEBSITE",
        DiscoveryGap.status.in_(("NOT_FOUND", "BLOCKED")), DiscoveryGap.deleted_at.is_(None)))).scalars().all()
    for eid in not_found:
        if cov[eid].website_status == "UNKNOWN":
            cov[eid].website_status = "NOT_FOUND"

    # ------------------------------------------------------------------ documents
    doc_links = (await db.execute(
        select(DocumentEntity.entity_id, DocumentEntity.document_id, Document.document_scope)
        .join(Document, Document.id == DocumentEntity.document_id)
        .where(
            DocumentEntity.entity_id.in_(entity_ids),
            DocumentEntity.deleted_at.is_(None),
            DocumentEntity.link_type.in_(FINANCIAL_DOCUMENT_LINK_TYPES),
            Document.download_status == "downloaded",
            Document.deleted_at.is_(None),
        )
    )).all()
    own_docs = (await db.execute(
        select(Document.entity_id, Document.id, Document.document_scope).where(
            Document.entity_id.in_(entity_ids),
            Document.document_type.in_(("annual_report", "financial_statement")),
            Document.download_status == "downloaded",
            Document.deleted_at.is_(None),
        )
    )).all()
    per_entity_docs: dict[str, dict[str, str]] = defaultdict(dict)
    for eid, did, scope in [*doc_links, *own_docs]:
        per_entity_docs[eid][did] = scope
    for eid, docs in per_entity_docs.items():
        cov[eid].financial_documents = len(docs)
        cov[eid].regulatory_documents = sum(1 for sc in docs.values() if sc == "regulatory_aggregate")
        cov[eid].institution_documents = sum(1 for sc in docs.values() if sc == "institution_specific")
        cov[eid].own_annual_report = cov[eid].institution_documents > 0

    inst_docs = (await db.execute(select(Document).where(
        Document.entity_id.in_(entity_ids), Document.document_scope == "institution_specific",
        Document.download_status == "downloaded", Document.deleted_at.is_(None)))).scalars().all()
    for d in inst_docs:
        c = cov[d.entity_id]
        c.machine_readable_documents += int(d.text_layer_status in ("machine_readable", "partially_corrupted"))
        c.analysed_documents += int(d.extracted_at is not None)
        year = d.reporting_year or d.period_year
        if year and (c.latest_document_year is None or year > c.latest_document_year):
            c.latest_document_year = year
        if d.url:
            c.institution_document_urls.append(d.url)

    # ------------------------------------------------------------------ parents of branches
    from app.models.entity_relationship import EntityRelationship

    rels = (await db.execute(select(EntityRelationship).where(
        EntityRelationship.source_entity_id.in_(entity_ids), EntityRelationship.relationship_type == "branch_of",
        EntityRelationship.deleted_at.is_(None)))).scalars().all()
    parent_ids = {r.target_entity_id for r in rels}
    parent_names = {e.id: e.canonical_name for e in (await db.execute(
        select(Entity).where(Entity.id.in_(parent_ids)))).scalars().all()} if parent_ids else {}
    parent_ok = set((await db.execute(select(EntitySource.entity_id).where(
        EntitySource.entity_id.in_(parent_ids), EntitySource.deleted_at.is_(None),
        EntitySource.lifecycle_status.in_(("VERIFIED", "ACTIVE")),
        EntitySource.link_role.in_(("official_website", "official_publications", "market_infrastructure")),
    ))).scalars().all()) if parent_ids else set()
    for r in rels:
        cov[r.source_entity_id].parent_name = parent_names.get(r.target_entity_id)
        cov[r.source_entity_id].parent_has_source = r.target_entity_id in parent_ok
    for eid, m in linked_members.items():
        if m.member_form == "branch" and "parent not resolved" in (m.resolution_notes or ""):
            cov[eid].ambiguities.append({"type": "PARENT_SUBSIDIARY_AMBIGUITY", "label": m.parent_name_raw,
                                         "evidence": m.resolution_notes})

    # ------------------------------------------------------------------ label ambiguities (latest rounds)
    from app.models.discovery import DiscoveryRound

    for code, keys in (("bceao_regulatory_fascicle", ("editions",)), ("brvm_market_listings", None)):
        latest = (await db.execute(select(DiscoveryRound).where(
            DiscoveryRound.strategy_code == code, DiscoveryRound.details.is_not(None))
            .order_by(DiscoveryRound.created_at.desc()).limit(1))).scalar_one_or_none()
        if latest is None:
            continue
        groups = []
        if keys:
            for ed in latest.details.get("editions", []):
                groups += [(a.get("label"), a.get("candidates", []), f"fascicle p.{a.get('pages')}")
                           for a in ed.get("ambiguous", [])]
        else:
            groups += [(u.get("raison_sociale"), u.get("candidates", []), u.get("url"))
                       for u in latest.details.get("finance_issuers_unresolved", [])]
        for label, candidates, where in groups:
            for cand in candidates:
                eid = cand.get("entity_id") if isinstance(cand, dict) else cand
                if eid in cov:
                    historical = isinstance(cand, dict) and "former" in (cand.get("reason") or "")
                    cov[eid].ambiguities.append({
                        "type": "HISTORICAL_NAME_AMBIGUITY" if historical else "ENTITY_AMBIGUOUS",
                        "label": label, "evidence": f"{code}: {where}",
                    })

    # ------------------------------------------------------------------ gap queue per entity
    gap_rows = (await db.execute(select(DiscoveryGap).where(
        DiscoveryGap.entity_id.in_(entity_ids), DiscoveryGap.status != "RESOLVED",
        DiscoveryGap.deleted_at.is_(None)))).scalars().all()
    for g in gap_rows:
        c = cov[g.entity_id]
        c.gaps.append(f"{g.gap_type}:{g.status}")
        if g.last_attempt_at and (c.last_attempt_at is None or g.last_attempt_at.isoformat() > c.last_attempt_at):
            c.last_attempt_at = g.last_attempt_at.isoformat()
        if g.next_attempt_at and (c.next_attempt_at is None or g.next_attempt_at.isoformat() < c.next_attempt_at):
            c.next_attempt_at = g.next_attempt_at.isoformat()

    # ------------------------------------------------------------------ financial data
    inst_to_entity = dict((await db.execute(
        select(Institution.id, Institution.entity_id).where(Institution.entity_id.in_(entity_ids)))).all())
    banking_metrics = select(MetricDefinition.code).where(MetricDefinition.sector == "banking")
    obs = (await db.execute(
        select(FinancialData.entity_id, FinancialData.institution_id, FinancialData.status,
               FinancialData.metric_code, FinancialData.scope_evidence_class, FinancialData.scope_reason_code,
               FinancialData.quality_flags, FinancialData.value_normalized, Document.document_scope,
               Document.url, Document.file_hash, FinancialData.page_number, FinancialData.extraction_method,
               FinancialData.source_location, FinancialData.source_id)
        .join(Document, Document.id == FinancialData.document_id)
        .where(
            FinancialData.deleted_at.is_(None),
            FinancialData.metric_code.in_(banking_metrics),
            or_(FinancialData.entity_id.in_(entity_ids), FinancialData.institution_id.in_(list(inst_to_entity))),
        )
    )).all()
    totals: Counter[str] = Counter()
    classes: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    flags: Counter[str] = Counter()
    doc_scopes: Counter[str] = Counter()
    provenance: Counter[str] = Counter()
    per_metric: dict[str, dict[str, Any]] = defaultdict(lambda: {"entities": set(), "statuses": Counter(),
                                                                  "negative": 0, "zero": 0})
    for (entity_id, institution_id, status, metric, sclass, reason, qflags, value, dscope, url, fhash, page,
         method, location, source_id) in obs:
        eid = entity_id if entity_id in cov else inst_to_entity.get(institution_id)
        if eid in cov:
            cov[eid].observations[status] = cov[eid].observations.get(status, 0) + 1
            totals[status] += 1
            classes[sclass or "none"] += 1
            reasons[reason or "none"] += 1
            doc_scopes[dscope or "unknown"] += 1
            for f in qflags or []:
                flags[f.get("code", "?")] += 1
            pm = per_metric[metric]
            pm["entities"].add(eid)
            pm["statuses"][status] += 1
            if value is not None and value < 0:
                pm["negative"] += 1
            if value is not None and value == 0:
                pm["zero"] += 1
            provenance["observations"] += 1
            complete = all((source_id, url, fhash, page, method, location))
            provenance["complete"] += int(complete)
            for key, present in (("missing_url", url), ("missing_hash", fhash), ("missing_page", page),
                                 ("missing_method", method), ("missing_location", location)):
                provenance[key] += int(not present)
    snap.observation_status_counts = {s: totals.get(s, 0) for s in OBS_STATUSES}
    snap.scope_class_counts = dict(sorted(classes.items()))
    snap.reason_code_counts = dict(sorted(reasons.items()))
    snap.quality_flag_counts = dict(sorted(flags.items()))
    snap.observations_by_document_scope = dict(sorted(doc_scopes.items()))
    snap.provenance = dict(provenance)
    catalogue = (await db.execute(select(MetricDefinition.code).where(MetricDefinition.sector == "banking")
                                  .order_by(MetricDefinition.code))).scalars().all()
    for code in catalogue:
        pm = per_metric.get(code)
        statuses = pm["statuses"] if pm else Counter()
        snap.metric_table.append({
            "metric": code, "entities_with": len(pm["entities"]) if pm else 0,
            "entities_without": len(cov) - (len(pm["entities"]) if pm else 0),
            **{s: statuses.get(s, 0) for s in OBS_STATUSES},
            "negative": pm["negative"] if pm else 0, "zero": pm["zero"] if pm else 0,
        })
    snap.entities = sorted(cov.values(), key=lambda c: (c.country_code, c.name))
    return snap


async def _orphans(db: AsyncSession, countries: dict[str, str]) -> list[dict[str, Any]]:
    """Financial institutions present in the Entity Hub but absent from every official snapshot."""
    member_entities = select(ReferenceUniverseMember.entity_id).where(
        ReferenceUniverseMember.entity_id.is_not(None), ReferenceUniverseMember.deleted_at.is_(None)
    )
    rows = (await db.execute(
        select(Entity).where(
            Entity.entity_class == "financial_institution",
            Entity.deleted_at.is_(None),
            Entity.id.not_in(member_entities),
        )
    )).scalars().all()
    return [
        {"entity_id": e.id, "name": e.canonical_name, "entity_type": e.entity_type,
         "country": countries.get(e.country_id or "", None)}
        for e in sorted(rows, key=lambda e: e.canonical_name)
    ]


def coverage_to_dict(snap: CoverageSnapshot) -> dict[str, Any]:
    data = snap.summary()
    data["entities"] = [asdict(e) for e in snap.entities]
    return data
