"""
Coverage report (Phase 15) — rendered from PostgreSQL only (no figure is typed by hand).
Sections A-K follow the mission report template.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.discovery import UMOA_COUNTRY_CODES
from app.models.country import Country
from app.models.discovery import (
    DiscoveryGap,
    DiscoveryRound,
    DiscoveryRun,
    ReferenceUniverse,
    ReferenceUniverseMember,
)
from scraping.universe.coverage import CoverageSnapshot, compute_coverage


def _pct(value: float | None) -> str:
    return "UNKNOWN" if value is None else f"{value * 100:.1f} %"


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join("" if c is None else str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


async def build_report(db: AsyncSession, universe_code: str, run_id: str | None = None) -> str:
    snap = await compute_coverage(db, universe_code)
    names = {c.code: c.name_en for c in (await db.execute(select(Country))).scalars().all()}
    run = await _run(db, universe_code, run_id)
    rounds = [] if run is None else (await db.execute(
        select(DiscoveryRound).where(DiscoveryRound.run_id == run.id).order_by(DiscoveryRound.round_number)
    )).scalars().all()
    lines: list[str] = [f"# Coverage report — {universe_code}", ""]
    lines += _reference(snap, run)
    lines += await _snapshot_changes(db, universe_code)
    lines += _section_a(snap, names)
    lines += _section_b(snap)
    lines += _section_c(snap)
    lines += _section_d(snap)
    lines += _section_e(snap)
    lines += _section_f(snap)
    lines += _institutional(snap, names)
    lines += await _documents(db)
    lines += _gap_lists(snap)
    lines += _ambiguities(snap, rounds)
    lines += _rounds(rounds)
    lines += await _gap_queue(db)
    lines += _orphans(snap)
    return "\n".join(lines)


async def _snapshot_changes(db: AsyncSession, universe_code: str) -> list[str]:
    """Registration numbers added / absent between the two most recent official snapshots."""
    umoa = (await db.execute(select(ReferenceUniverse).where(
        ReferenceUniverse.universe_code == universe_code, ReferenceUniverse.country_id.is_(None),
        ReferenceUniverse.status.in_(("COMPLETE", "INCOMPLETE", "UNKNOWN")), ReferenceUniverse.deleted_at.is_(None),
    ))).scalars().all()
    ordered = sorted((u for u in umoa if u.reference_date), key=lambda u: u.reference_date)
    if len(ordered) < 2:
        return []
    previous, current = ordered[-2], ordered[-1]

    async def lines_of(snapshot: ReferenceUniverse) -> dict[str, tuple[str, str]]:
        rows = (await db.execute(
            select(ReferenceUniverseMember, Country.code)
            .join(ReferenceUniverse, ReferenceUniverse.id == ReferenceUniverseMember.universe_id)
            .join(Country, Country.id == ReferenceUniverse.country_id)
            .where(ReferenceUniverse.reference_document_id == snapshot.reference_document_id,
                   ReferenceUniverseMember.category == "bank", ReferenceUniverseMember.deleted_at.is_(None))
        )).all()
        return {m.registration_number or m.normalized_name: (cc, m.official_name) for m, cc in rows}

    before, after = await lines_of(previous), await lines_of(current)
    added = sorted((after[k][0], k, after[k][1]) for k in after.keys() - before.keys())
    absent = sorted((before[k][0], k, before[k][1]) for k in before.keys() - after.keys())
    out = [f"## Changes between official snapshots ({previous.reference_date} → {current.reference_date})", ""]
    out.append(f"Listed in {current.reference_date} but not in {previous.reference_date} ({len(added)}):")
    out += ["", _table(["Country", "Registration", "Official line"], [list(r) for r in added]) if added else "None.", ""]
    out.append(f"Listed in {previous.reference_date} but absent from {current.reference_date} ({len(absent)}) — "
               "entities are kept, never deleted; the reason (radiation, conversion, merger) is not inferred:")
    out += ["", _table(["Country", "Registration", "Official line"], [list(r) for r in absent]) if absent else "None.", ""]
    return out


async def _run(db, universe_code, run_id) -> DiscoveryRun | None:
    if run_id:
        return await db.get(DiscoveryRun, run_id)
    return (await db.execute(select(DiscoveryRun).where(DiscoveryRun.universe_code == universe_code)
                             .order_by(DiscoveryRun.started_at.desc()).limit(1))).scalar_one_or_none()


def _reference(snap: CoverageSnapshot, run: DiscoveryRun | None) -> list[str]:
    out = ["## Official reference", ""]
    if not snap.reference_available:
        out += ["**COVERAGE INCOMPLETE — no self-consistent official reference list is available.**", ""]
    else:
        out += [
            f"- Current reference: **{snap.reference_title}** ({snap.reference_source}), reference date "
            f"**{snap.reference_date}**, status **{snap.reference_status}**",
            f"- URL: {snap.reference_url}",
            f"- Expected banks: **{snap.expected_total}** — evidence: {snap.expected_evidence}",
            "",
        ]
    if snap.snapshots:
        out += ["All official snapshots processed:", "",
                _table(["Reference date", "Source", "Expected", "Parsed lines", "Resolved", "Status", "Current"],
                       [[s["reference_date"], s["source"], s["expected"], s["discovered"], s["matched"],
                         s["status"], "yes" if s["is_current"] else ""] for s in snap.snapshots]), ""]
    if run is not None:
        out += [f"- Last run: `{run.id}` started {run.started_at:%Y-%m-%d %H:%M:%S} UTC, finished "
                f"{run.finished_at:%Y-%m-%d %H:%M:%S} UTC" if run.finished_at else f"- Last run: `{run.id}` (running)",
                f"- Stop condition: **{run.stop_condition}** — {run.stop_reason}", ""]
    return out


def _section_a(snap, names) -> list[str]:
    rows = []
    for cc in UMOA_COUNTRY_CODES:
        c = snap.countries.get(cc)
        if c is None:
            rows.append([names.get(cc, cc), "UNKNOWN", 0, "UNKNOWN", "UNKNOWN"])
            continue
        missing = None if c.expected is None else max(c.expected - c.matched, 0)
        rows.append([names.get(cc, cc), c.expected if c.expected is not None else "UNKNOWN", c.matched,
                     missing if missing is not None else "UNKNOWN", _pct(c.entity_ratio)])
    return ["## A. Universe (banks per country)", "",
            _table(["Country", "Expected Banks", "Discovered Banks", "Missing Banks", "Coverage %"], rows), ""]


def _section_b(snap) -> list[str]:
    return ["## B. Entity coverage", "",
            _table(["Expected", "Parsed official lines", "Discovered (resolved in Entity Hub)", "Coverage %"],
                   [[snap.expected_total if snap.expected_total is not None else "UNKNOWN", snap.discovered_total,
                     snap.matched_total, _pct(snap.entity_ratio)]]), ""]


def _level_row(snap, label, key):
    lv = snap.level(key)
    return [label, lv["entities"], lv["found"], lv["missing"], _pct(lv["ratio"])]


def _section_c(snap) -> list[str]:
    web = Counter(e.website_status for e in snap.entities)
    return ["## C. Source coverage", "",
            _table(["Source level", "Entities", "Found", "Missing", "Coverage %"], [
                _level_row(snap, "Regulatory source (BCEAO / CB-UMOA listing)", "regulatory_source"),
                _level_row(snap, "Institution-owned official source (website / publications)", "official_own_source"),
                _level_row(snap, "Official website VERIFIED or ACTIVE", "website_verified"),
                _level_row(snap, "Market infrastructure (BRVM)", "market_listing"),
            ]), "",
            "Official website status breakdown: " + ", ".join(
                f"{k}={web.get(k, 0)}" for k in ("ACTIVE", "VERIFIED", "FOUND", "BLOCKED", "NOT_FOUND", "UNKNOWN")),
            ""]


def _section_d(snap) -> list[str]:
    reg = snap.level("regulatory_document")
    inst = snap.level("institution_specific_document")
    return ["## D. Document coverage (regulatory aggregate ≠ institution-specific)", "",
            _table(["Level", "Entities", "Found", "Missing", "Coverage %"], [
                ["Regulatory document coverage (aggregated regulatory publication, e.g. BCEAO fascicle)",
                 reg["entities"], reg["found"], reg["missing"], _pct(reg["ratio"])],
                ["Institution-specific document coverage (published by the institution itself)",
                 inst["entities"], inst["found"], inst["missing"], _pct(inst["ratio"])],
            ]), "",
            f"Institution-specific document coverage is {inst['found']}/{inst['entities']}. A regulatory publication "
            "covering many institutions is NOT counted as an institution's own financial document.", ""]


def _section_e(snap) -> list[str]:
    obs = snap.level("financial_observation")
    by_scope = snap.observations_by_document_scope
    total = sum(by_scope.values())
    lines = ["## E. Financial observation coverage", "",
             _table(["Entities", "With ≥1 non-rejected observation", "Without", "Coverage %"],
                    [[obs["entities"], obs["found"], obs["missing"], _pct(obs["ratio"])]]), "",
             "Observations by document scope: " + (", ".join(f"{k}={v}" for k, v in by_scope.items()) or "none"),
             ""]
    if total and by_scope.get("regulatory_aggregate", 0) == total:
        lines += [f"All {total} observations come from an aggregated regulatory publication (one page per licensed "
                  "institution), not from financial reports published individually by the banks.", ""]
    lines += ["### Per-metric coverage (banking catalogue)", "",
              _table(["Metric", "Banks with", "Banks without", "verified", "reviewed", "needs_review", "extracted",
                      "rejected", "negative", "zero"],
                     [[m["metric"], m["entities_with"], m["entities_without"], m["verified"], m["reviewed"],
                       m["needs_review"], m["extracted"], m["rejected"], m["negative"], m["zero"]]
                      for m in snap.metric_table]), ""]
    return lines


def _section_f(snap) -> list[str]:
    obs = snap.observation_status_counts
    lv = snap.level("financial_validation")
    prov = snap.provenance
    return ["## F. Financial validation coverage", "",
            _table(["Observations", "Verified", "Reviewed", "Needs Review", "Extracted", "Rejected"],
                   [[sum(obs.values()), obs.get("verified", 0), obs.get("reviewed", 0), obs.get("needs_review", 0),
                     obs.get("extracted", 0), obs.get("rejected", 0)]]), "",
            f"Entities with at least one verified observation: {lv['found']} / {lv['entities']} ({_pct(lv['ratio'])})",
            "",
            "### Scope evidence (A/B explicit → may be extracted; C inferred / D none → needs_review)", "",
            _table(["Class", "Observations"], [[k, v] for k, v in snap.scope_class_counts.items()]), "",
            _table(["Reason code", "Observations"], [[k, v] for k, v in snap.reason_code_counts.items()]), "",
            "### Quality flags (informative; values never modified)", "",
            _table(["Flag", "Observations"], [[k, v] for k, v in snap.quality_flag_counts.items()])
            if snap.quality_flag_counts else "None.", "",
            "### Provenance (observation → document → source → URL → page → location → method)", "",
            _table(["Observations", "Complete", "Missing URL", "Missing hash", "Missing page", "Missing location",
                    "Missing method"],
                   [[prov.get("observations", 0), prov.get("complete", 0), prov.get("missing_url", 0),
                     prov.get("missing_hash", 0), prov.get("missing_page", 0), prov.get("missing_location", 0),
                     prov.get("missing_method", 0)]]), ""]


def _entity_list(entities, title: str, extra) -> list[str]:
    out = [f"### {title} ({len(entities)})", ""]
    if not entities:
        return out + ["None.", ""]
    out.append(_table(["Country", "Entity", "Registration", "Detail"],
                      [[e.country_code, e.name, e.registration_number, extra(e)] for e in entities]))
    return out + [""]


def _gap_lists(snap) -> list[str]:
    out = ["## G. Source gaps", ""]
    out += _entity_list([e for e in snap.entities if not e.regulatory_listing],
                        "Entities without regulatory source", lambda e: "")
    out += _entity_list([e for e in snap.entities if not e.official_own_source],
                        "Entities without institution-owned official source (website / publications)",
                        lambda e: f"website {e.website_status}")
    out += ["## H. Document gaps", ""]
    out += _entity_list([e for e in snap.entities if not e.has_financial_document],
                        "Entities without financial document", lambda e: "")
    out += ["## I. Data gaps", ""]
    out += _entity_list([e for e in snap.entities if not e.has_financial_data],
                        "Entities without financial data", lambda e: "")
    return out


def _ambiguities(snap, rounds) -> list[str]:
    out = ["## J. Ambiguities (human resolution required)", ""]
    missing = [m for c in snap.countries.values() for m in c.missing]
    out += [f"### Official list lines not resolved ({len(missing)})", ""]
    if missing:
        out.append(_table(["Country", "Official line", "Registration", "Status", "Candidates / notes"], [
            [m.country_code, m.official_name, m.registration_number, m.resolution_status,
             "; ".join(f"{c.get('name')} ({c.get('reason')})" for c in (m.candidates or [])) or (m.notes or "")]
            for m in missing]))
    else:
        out.append("None.")
    out.append("")
    fascicle = [r for r in rounds if r.strategy_code == "bceao_regulatory_fascicle" and r.details]
    if fascicle:
        editions = fascicle[-1].details.get("editions", [])
        for ed in editions:
            amb, unres = ed.get("ambiguous", []), ed.get("unresolved", [])
            out += [f"### Regulatory fascicle labels not linked — {ed.get('url')}", "",
                    f"Institutions in document: {ed.get('institutions_in_document')} — linked to the bank universe: "
                    f"{len(ed.get('linked', []))} — ambiguous: {len(amb)} — no match: {len(unres)} "
                    "(no match = financial establishments outside the bank universe, closed/renamed banks, or "
                    "labels too different to link safely)", ""]
            if amb:
                out.append(_table(["Country", "Label in document", "Pages", "Candidates"], [
                    [a["country"], a["label"], a["pages"],
                     "; ".join(str(c.get("name", c)) if isinstance(c, dict) else str(c) for c in a["candidates"])]
                    for a in amb]))
                out.append("")
            if unres:
                out.append(_table(["Country", "Label in document (no match)", "Pages"],
                                  [[u["country"], u["label"], u["pages"]] for u in unres]))
                out.append("")
    return out


def _rounds(rounds) -> list[str]:
    out = ["## K. Search rounds", ""]
    rows = []
    for r in rounds:
        b, a = r.coverage_before or {}, r.coverage_after or {}

        def lv(d, k):
            v = (d.get("levels") or {}).get(k) or {}
            return f"{v.get('found', 0)}/{v.get('entities', 0)}"

        rows.append([r.round_number, r.strategy_code, r.targets_count, r.sources_found, r.new_entities,
                     r.new_documents, r.new_document_links, r.new_observations,
                     f"{b.get('matched', 0)}/{b.get('expected')}", f"{a.get('matched', 0)}/{a.get('expected')}",
                     f"{lv(b, 'financial_document')} → {lv(a, 'financial_document')}",
                     f"{lv(b, 'financial_data')} → {lv(a, 'financial_data')}",
                     len(r.errors or [])])
    out.append(_table(["#", "Strategy", "Targets", "Sources found", "New entities", "New docs", "Doc links",
                       "New observations", "Entities before", "Entities after", "Docs cov.", "Data cov.",
                       "Errors"], rows))
    return out + [""]


async def _gap_queue(db) -> list[str]:
    gaps = (await db.execute(select(DiscoveryGap).where(DiscoveryGap.deleted_at.is_(None)))).scalars().all()
    counts = Counter((g.gap_type, g.status) for g in gaps)
    types = sorted({t for t, _ in counts})
    statuses = ("OPEN", "SEARCHING", "NOT_FOUND", "BLOCKED", "RESOLVED")
    last = max((g.last_attempt_at for g in gaps if g.last_attempt_at), default=None)
    out = ["## Source gap queue", "", f"Last attempt: {last}", "",
           _table(["Gap type", *statuses], [[t, *[counts.get((t, s), 0) for s in statuses]] for t in types]), ""]
    return out


def _orphans(snap) -> list[str]:
    out = [f"## Entities outside the official universe ({len(snap.orphan_institutions)})", "",
           "Financial institutions in the Entity Hub that no official list line supports (demo / legacy rows). "
           "They are excluded from every coverage figure.", ""]
    if snap.orphan_institutions:
        out.append(_table(["Entity", "Type", "Country"],
                          [[o["name"], o["entity_type"], o["country"]] for o in snap.orphan_institutions]))
    return out + [""]


LEVELS_17 = (
    ("Entity coverage", None),
    ("Official source coverage (institutional source found, any status)", "official_source_found"),
    ("Verified source coverage (website / publications / BRVM, VERIFIED or ACTIVE)", "verified_source"),
    ("Institutional document coverage", "institution_specific_document"),
    ("Machine-readable institutional document coverage", "machine_readable_document"),
    ("Regulatory document coverage (aggregated BCEAO fascicle)", "regulatory_document"),
    ("Financial observation coverage", "financial_observation"),
    ("needs_review coverage", "needs_review_data"),
    ("extracted coverage", "extracted_data"),
    ("reviewed coverage", "reviewed_data"),
    ("verified coverage", "financial_validation"),
)


def _institutional(snap, names) -> list[str]:
    out = ["## Institution-specific coverage (Phase 17)", ""]
    rows = []
    for label, key in LEVELS_17:
        if key is None:
            rows.append([label, snap.expected_total, snap.matched_total, _pct(snap.entity_ratio)])
        else:
            lv = snap.level(key)
            rows.append([label, lv["entities"], lv["found"], _pct(lv["ratio"])])
    out += [_table(["Level", "Entities", "Found", "Coverage %"], rows), ""]
    by_cc: dict[str, list] = {}
    for e in snap.entities:
        by_cc.setdefault(e.country_code, []).append(e)
    crow = []
    for cc in UMOA_COUNTRY_CODES:
        es = by_cc.get(cc, [])
        crow.append([names.get(cc, cc), len(es), sum(e.institutional_source for e in es),
                     sum(e.institution_documents > 0 for e in es), sum(e.machine_readable_documents > 0 for e in es),
                     sum(e.regulatory_documents > 0 for e in es), sum(e.has_financial_data for e in es),
                     sum(e.has_verified_data for e in es)])
    out += ["### Coverage by country", "",
            _table(["Country", "Banks", "Verified source", "Institutional docs", "Machine-readable docs",
                    "Regulatory docs", "Observations", "Verified"], crow), ""]
    out += ["### Matrix of the 137 banks", "",
            "Legend: Reg = regulatory listing; Web = official website status; BRVM = market source; Parent = parent "
            "bank has a verified source; Docs = institution-specific documents (machine-readable / analysed); "
            "Obs = observations (needs_review / extracted / verified).", ""]
    mrows = []
    for e in sorted(snap.entities, key=lambda e: (e.country_code, e.name)):
        o = e.observations
        mrows.append([
            e.country_code, e.name[:60], e.registration_number, "yes" if e.regulatory_listing else "no",
            e.website_status, "yes" if (e.market_listing or e.market_filings) else "-",
            ("yes" if e.parent_has_source else "no") if e.parent_name else "-",
            f"{e.institution_documents} ({e.machine_readable_documents}/{e.analysed_documents})",
            e.latest_document_year or "-", e.regulatory_documents,
            f"{o.get('needs_review', 0)}/{o.get('extracted', 0)}/{o.get('verified', 0)}",
            ", ".join(sorted(g.split(":")[0] for g in e.gaps)) or "-",
            (e.last_attempt_at or "-")[:10], (e.next_attempt_at or "-")[:10],
        ])
    out += [_table(["CC", "Bank", "Registration", "Reg", "Web", "BRVM", "Parent", "Docs (mr/an)", "Last year",
                    "Reg. docs", "Obs nr/ex/ver", "Open gaps", "Last attempt", "Next retry"], mrows), ""]
    return out


async def _documents(db) -> list[str]:
    from app.models.document import Document

    docs = (await db.execute(select(Document).where(Document.deleted_at.is_(None)))).scalars().all()
    inst = [d for d in docs if d.document_scope == "institution_specific"]
    tl = Counter(d.text_layer_status for d in inst)
    out = ["## Documents", "",
           _table(["Documents (all)", "Institution-specific", "machine_readable", "partially_corrupted",
                   "not_machine_readable (scanned)", "unknown", "analysed", "with observations"],
                  [[len(docs), len(inst), tl.get("machine_readable", 0), tl.get("partially_corrupted", 0),
                    tl.get("not_machine_readable", 0), tl.get("unknown", 0),
                    sum(1 for d in inst if d.extracted_at), sum(1 for d in inst if d.extraction_status == "extracted")]]),
           "", "Document scope breakdown: " + ", ".join(f"{k}={v}" for k, v in sorted(
               Counter(d.document_scope for d in docs).items())), ""]
    return out
