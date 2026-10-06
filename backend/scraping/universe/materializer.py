"""
Materialization of an official reference list into the Entity Hub (Phase 15).

For one parsed official list (a dated snapshot) it creates / updates, idempotently:
  - reference_universes      : one UMOA row + one row per country, expected counts from the document;
  - reference_universe_members : one row per bank line, with its resolution;
  - entities + institutions  : only for lines of the official list (never invented);
  - entity_identifiers       : registration numbers read in the document;
  - entity_names             : official / acronym / former names (history, never overwritten);
  - entity_sources           : regulatory_listing link (ACTIVE: the source produced the entity);
  - document_entities        : reference_listing link to the list document and page;
  - entity_relationships     : branch_of, only when the parent resolves unambiguously.

Ambiguous lines are NOT linked and NOT created: they stay for human review.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import LINK_ROLE_PRIORITY, UMOA_COUNTRY_CODES
from app.models.country import Country
from app.models.discovery import (
    DocumentEntity,
    EntityIdentifier,
    EntityName,
    EntitySource,
    ReferenceUniverse,
    ReferenceUniverseMember,
)
from app.models.document import Document
from app.models.entity import Entity
from app.models.entity_relationship import EntityRelationship
from app.models.institution import Institution
from app.models.source import Source
from scraping.universe.normalize import name_key, normalize_name
from scraping.universe.reference_list import ParsedMember, ParsedReferenceList
from scraping.universe.resolution import EntityResolver, IndexedEntity, Resolution


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass
class MaterializationResult:
    universe_ids: dict[str, str] = field(default_factory=dict)  # cc | "UMOA" → id
    members: int = 0
    entities_created: int = 0
    entities_matched: int = 0
    ambiguous: int = 0
    relationships_created: int = 0
    names_added: int = 0
    snapshot_status: str = "UNKNOWN"
    issues: list[str] = field(default_factory=list)


class UniverseMaterializer:
    def __init__(self, resolver: EntityResolver, universe_code: str) -> None:
        self.resolver = resolver
        self.universe_code = universe_code

    # ================================================================== entry point
    async def materialize(
        self,
        db: AsyncSession,
        *,
        parsed: ParsedReferenceList,
        document: Document,
        source: Source,
        run_id: str | None,
        country_codes: tuple[str, ...] = UMOA_COUNTRY_CODES,
    ) -> MaterializationResult:
        result = MaterializationResult()
        issues = parsed.self_check(UMOA_COUNTRY_CODES)
        result.issues = issues
        countries = {c.code: c for c in (await db.execute(select(Country))).scalars().all()}
        now = utcnow()

        # ---------------------------------------------------------- universe rows (snapshot)
        umoa = await self._universe_row(db, document, None)
        total_expected, total_evidence = parsed.expected_banks_total(UMOA_COUNTRY_CODES)
        self._fill_universe(umoa, parsed, source, document, total_expected, total_evidence, now)
        umoa.self_check = {"issues": issues, "layout": parsed.layout, "title": parsed.title,
                           "reference_date_text": parsed.reference_date_text}
        result.universe_ids["UMOA"] = umoa.id
        rows: dict[str, ReferenceUniverse] = {}
        for cc in UMOA_COUNTRY_CODES:
            row = await self._universe_row(db, document, countries[cc].id)
            expected, evidence = parsed.expected_banks(cc)
            self._fill_universe(row, parsed, source, document, expected, evidence, now)
            country = parsed.countries.get(cc)
            row.history_events = country.history if country else None
            row.self_check = {"issues": [i for i in issues if i.startswith(f"{cc}:") or i.startswith(f"{cc} ")]}
            rows[cc] = row
            result.universe_ids[cc] = row.id
        await db.flush()

        if issues:
            # Internally inconsistent document: kept as evidence, never made current, nothing created.
            for row in [umoa, *rows.values()]:
                row.status = "AMBIGUOUS"
                row.status_reason = "self-check failed: " + "; ".join(issues[:10])
            result.snapshot_status = "AMBIGUOUS"
            return result

        # ---------------------------------------------------------- members + resolution
        member_rows: list[tuple[ReferenceUniverseMember, ParsedMember]] = []
        for cc in country_codes:
            country = parsed.countries.get(cc)
            if country is None:
                continue
            for pm in country.banks():
                mrow = await self._member_row(db, rows[cc], pm)
                member_rows.append((mrow, pm))
                result.members += 1
                if mrow.review_decision is not None:
                    # A human decision is never overridden. A confirmed link carries the official
                    # evidence (registration number, names) so later lists resolve by identifier.
                    if mrow.review_decision == "confirmed" and mrow.entity_id:
                        entity = await db.get(Entity, mrow.entity_id)
                        await self._record_evidence(db, entity, pm, mrow, parsed, document, source, run_id, countries)
                        result.entities_matched += 1
                    continue
                if mrow.resolution_status in ("matched", "created") and mrow.entity_id:
                    entity = await db.get(Entity, mrow.entity_id)
                    await self._record_evidence(db, entity, pm, mrow, parsed, document, source, run_id, countries)
                    result.entities_matched += 1
                    continue
                resolution = self.resolver.resolve_member(
                    country_code=cc,
                    official_name=pm.official_name,
                    registration_number=pm.registration_number,
                    former_names=pm.designation.former_names,
                    acronym=pm.designation.acronym,
                    branch=pm.form == "branch",
                )
                await self._apply_resolution(
                    db, mrow, pm, resolution, parsed, document, source, run_id, countries, result
                )
        await db.flush()

        # ---------------------------------------------------------- branches → parents
        for mrow, pm in member_rows:
            if pm.form != "branch" or not mrow.entity_id:
                continue
            parent_name = pm.designation.parent_name or pm.official_name
            parent = self.resolver.resolve_parent(parent_name=parent_name, host_country_code=pm.country_code)
            if parent.status != "matched" or parent.entity_id == mrow.entity_id:
                note = f"parent not resolved ({parent.status}): {parent_name!r}"
                if note not in (mrow.resolution_notes or ""):
                    mrow.resolution_notes = f"{mrow.resolution_notes} | {note}" if mrow.resolution_notes else note
                continue
            if await self._ensure_branch_relationship(db, mrow.entity_id, parent.entity_id, pm, parsed, document,
                                                      source, parent):
                result.relationships_created += 1

        # ---------------------------------------------------------- counts & status per country
        for cc, row in rows.items():
            await self._refresh_counts(db, row)
        await self._refresh_counts(db, umoa, total=True)
        result.snapshot_status = umoa.status
        await db.flush()
        return result

    # ================================================================== universe rows
    async def _universe_row(self, db: AsyncSession, document: Document, country_id: str | None) -> ReferenceUniverse:
        stmt = select(ReferenceUniverse).where(
            ReferenceUniverse.universe_code == self.universe_code,
            ReferenceUniverse.reference_document_id == document.id,
            ReferenceUniverse.deleted_at.is_(None),
        )
        stmt = stmt.where(
            ReferenceUniverse.country_id.is_(None) if country_id is None else ReferenceUniverse.country_id == country_id
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ReferenceUniverse(universe_code=self.universe_code, country_id=country_id,
                                    reference_document_id=document.id)
            db.add(row)
        return row

    @staticmethod
    def _fill_universe(row, parsed, source, document, expected, evidence, now) -> None:
        row.entity_class = "financial_institution"
        row.entity_type = "commercial_bank"
        row.reference_source_id = source.id
        row.reference_document_id = document.id
        row.reference_date = parsed.reference_date
        row.expected_count = expected  # None when the document does not state it
        row.expected_count_evidence = evidence
        row.last_checked_at = now

    async def _refresh_counts(self, db: AsyncSession, row: ReferenceUniverse, total: bool = False) -> None:
        stmt = select(ReferenceUniverseMember).join(
            ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id
        ).where(
            ReferenceUniverse.universe_code == self.universe_code,
            ReferenceUniverse.reference_document_id == row.reference_document_id,
            ReferenceUniverse.deleted_at.is_(None),
            ReferenceUniverseMember.deleted_at.is_(None),
            ReferenceUniverseMember.category == "bank",
        )
        if not total:
            stmt = stmt.where(ReferenceUniverseMember.universe_id == row.id)
        members = (await db.execute(stmt)).scalars().all()
        row.discovered_count = len(members)
        row.matched_count = sum(1 for m in members if m.entity_id and m.resolution_status in ("matched", "created"))
        if row.expected_count is None:
            row.coverage_ratio = None
            row.status = "UNKNOWN"
            row.status_reason = "expected count not stated by the official document"
            return
        row.coverage_ratio = (
            Decimal(min(row.matched_count, row.expected_count)) / Decimal(row.expected_count)
            if row.expected_count > 0 else None
        )
        pending = [m for m in members if m.resolution_status in ("ambiguous", "unresolved")]
        if row.matched_count == row.expected_count and row.discovered_count == row.expected_count and not pending:
            row.status, row.status_reason = "COMPLETE", None
        else:
            row.status = "INCOMPLETE"
            row.status_reason = (
                f"{row.matched_count}/{row.expected_count} resolved; {len(pending)} pending review"
            )

    # ================================================================== members
    async def _member_row(self, db: AsyncSession, universe: ReferenceUniverse, pm: ParsedMember
                          ) -> ReferenceUniverseMember:
        key = pm.registration_number
        stmt = select(ReferenceUniverseMember).where(
            ReferenceUniverseMember.universe_id == universe.id,
            ReferenceUniverseMember.category == pm.category,
            ReferenceUniverseMember.deleted_at.is_(None),
        )
        stmt = stmt.where(
            ReferenceUniverseMember.registration_number == key if key
            else ReferenceUniverseMember.normalized_name == normalize_name(pm.official_name)
        )
        row = (await db.execute(stmt)).scalar_one_or_none()
        if row is None:
            row = ReferenceUniverseMember(universe_id=universe.id, category=pm.category)
            db.add(row)
        row.member_form = pm.form
        row.raw_name = pm.raw_name
        row.official_name = pm.official_name[:500]
        row.normalized_name = normalize_name(pm.official_name)[:500]
        row.acronym = pm.designation.acronym
        row.former_names = pm.designation.former_names or None
        row.parent_name_raw = pm.designation.parent_name
        row.registration_number = pm.registration_number
        row.row_index = pm.row_index
        row.page_number = pm.page_number
        row.raw_text = pm.raw_name
        row.flags = (pm.designation.flags + pm.notes) or None
        await db.flush()
        return row

    async def _apply_resolution(
        self, db, mrow: ReferenceUniverseMember, pm: ParsedMember, res: Resolution, parsed, document, source, run_id,
        countries, result: MaterializationResult,
    ) -> None:
        if res.status == "ambiguous":
            mrow.entity_id = None
            mrow.resolution_status = "ambiguous"
            mrow.resolution_method = None
            mrow.confidence = None
            mrow.candidate_entity_ids = res.candidates
            mrow.resolution_notes = res.notes
            result.ambiguous += 1
            return
        if res.status == "matched":
            entity = await db.get(Entity, res.entity_id)
            mrow.entity_id = entity.id
            mrow.resolution_status = "matched"
            result.entities_matched += 1
        else:
            entity = await self._create_entity(db, pm, source, document, parsed, countries)
            mrow.entity_id = entity.id
            mrow.resolution_status = "created"
            result.entities_created += 1
        mrow.resolution_method = res.method or "created_from_official_list"
        mrow.confidence = Decimal(str(res.confidence)) if res.confidence is not None else Decimal("1")
        mrow.candidate_entity_ids = None
        mrow.resolution_notes = res.notes
        result.names_added += await self._record_evidence(
            db, entity, pm, mrow, parsed, document, source, run_id, countries
        )

    async def _create_entity(self, db, pm: ParsedMember, source, document, parsed, countries) -> Entity:
        country = countries[pm.country_code]
        entity = Entity(
            entity_class="financial_institution",
            entity_type="commercial_bank",
            canonical_name=pm.official_name[:255],
            short_name=(pm.designation.acronym or None) and pm.designation.acronym[:50],
            country_id=country.id,
            status="active",
            description=(
                f"Établissement de crédit agréé ({'succursale' if pm.form == 'branch' else 'banque'}) — "
                f"{parsed.title[:120]} ; date de référence {parsed.reference_date}"
            ),
        )
        db.add(entity)
        await db.flush()
        db.add(Institution(
            name_official=pm.official_name[:255],
            name_commercial=pm.designation.acronym,
            institution_type="bank",
            country_id=country.id,
            regulatory_id=pm.registration_number,
            status="active",
            source_id=source.id,
            entity_id=entity.id,
            data_notes=(
                f"Created by the discovery engine from an official list: {source.short_name} "
                f"'{parsed.title[:100]}' (reference date {parsed.reference_date}), page {pm.page_number}."
            ),
        ))
        indexed = IndexedEntity(id=entity.id, country_code=pm.country_code, canonical_name=entity.canonical_name,
                                is_branch=pm.form == "branch")
        indexed.add_name(pm.official_name)
        for former in pm.designation.former_names:
            indexed.add_name(former)
        indexed.add_name(pm.designation.acronym, "acronym")
        self.resolver.add(indexed)
        await db.flush()
        return entity

    # ================================================================== evidence (idempotent)
    async def _record_evidence(
        self, db, entity: Entity, pm: ParsedMember, mrow, parsed: ParsedReferenceList, document: Document,
        source: Source, run_id, countries,
    ) -> int:
        added = 0
        ref_date = parsed.reference_date
        if pm.registration_number:
            await self._ensure_identifier(db, entity, pm, document, source, ref_date)
            self.resolver.register_identifier(entity.id, pm.registration_number)
        added += await self._record_official_name(db, entity, pm.official_name, ref_date, source, document,
                                                  pm.page_number)
        if pm.designation.acronym:
            added += await self._ensure_name(db, entity, pm.designation.acronym, "acronym", source, document,
                                             pm.page_number, valid_from=ref_date)
        for former in pm.designation.former_names:
            # "X ex Y": Y was no longer the name at the reference date.
            added += await self._ensure_name(db, entity, former, "former", source, document, pm.page_number,
                                             valid_to=ref_date)
        indexed = self.resolver.entities.get(entity.id)
        if indexed is not None:
            indexed.add_name(pm.official_name)
            for former in pm.designation.former_names:
                indexed.add_name(former)
            indexed.add_name(pm.designation.acronym, "acronym")
            if pm.form == "branch":
                indexed.is_branch = True
        await self._ensure_entity_source(db, entity, source, document, pm, run_id)
        await self._ensure_document_link(db, entity, document, pm)
        return added

    async def _ensure_identifier(self, db, entity, pm, document, source, ref_date) -> None:
        existing = (
            await db.execute(
                select(EntityIdentifier).where(
                    EntityIdentifier.id_type == "bceao_registration_number",
                    EntityIdentifier.value == pm.registration_number,
                    EntityIdentifier.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.valid_from is None or (ref_date and ref_date < existing.valid_from):
                existing.valid_from = ref_date
            return
        db.add(EntityIdentifier(
            entity_id=entity.id, id_type="bceao_registration_number", value=pm.registration_number,
            authority_name="Commission Bancaire de l'UMOA / BCEAO (liste des établissements de crédit agréés)",
            valid_from=ref_date, source_id=source.id, document_id=document.id, page_number=pm.page_number,
        ))
        await db.flush()

    async def _ensure_name(self, db, entity, name, name_type, source, document, page, valid_from=None,
                           valid_to=None) -> int:
        norm = normalize_name(name)[:500]
        if not norm:
            return 0
        existing = (
            await db.execute(
                select(EntityName).where(
                    EntityName.entity_id == entity.id,
                    EntityName.name_type == name_type,
                    EntityName.normalized_name == norm,
                    EntityName.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if valid_from and (existing.valid_from is None or valid_from < existing.valid_from):
                existing.valid_from = valid_from
            return 0
        db.add(EntityName(entity_id=entity.id, name=name[:500], normalized_name=norm, name_type=name_type,
                          valid_from=valid_from, valid_to=valid_to, source_id=source.id, document_id=document.id,
                          page_number=page))
        await db.flush()
        return 1

    async def _record_official_name(self, db, entity: Entity, name: str, ref_date: date | None, source, document,
                                    page) -> int:
        """Official name history: a newer, different official name closes the previous one."""
        norm = normalize_name(name)
        officials = (
            await db.execute(
                select(EntityName).where(
                    EntityName.entity_id == entity.id,
                    EntityName.name_type == "official",
                    EntityName.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        same = next((n for n in officials if n.normalized_name == norm), None)
        if same is not None:
            if ref_date and (same.valid_from is None or ref_date < same.valid_from):
                same.valid_from = ref_date
            return 0
        current = [n for n in officials if n.valid_to is None]
        newest_known = max((n.valid_from for n in officials if n.valid_from), default=None)
        is_newer = ref_date is not None and (newest_known is None or ref_date > newest_known)
        if is_newer:
            for n in current:
                n.valid_to = ref_date - timedelta(days=1) if n.valid_from and ref_date > n.valid_from else ref_date
            entity.canonical_name = name[:255]
            valid_to = None
        else:
            # Older snapshot with another name: a historical official name, closed at the next known one.
            later = min((n.valid_from for n in officials if n.valid_from and ref_date and n.valid_from > ref_date),
                        default=None)
            valid_to = later - timedelta(days=1) if later else ref_date
        db.add(EntityName(entity_id=entity.id, name=name[:500], normalized_name=norm[:500], name_type="official",
                          valid_from=ref_date, valid_to=valid_to, source_id=source.id, document_id=document.id,
                          page_number=page))
        await db.flush()
        return 1

    async def _ensure_entity_source(self, db, entity, source, document, pm, run_id) -> None:
        existing = (
            await db.execute(
                select(EntitySource).where(
                    EntitySource.entity_id == entity.id,
                    EntitySource.link_role == "regulatory_listing",
                    EntitySource.source_id == source.id,
                    EntitySource.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        now = utcnow()
        evidence = f"listed in '{document.title[:150]}' p.{pm.page_number} ({pm.registration_number})"
        if existing is None:
            db.add(EntitySource(
                entity_id=entity.id, source_id=source.id, url=document.url, link_role="regulatory_listing",
                priority=LINK_ROLE_PRIORITY["regulatory_listing"], lifecycle_status="ACTIVE",
                discovery_method="official_reference_list", discovery_run_id=run_id,
                evidence_document_id=document.id, evidence_page=pm.page_number, verification_evidence=evidence,
                verified_at=now, last_checked_at=now, last_http_status=200,
            ))
        else:
            existing.lifecycle_status = "ACTIVE"
            existing.url = document.url
            existing.evidence_document_id = document.id
            existing.evidence_page = pm.page_number
            existing.verification_evidence = evidence
            existing.last_checked_at = now
        await db.flush()

    async def _ensure_document_link(self, db, entity, document, pm) -> None:
        existing = (
            await db.execute(
                select(DocumentEntity).where(
                    DocumentEntity.document_id == document.id,
                    DocumentEntity.entity_id == entity.id,
                    DocumentEntity.link_type == "reference_listing",
                    DocumentEntity.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if existing is None:
            db.add(DocumentEntity(
                document_id=document.id, entity_id=entity.id, link_type="reference_listing",
                page_from=pm.page_number, page_to=pm.page_number, label_in_document=pm.raw_name[:500],
                method="official_reference_list", evidence=pm.registration_number,
            ))
            await db.flush()

    async def _ensure_branch_relationship(self, db, branch_id, parent_id, pm, parsed, document, source,
                                          parent: Resolution) -> bool:
        existing = (
            await db.execute(
                select(EntityRelationship).where(
                    EntityRelationship.source_entity_id == branch_id,
                    EntityRelationship.target_entity_id == parent_id,
                    EntityRelationship.relationship_type == "branch_of",
                    EntityRelationship.deleted_at.is_(None),
                )
            )
        ).scalars().first()
        if existing is not None:
            if parsed.reference_date and (existing.valid_from is None or parsed.reference_date < existing.valid_from):
                existing.valid_from = parsed.reference_date
            return False
        db.add(EntityRelationship(
            source_entity_id=branch_id, target_entity_id=parent_id, relationship_type="branch_of",
            role_context="succursale", valid_from=parsed.reference_date, is_current=True, source_id=source.id,
            document_id=document.id, page_number=pm.page_number,
            confidence_score=Decimal(str(parent.confidence or 0.8)),
            notes=f"'{pm.raw_name}' ({pm.registration_number}); parent resolved by {parent.method}",
        ))
        await db.flush()
        return True


# ====================================================================== current snapshot
async def refresh_current_snapshot(db: AsyncSession, universe_code: str) -> ReferenceUniverse | None:
    """The current expected universe = the most recent self-consistent official snapshot."""
    umoa_rows = (
        await db.execute(
            select(ReferenceUniverse).where(
                ReferenceUniverse.universe_code == universe_code,
                ReferenceUniverse.country_id.is_(None),
                ReferenceUniverse.deleted_at.is_(None),
            )
        )
    ).scalars().all()
    valid = [r for r in umoa_rows if r.status in ("COMPLETE", "INCOMPLETE", "UNKNOWN") and r.reference_date]
    current = max(valid, key=lambda r: (r.reference_date, r.created_at), default=None)
    all_rows = (
        await db.execute(
            select(ReferenceUniverse).where(
                ReferenceUniverse.universe_code == universe_code, ReferenceUniverse.deleted_at.is_(None)
            )
        )
    ).scalars().all()
    for row in all_rows:
        row.is_current = current is not None and row.reference_document_id == current.reference_document_id
    await db.flush()
    return current


def member_name_key(member: ReferenceUniverseMember) -> str:
    return name_key(member.official_name)
