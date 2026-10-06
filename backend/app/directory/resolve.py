"""
Directory name resolution (Phase 20) — EXACT names only, after typographic normalization.

A name given by an analyst (pilot manifest, mandate contacts) is matched against:
  1. institutions.name_official / name_commercial;
  2. the official / former names of the linked entity (entity_names, Phase 15 Entity Hub);
  3. entities.canonical_name / short_name (banks without an institution row, DFIs).
Comparison key = scraping.universe.normalize.normalize_name (case, accents, apostrophes,
punctuation, spaces) — the WORDS must be the same: no fuzzy match, no word dropped.
A key matching more than one record is ambiguous and resolves to nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.discovery import EntityName
from app.models.entity import Entity
from app.models.institution import Institution
from scraping.universe.normalize import normalize_name, strip_parentheticals


@dataclass(frozen=True)
class Resolved:
    institution_id: str | None
    entity_id: str | None


def keys(name: str | None) -> set[str]:
    if not name:
        return set()
    return {k for k in (normalize_name(name), normalize_name(strip_parentheticals(name))) if k}


async def resolve_names(db: AsyncSession, names: set[str]) -> dict[str, Resolved]:
    wanted = {n: keys(n) for n in names if n}
    if not wanted:
        return {}
    index: dict[str, set[tuple[str | None, str | None]]] = {}

    def add(key_names, inst_id, ent_id):
        for k in key_names:
            index.setdefault(k, set()).add((inst_id, ent_id))

    insts = (await db.execute(select(Institution.id, Institution.name_official, Institution.name_commercial,
                                     Institution.entity_id).where(Institution.deleted_at.is_(None)))).all()
    inst_by_entity = {e: i for i, _, _, e in insts if e}
    for inst_id, official, commercial, ent_id in insts:
        add(keys(official) | keys(commercial), inst_id, ent_id)
    for ent_id, name in (await db.execute(select(EntityName.entity_id, EntityName.name)
                                          .where(EntityName.deleted_at.is_(None)))).all():
        add(keys(name), inst_by_entity.get(ent_id), ent_id)
    for ent_id, canonical, short in (await db.execute(select(Entity.id, Entity.canonical_name, Entity.short_name)
                                                      .where(Entity.deleted_at.is_(None)))).all():
        add(keys(canonical) | keys(short), inst_by_entity.get(ent_id), ent_id)

    out: dict[str, Resolved] = {}
    for name, ks in wanted.items():
        hits = set().union(*(index.get(k, set()) for k in ks))
        # the same institution reached through several of its names is one hit
        records = {(i or "", e or "") for i, e in hits}
        by_entity = {e for _, e in records if e}
        by_inst = {i for i, _ in records if i}
        if len(by_inst) == 1 and len(by_entity) <= 1:
            out[name] = Resolved(next(iter(by_inst)), next(iter(by_entity), None))
        elif not by_inst and len(by_entity) == 1:
            out[name] = Resolved(None, next(iter(by_entity)))
    return out
