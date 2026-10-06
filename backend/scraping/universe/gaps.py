"""
Source gap queue (Phase 15).

After every round the queue is reconciled with the coverage computed from PostgreSQL:
  - a missing item without an open gap         → new gap (OPEN, priority by type);
  - a gap whose item is now present            → RESOLVED (resolved_at);
  - a gap every applicable strategy has tried  → NOT_FOUND, with next_attempt_at (retry later);
  - a gap blocked by the target (403, robots)  → BLOCKED;
  - a NOT_FOUND gap whose retry date has passed is reopened at the start of the next run.
A source that is empty today is never considered useless for good: it is simply retried.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import (
    DEFAULT_GAP_RETRY_DAYS,
    GAP_PRIORITY_BY_TYPE,
    HUMAN_ONLY_GAP_TYPES,
    LEGACY_GAP_TYPES,
)
from app.models.country import Country
from app.models.discovery import DiscoveryGap, ReferenceUniverse, ReferenceUniverseMember
from scraping.universe.coverage import CoverageSnapshot, EntityCoverage


def utcnow() -> datetime:
    return datetime.now(UTC)


def missing_items(e: EntityCoverage) -> dict[str, str]:
    """Gap type → reason (evidence), for one entity of the official universe.

    NOT_FOUND never means "does not exist": only that the strategies executed so far found nothing.
    """
    out: dict[str, str] = {}
    if not e.regulatory_listing:
        out["REGULATORY_SOURCE"] = "no regulatory listing linked"
    # ---- institutional source (own website / publications, BRVM market source)
    if not e.institutional_source:
        if e.website_candidates:
            out["SOURCE_FOUND_UNVERIFIED"] = (f"{e.website_candidates} candidate website(s) not verified "
                                              f"(content does not name the bank, or unreachable): {e.website_url}")
        elif e.website_blocked:
            out["SOURCE_BLOCKED"] = f"{e.website_blocked} candidate website(s) refuse access (HTTP 401/403/429 / robots)"
        else:
            out["SOURCE_NOT_FOUND"] = "no institutional source found by the strategies executed so far"
    # ---- institution-specific documents
    inst_docs = len(e.institution_document_urls)
    if inst_docs == 0:
        out["DOCUMENT_NOT_FOUND"] = "no institution-specific document found by the strategies executed so far"
    elif e.machine_readable_documents == 0:
        out["DOCUMENT_NOT_MACHINE_READABLE"] = (f"{inst_docs} institution-specific document(s) found, none with a "
                                                "reliable text layer (scanned / corrupted): no extraction possible")
    elif e.analysed_documents < inst_docs:
        out["DOCUMENT_FOUND_UNVERIFIED"] = f"{inst_docs - e.analysed_documents} document(s) not yet analysed"
    # ---- ambiguities (human decision)
    for amb in e.ambiguities:
        out.setdefault(amb["type"], f"label '{amb.get('label')}' — {amb.get('evidence')}")
    # ---- data
    if not e.has_financial_document:
        out["FINANCIAL_DOCUMENT"] = "no downloaded financial document linked"
    if not e.has_financial_data:
        out["FINANCIAL_DATA"] = "no non-rejected observation on a banking catalogue metric"
    elif not e.has_verified_data:
        out["VALIDATION"] = "observations exist but none is verified (human review required)"
    return out


class GapQueue:
    def __init__(self, retry_days: int = DEFAULT_GAP_RETRY_DAYS) -> None:
        self.retry_days = retry_days

    async def reopen_due(self, db: AsyncSession, force: bool = False) -> int:
        """Reopen NOT_FOUND gaps whose retry date has passed (or all of them on an explicit operator
        request, e.g. after an extractor change). BLOCKED gaps are never reopened here."""
        now = utcnow()
        stmt = select(DiscoveryGap).where(DiscoveryGap.status == "NOT_FOUND", DiscoveryGap.deleted_at.is_(None))
        if not force:
            stmt = stmt.where(DiscoveryGap.next_attempt_at <= now)
        due = (await db.execute(stmt)).scalars().all()
        for gap in due:
            gap.status = "OPEN"
        await db.flush()
        return len(due)

    async def reconcile(self, db: AsyncSession, snap: CoverageSnapshot) -> dict[str, int]:
        now = utcnow()
        stats = {"opened": 0, "resolved": 0}
        countries = {c.code: c.id for c in (await db.execute(select(Country))).scalars().all()}
        current_rows = {
            r.country_id: r.id for r in (await db.execute(select(ReferenceUniverse).where(
                ReferenceUniverse.universe_code == snap.universe_code, ReferenceUniverse.is_current.is_(True),
                ReferenceUniverse.deleted_at.is_(None)))).scalars().all()
        }
        open_gaps = (await db.execute(select(DiscoveryGap).where(
            DiscoveryGap.status != "RESOLVED", DiscoveryGap.deleted_at.is_(None)))).scalars().all()
        by_key = {(g.entity_id, g.member_id, g.gap_type): g for g in open_gaps}
        wanted: dict[tuple[str | None, str | None, str], tuple[str, str, str | None]] = {}

        for e in snap.entities:
            for gap_type, reason in missing_items(e).items():
                wanted[(e.entity_id, None, gap_type)] = (reason, e.country_code, None)
        for cc, country in snap.countries.items():
            for m in country.missing:
                wanted[(None, m.member_id, "ENTITY_UNRESOLVED")] = (
                    f"official line not resolved ({m.resolution_status}): {m.official_name}", cc, m.member_id)

        for key, (reason, cc, _member) in wanted.items():
            gap = by_key.get(key)
            if gap is None:
                entity_id, member_id, gap_type = key
                db.add(DiscoveryGap(
                    universe_id=current_rows.get(countries.get(cc)), entity_id=entity_id, member_id=member_id,
                    country_id=countries.get(cc), gap_type=gap_type,
                    priority=GAP_PRIORITY_BY_TYPE.get(gap_type, "MEDIUM"), status="OPEN", attempts=0,
                    strategies_tried=[], reason=reason, evidence=reason,
                ))
                stats["opened"] += 1
            elif gap.status in ("OPEN", "SEARCHING"):
                gap.reason = reason
            if gap is not None:
                gap.evidence = reason
        # Gaps of the current universe that are no longer missing are resolved.
        in_scope = {e.entity_id for e in snap.entities}
        missing_member_ids = {m.member_id for c in snap.countries.values() for m in c.missing}
        current_member_ids = set((await db.execute(
            select(ReferenceUniverseMember.id).where(
                ReferenceUniverseMember.universe_id.in_([uid for uid in current_rows.values() if uid]),
                ReferenceUniverseMember.deleted_at.is_(None),
            )
        )).scalars().all())
        for key, gap in by_key.items():
            if key in wanted:
                continue
            entity_id, member_id, gap_type = key
            if gap_type in LEGACY_GAP_TYPES:
                # Phase-15 types replaced by the SOURCE_* / DOCUMENT_* taxonomy: closed, never "found".
                gap.status = "RESOLVED"
                gap.resolved_at = now
                gap.reason = f"superseded by the Phase-17 gap taxonomy | {gap.reason or ''}".rstrip(" |")
                stats["superseded"] = stats.get("superseded", 0) + 1
            elif member_id and member_id not in current_member_ids:
                gap.status = "RESOLVED"
                gap.resolved_at = now
                gap.reason = f"closed: line of a superseded official snapshot | {gap.reason or ''}".rstrip(" |")
                stats["out_of_scope"] = stats.get("out_of_scope", 0) + 1
            elif (entity_id and entity_id in in_scope) or (member_id and member_id not in missing_member_ids):
                gap.status = "RESOLVED"
                gap.resolved_at = now
                stats["resolved"] += 1
            elif entity_id and snap.reference_available:
                # The entity is no longer listed by the current official reference (e.g. a branch
                # converted into a subsidiary): the gap no longer applies. The entity itself is kept.
                gap.status = "RESOLVED"
                gap.resolved_at = now
                gap.reason = (f"closed: entity absent from the current official list "
                              f"({snap.reference_source} {snap.reference_date}) | {gap.reason or ''}").rstrip(" |")
                stats["out_of_scope"] = stats.get("out_of_scope", 0) + 1
        await db.flush()
        return stats

    async def open_targets(self, db: AsyncSession, gap_types: set[str]) -> list[DiscoveryGap]:
        return list((await db.execute(select(DiscoveryGap).where(
            DiscoveryGap.gap_type.in_(gap_types), DiscoveryGap.status.in_(("OPEN", "SEARCHING")),
            DiscoveryGap.deleted_at.is_(None)))).scalars().all())

    async def pending(self, db: AsyncSession, gap_types: set[str]) -> list[DiscoveryGap]:
        """Gaps already searched and waiting for their retry date (NOT_FOUND) or blocked."""
        return list((await db.execute(select(DiscoveryGap).where(
            DiscoveryGap.gap_type.in_(gap_types), DiscoveryGap.status.in_(("NOT_FOUND", "BLOCKED")),
            DiscoveryGap.deleted_at.is_(None)))).scalars().all())

    async def record_attempt(
        self, db: AsyncSession, gaps: list[DiscoveryGap], strategy_code: str, blocked_entity_ids: set[str]
    ) -> None:
        now = utcnow()
        for gap in gaps:
            gap.attempts = (gap.attempts or 0) + 1
            tried = list(gap.strategies_tried or [])
            if strategy_code not in tried:
                tried.append(strategy_code)
            gap.strategies_tried = tried
            gap.last_attempt_at = now
            gap.last_strategy = strategy_code
            if gap.entity_id in blocked_entity_ids:
                gap.status = "BLOCKED"
                gap.reason = f"{gap.reason or ''} | blocked during {strategy_code}".strip(" |")
            elif gap.status == "OPEN":
                gap.status = "SEARCHING"
        await db.flush()

    async def finalize(self, db: AsyncSession, strategies_by_gap_type: dict[str, list[str]]) -> dict[str, int]:
        """End of run: gaps every applicable strategy has tried become NOT_FOUND (retry scheduled)."""
        now = utcnow()
        stats = {"not_found": 0, "human_review": 0, "no_strategy": 0}
        gaps = (await db.execute(select(DiscoveryGap).where(
            DiscoveryGap.status.in_(("OPEN", "SEARCHING")), DiscoveryGap.deleted_at.is_(None)))).scalars().all()
        for gap in gaps:
            if gap.gap_type in HUMAN_ONLY_GAP_TYPES:
                gap.status = "OPEN"
                stats["human_review"] += 1
                continue
            applicable = strategies_by_gap_type.get(gap.gap_type, [])
            if not applicable:
                gap.status = "OPEN"
                gap.reason = f"{gap.reason or ''} | no enabled strategy handles this gap".strip(" |")
                stats["no_strategy"] += 1
                continue
            tried = set(gap.strategies_tried or [])
            if set(applicable) <= tried:
                gap.status = "NOT_FOUND"
                gap.next_attempt_at = now + timedelta(days=self.retry_days)
                stats["not_found"] += 1
        await db.flush()
        return stats
