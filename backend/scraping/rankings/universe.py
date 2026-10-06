"""
Ranking universe — the official, homogeneous population of banks.

The banking ranking universe is built dynamically from the CURRENT official reference
snapshot (reference_universes.is_current, universe_code UMOA.BANKING, financial_institution /
commercial_bank), never from `SELECT * FROM institutions`, never from a hardcoded list or count.

A member belongs to the universe when:
  - its snapshot is current and not deleted;
  - its line is a bank line (category = 'bank'), resolved (matched / created) to an entity,
    and not rejected by a human decision;
  - its entity is a financial_institution / commercial_bank;
  - an institution row exists for that entity, with institution_type = 'bank',
    in the country of the snapshot (country-level snapshots only).

Every other non-deleted institution of the requested scope is kept in the database and in the
history, but reported as an explicit population exclusion (e.g. a branch that only appears in
an older snapshot). Nothing is deleted or modified here.

When no current reference snapshot exists at all (databases that never ran the discovery
engine), the universe falls back to the institutions of type 'bank' and says so in
`source` — the two populations are never mixed.
"""
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import UNIVERSE_BANKING
from app.models.country import Country
from app.models.discovery import ReferenceUniverse, ReferenceUniverseMember
from app.models.entity import Entity
from app.models.institution import Institution

UMOA = "UMOA"

UNIVERSE_ENTITY_CLASS = "financial_institution"
UNIVERSE_ENTITY_TYPE = "commercial_bank"
UNIVERSE_INSTITUTION_TYPE = "bank"
UNIVERSE_MEMBER_CATEGORY = "bank"
RESOLVED_MEMBER_STATUSES = ("matched", "created")

SOURCE_REFERENCE = "reference_universe"
SOURCE_FALLBACK = "institutions_table"

# Population exclusion reasons (institutions outside the ranking universe).
REASON_NOT_IN_CURRENT_UNIVERSE = "not_in_current_reference_universe"
REASON_NOT_A_BANK = "institution_type_not_bank"


@dataclass
class ExcludedInstitution:
    institution: Institution
    country_code: str | None
    reason: str


@dataclass
class UniverseResolution:
    members: list[tuple[Institution, str | None]]
    excluded: list[ExcludedInstitution] = field(default_factory=list)
    source: str = SOURCE_REFERENCE
    reference_date: date | None = None
    # Same institution reached through several member lines: must stay 0.
    duplicate_member_lines: int = 0


async def current_reference_universes(db: AsyncSession) -> list[ReferenceUniverse]:
    rows = await db.execute(
        select(ReferenceUniverse).where(
            ReferenceUniverse.universe_code == UNIVERSE_BANKING,
            ReferenceUniverse.is_current.is_(True),
            ReferenceUniverse.deleted_at.is_(None),
            ReferenceUniverse.entity_class == UNIVERSE_ENTITY_CLASS,
            ReferenceUniverse.entity_type == UNIVERSE_ENTITY_TYPE,
        )
    )
    return list(rows.scalars().all())


async def _scoped_institutions(db: AsyncSession, country_code: str | None) -> list[tuple[Institution, str | None]]:
    query = (
        select(Institution, Country.code)
        .join(Country, Institution.country_id == Country.id)
        .where(Institution.deleted_at.is_(None))
    )
    if country_code and country_code.upper() != UMOA:
        query = query.where(Country.code == country_code.upper())
    return [(inst, code) for inst, code in (await db.execute(query)).all()]


async def resolve_banking_universe(db: AsyncSession, country_code: str | None) -> UniverseResolution:
    """Members and explicit population exclusions for one country, or the 8 UMOA countries."""
    scoped = await _scoped_institutions(db, country_code)
    universes = await current_reference_universes(db)

    if not universes:
        members = [(i, c) for i, c in scoped if i.institution_type == UNIVERSE_INSTITUTION_TYPE]
        excluded = [
            ExcludedInstitution(i, c, REASON_NOT_A_BANK)
            for i, c in scoped
            if i.institution_type != UNIVERSE_INSTITUTION_TYPE
        ]
        return UniverseResolution(members=members, excluded=excluded, source=SOURCE_FALLBACK)

    query = (
        select(Institution, Country.code)
        .select_from(ReferenceUniverseMember)
        .join(ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id)
        .join(Entity, Entity.id == ReferenceUniverseMember.entity_id)
        .join(Institution, Institution.entity_id == Entity.id)
        .join(Country, Institution.country_id == Country.id)
        .where(
            ReferenceUniverse.id.in_([u.id for u in universes]),
            ReferenceUniverseMember.deleted_at.is_(None),
            ReferenceUniverseMember.category == UNIVERSE_MEMBER_CATEGORY,
            ReferenceUniverseMember.resolution_status.in_(RESOLVED_MEMBER_STATUSES),
            or_(
                ReferenceUniverseMember.review_decision.is_(None),
                ReferenceUniverseMember.review_decision != "rejected",
            ),
            Entity.deleted_at.is_(None),
            Entity.entity_class == UNIVERSE_ENTITY_CLASS,
            Entity.entity_type == UNIVERSE_ENTITY_TYPE,
            Institution.deleted_at.is_(None),
            Institution.institution_type == UNIVERSE_INSTITUTION_TYPE,
            or_(ReferenceUniverse.country_id.is_(None), ReferenceUniverse.country_id == Institution.country_id),
        )
    )
    if country_code and country_code.upper() != UMOA:
        query = query.where(Country.code == country_code.upper())

    seen: dict[str, tuple[Institution, str | None]] = {}
    duplicates = 0
    for inst, code in (await db.execute(query)).all():
        if inst.id in seen:
            duplicates += 1
            continue
        seen[inst.id] = (inst, code)

    excluded = [
        ExcludedInstitution(
            i, c, REASON_NOT_A_BANK if i.institution_type != UNIVERSE_INSTITUTION_TYPE else REASON_NOT_IN_CURRENT_UNIVERSE
        )
        for i, c in scoped
        if i.id not in seen
    ]
    dates = {u.reference_date for u in universes if u.reference_date is not None}
    return UniverseResolution(
        members=list(seen.values()),
        excluded=excluded,
        source=SOURCE_REFERENCE,
        reference_date=max(dates) if dates else None,
        duplicate_member_lines=duplicates,
    )
