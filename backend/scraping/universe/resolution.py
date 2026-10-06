"""
Entity resolution for the discovery engine (Phase 15).

Order of evidence (strongest first):
  1. regulatory registration number (e.g. "B 0061 F")      → matched, confidence 1.0
  2. exact name (official / former / regulatory label), same country, same form
                                                            → matched, confidence 0.9
  3. name without country words / acronym, same country, unique candidate
                                                            → matched, confidence 0.8
  4. anything weaker (token overlap)                        → AMBIGUOUS: candidates kept, nothing linked
  5. nothing                                                → no match (the caller may create the entity)

Hard rules:
  - never across countries;
  - a branch ("SUCCURSALE") never resolves to a non-branch entity and vice versa
    (a branch is never merged with its parent bank);
  - an entity carrying a DIFFERENT registration number is a different licensed entity.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.country import Country
from app.models.discovery import EntityIdentifier, EntityName, ReferenceUniverseMember
from app.models.entity import Entity
from scraping.universe.normalize import core_key, core_tokens, name_key, normalize_name

BANK_ENTITY_TYPES = ("commercial_bank", "development_bank")

GENERIC_TOKENS = frozenset({
    "BANK", "BANQUE", "BANCO", "BANKING", "INTERNATIONAL", "INTERNATIONALE", "GROUP", "GROUPE", "SOCIETE",
    "COMPAGNIE", "CREDIT", "FINANCE", "FINANCIERE", "DE", "DU", "DES", "DA", "LA", "LE", "LES", "L", "D", "ET",
    "POUR", "AU", "AUX", "EN", "FOR", "OF", "THE", "AND", "UNION", "AFRIQUE", "AFRICA", "OUEST", "WEST",
})


def is_branch_name(value: str | None) -> bool:
    return " SUCCURSALE " in f" {normalize_name(value)} "


@dataclass
class IndexedEntity:
    id: str
    country_code: str | None
    canonical_name: str
    registration_numbers: set[str] = field(default_factory=set)
    name_keys: set[str] = field(default_factory=set)  # official / former / labels, parentheticals removed
    core_keys: set[str] = field(default_factory=set)  # same without country words
    acronym_keys: set[str] = field(default_factory=set)
    token_sets: list[frozenset[str]] = field(default_factory=list)
    is_branch: bool = False

    def add_name(self, value: str | None, kind: str = "official") -> None:
        if not value:
            return
        if kind == "acronym":
            key = normalize_name(value)
            if key:
                self.acronym_keys.add(key)
            return
        key = name_key(value)
        if key:
            self.name_keys.add(key)
        ck = core_key(value)
        if ck:
            self.core_keys.add(ck)
            self.token_sets.append(frozenset(core_tokens(value)))


@dataclass
class Resolution:
    status: str  # matched | ambiguous | no_match
    entity_id: str | None = None
    method: str | None = None
    confidence: float | None = None
    candidates: list[dict] = field(default_factory=list)
    notes: str | None = None


class EntityResolver:
    def __init__(self, entities: list[IndexedEntity] | None = None) -> None:
        self.entities: dict[str, IndexedEntity] = {}
        self.by_registration: dict[str, str] = {}
        for ent in entities or []:
            self.add(ent)

    # ------------------------------------------------------------------ index
    def add(self, ent: IndexedEntity) -> None:
        self.entities[ent.id] = ent
        for reg in ent.registration_numbers:
            self.by_registration[reg] = ent.id

    def register_identifier(self, entity_id: str, registration_number: str) -> None:
        ent = self.entities.get(entity_id)
        if ent is not None:
            ent.registration_numbers.add(registration_number)
        self.by_registration[registration_number] = entity_id

    async def load(self, db: AsyncSession) -> int:
        """Index every financial institution of the Entity Hub (all sources of entities)."""
        countries = {c.id: c.code for c in (await db.execute(select(Country))).scalars().all()}
        rows = (
            await db.execute(
                select(Entity).where(Entity.entity_class == "financial_institution", Entity.deleted_at.is_(None))
            )
        ).scalars().all()
        self.entities.clear()
        self.by_registration.clear()
        for e in rows:
            ent = IndexedEntity(
                id=e.id, country_code=countries.get(e.country_id or ""), canonical_name=e.canonical_name,
                is_branch=is_branch_name(e.canonical_name),
            )
            ent.add_name(e.canonical_name)
            ent.add_name(e.short_name, "acronym")
            self.entities[e.id] = ent
        names = (await db.execute(select(EntityName).where(EntityName.deleted_at.is_(None)))).scalars().all()
        for n in names:
            ent = self.entities.get(n.entity_id)
            if ent is not None:
                ent.add_name(n.name, "acronym" if n.name_type == "acronym" else "official")
        idents = (
            await db.execute(select(EntityIdentifier).where(EntityIdentifier.deleted_at.is_(None)))
        ).scalars().all()
        for i in idents:
            if i.entity_id in self.entities:
                self.entities[i.entity_id].registration_numbers.add(i.value)
                self.by_registration[i.value] = i.entity_id
        # The official list states the form (branch vs subsidiary) even when the name does not.
        branch_ids = (
            await db.execute(
                select(ReferenceUniverseMember.entity_id).where(
                    ReferenceUniverseMember.member_form == "branch",
                    ReferenceUniverseMember.entity_id.is_not(None),
                    ReferenceUniverseMember.deleted_at.is_(None),
                )
            )
        ).scalars().all()
        for entity_id in branch_ids:
            if entity_id in self.entities:
                self.entities[entity_id].is_branch = True
        return len(self.entities)

    # ------------------------------------------------------------------ helpers
    def _country_candidates(self, country_code: str, branch: bool) -> list[IndexedEntity]:
        return [e for e in self.entities.values() if e.country_code == country_code and e.is_branch == branch]

    @staticmethod
    def _describe(ent: IndexedEntity, score: float, reason: str) -> dict:
        return {"entity_id": ent.id, "name": ent.canonical_name, "score": round(score, 3), "reason": reason}

    # ------------------------------------------------------------------ official list line
    def resolve_member(
        self,
        *,
        country_code: str,
        official_name: str,
        registration_number: str | None,
        former_names: list[str] | None = None,
        acronym: str | None = None,
        branch: bool = False,
    ) -> Resolution:
        if registration_number and registration_number in self.by_registration:
            ent = self.entities[self.by_registration[registration_number]]
            if ent.country_code != country_code:
                return Resolution(
                    "ambiguous", candidates=[self._describe(ent, 1.0, "same registration number, other country")],
                    notes="registration number already attached to an entity of another country",
                )
            return Resolution("matched", ent.id, "registration_number", 1.0)

        pool = [
            e for e in self._country_candidates(country_code, branch)
            # an entity with another registration number is another licensed entity
            if not e.registration_numbers or (registration_number in e.registration_numbers)
        ]
        key = name_key(official_name)
        exact = [e for e in pool if key and key in e.name_keys]
        if len(exact) == 1:
            return Resolution("matched", exact[0].id, "exact_name", 0.9)
        if len(exact) > 1:
            return Resolution("ambiguous", candidates=[self._describe(e, 0.9, "exact name") for e in exact],
                              notes="several entities share this exact name in the country")

        former_keys = {name_key(f) for f in former_names or [] if f}
        former = [e for e in pool if former_keys & e.name_keys]
        if len(former) == 1:
            return Resolution("matched", former[0].id, "former_name", 0.85)
        if len(former) > 1:
            return Resolution("ambiguous", candidates=[self._describe(e, 0.85, "former name") for e in former],
                              notes="former name shared by several entities")

        return self._weak_candidates(pool, official_name)

    # ------------------------------------------------------------------ label in a publication
    def resolve_label(self, *, country_code: str, label: str, code: str | None = None) -> Resolution:
        """Resolve the bank label used in a regulatory publication (e.g. BCEAO fascicle)."""
        branch = is_branch_name(label)
        pool = self._country_candidates(country_code, branch)
        key = name_key(label)
        exact = [e for e in pool if key and key in e.name_keys]
        if len(exact) == 1:
            return Resolution("matched", exact[0].id, "exact_name", 0.9)
        ck = core_key(label)
        core = [e for e in pool if ck and ck in e.core_keys]
        if len(core) == 1:
            return Resolution("matched", core[0].id, "name_without_country", 0.8)
        if len(exact) > 1 or len(core) > 1:
            cands = exact or core
            return Resolution("ambiguous", candidates=[self._describe(e, 0.8, "same name") for e in cands],
                              notes="several entities match this label")
        for value in (code, label):
            acr = normalize_name(value) if value else ""
            if acr:
                # current acronym, or a former acronym recorded as a former name ("ex BICIS")
                hits = [e for e in pool if acr in e.acronym_keys or acr in e.name_keys]
                if len(hits) == 1:
                    return Resolution("matched", hits[0].id, "acronym", 0.8)
                if len(hits) > 1:
                    return Resolution("ambiguous", candidates=[self._describe(e, 0.8, "acronym") for e in hits],
                                      notes="acronym shared by several entities")
        # "BICI COTE D'IVOIRE" ↔ official acronym "BICICI": the label's core followed by the ISO code of
        # the country the label itself names equals the entity's official acronym (unique, same country).
        from scraping.universe.normalize import country_codes_in

        if country_codes_in(label) == {country_code}:
            core = core_key(label).replace(" ", "")
            if core:
                hits = [e for e in pool if f"{core}{country_code}" in e.acronym_keys]
                if len(hits) == 1:
                    return Resolution("matched", hits[0].id, "acronym_with_country_code", 0.8,
                                      notes=f"'{core}' + '{country_code}' = official acronym")
        weak = self._weak_candidates(pool, label)
        if weak.status != "no_match":
            return weak
        # A brand-only label ("ORABANK") may designate the local BRANCH of a foreign bank: never
        # linked automatically (branch ≠ parent rule), but surfaced for human review.
        tokens = frozenset(core_tokens(label))
        other_form = [
            e for e in self._country_candidates(country_code, not branch)
            if tokens and any(tokens <= ts for ts in e.token_sets)
        ]
        if other_form:
            return Resolution(
                "ambiguous", candidates=[self._describe(e, 0.6, "label contained in a branch/subsidiary name")
                                         for e in other_form],
                notes="label only matches an entity of the other form (branch vs subsidiary): review required",
            )
        return weak

    def _weak_candidates(self, pool: list[IndexedEntity], value: str) -> Resolution:
        # Generic words ("BANK", "BANQUE", "INTERNATIONAL", ...) are no evidence: two unrelated banks
        # (or a demo row) sharing them must not send an official line to review.
        tokens = frozenset(core_tokens(value)) - GENERIC_TOKENS
        if not tokens:
            return Resolution("no_match")
        scored: list[tuple[float, IndexedEntity]] = []
        for e in pool:
            best = 0.0
            for ts in e.token_sets:
                distinctive = ts - GENERIC_TOKENS
                if distinctive and tokens & distinctive:
                    best = max(best, len(tokens & distinctive) / len(tokens | distinctive))
            if best >= 0.5:
                scored.append((best, e))
        if not scored:
            return Resolution("no_match")
        scored.sort(key=lambda x: -x[0])
        return Resolution(
            "ambiguous",
            candidates=[self._describe(e, s, "token overlap") for s, e in scored[:5]],
            notes="only partial name overlap: human review required",
        )

    # ------------------------------------------------------------------ parents of branches
    def resolve_parent(self, *, parent_name: str, host_country_code: str) -> Resolution:
        """Resolve the parent bank named in 'X, SUCCURSALE DU <pays>' (always in another country)."""
        key = name_key(parent_name)
        others = [e for e in self.entities.values() if e.country_code != host_country_code and not e.is_branch]
        exact = [e for e in others if key and key in e.name_keys]
        if len(exact) == 1:
            return Resolution("matched", exact[0].id, "parent_exact_name", 0.9)
        # "CORIS BANK INTERNATIONAL (CBI) BURKINA": name + country word naming the parent's country
        from scraping.universe.normalize import country_codes_in

        named = country_codes_in(parent_name) - {host_country_code}
        ck = core_key(parent_name)
        if len(named) == 1 and ck:
            (cc,) = tuple(named)
            hits = [e for e in others if e.country_code == cc and ck in e.core_keys]
            if len(hits) == 1:
                return Resolution("matched", hits[0].id, "parent_name_and_country", 0.85)
        core = [e for e in others if ck and ck in e.core_keys]
        if len(core) == 1:
            return Resolution("matched", core[0].id, "parent_name_without_country", 0.8)
        # "SOCIÉTÉ NIGÉRIENNE DE BANK (SONIBANK)": the acronym written by the list, if unique.
        import re

        acronyms = {normalize_name(a) for a in re.findall(r"\(([^()]+)\)", parent_name)}
        by_acronym = [e for e in others if acronyms & e.acronym_keys]
        if len(by_acronym) == 1 and not exact and not core:
            return Resolution("matched", by_acronym[0].id, "parent_acronym", 0.8)
        cands = exact or core or by_acronym
        if cands:
            return Resolution("ambiguous", candidates=[self._describe(e, 0.8, "parent name") for e in cands],
                              notes="parent name matches several entities")
        return Resolution("no_match")
