"""
Quality flags (Phase 16) — informative only.

A flag NEVER changes a value. A blocking flag (app.constants.quality.BLOCKING_QUALITY_FLAGS)
prevents any automatic promotion; it never changes a human status.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.constants.quality import BLOCKING_QUALITY_FLAGS
from app.models.document import Document
from app.models.financial_data import FinancialData

STRUCTURAL_ZERO_METRICS = ("total_actifs",)


def has_blocking_flag(flags: list[dict] | None) -> bool:
    return any(f.get("code") in BLOCKING_QUALITY_FLAGS for f in flags or [])


def merge_flags(existing: list[dict] | None, new: list[dict]) -> list[dict] | None:
    """Idempotent merge keyed by (code, detail)."""
    out = {(f["code"], f.get("detail")): f for f in existing or []}
    for f in new:
        out[(f["code"], f.get("detail"))] = f
    return sorted(out.values(), key=lambda f: (f["code"], f.get("detail") or "")) or None


def value_flags(rows: list[FinancialData]) -> dict[str, list[dict]]:
    """Flags derived from the values of one entity in one document (row id → flags)."""
    by_key: dict[tuple[str, int], FinancialData] = {(r.metric_code, r.period_year): r for r in rows}
    flags: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        v = r.value_normalized
        if v is None:
            continue
        if r.metric_code in STRUCTURAL_ZERO_METRICS and v == 0:
            flags[r.id].append({"code": "zero_on_structural_metric",
                                "detail": f"{r.metric_code} = 0 printed for {r.period_year}"})
        if r.metric_code == "depots_clients" and v == 0:
            total = by_key.get(("total_actifs", r.period_year))
            if total is not None and total.value_normalized and total.value_normalized > 0:
                flags[r.id].append({"code": "zero_on_structural_metric",
                                    "detail": f"depots_clients = 0 while total_actifs > 0 ({r.period_year})"})
        if r.metric_code == "capitaux_propres" and v < 0:
            flags[r.id].append({"code": "negative_equity", "detail": f"capitaux_propres < 0 ({r.period_year})"})
    return flags


def cross_statement_flags(rows: list[FinancialData], balance_sheet_results: dict[int, Decimal]) -> dict[str, list[dict]]:
    """P&L RESULTAT NET vs balance-sheet RESULTAT DE L'EXERCICE (both printed, millions)."""
    flags: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        if r.metric_code != "resultat_net" or r.period_year not in balance_sheet_results:
            continue
        printed = Decimal(r.value_original.replace(" ", "").replace(chr(0x2212), "-"))
        if printed != balance_sheet_results[r.period_year]:
            flags[r.id].append({
                "code": "cross_statement_mismatch",
                "detail": f"{r.period_year}: income statement {printed} vs balance sheet "
                          f"{balance_sheet_results[r.period_year]} (millions)",
            })
    return flags


async def cross_edition_flags(db: AsyncSession, entity_id: str) -> dict[str, list[dict]]:
    """Same entity / metric / year read in two regulatory editions with different values."""
    rows = (await db.execute(
        select(FinancialData).join(Document, Document.id == FinancialData.document_id).where(
            FinancialData.entity_id == entity_id, FinancialData.deleted_at.is_(None),
            Document.document_scope == "regulatory_aggregate",
        )
    )).scalars().all()
    groups: dict[tuple[str, int, str], list[FinancialData]] = defaultdict(list)
    for r in rows:
        groups[(r.metric_code, r.period_year, r.period_type)].append(r)
    flags: dict[str, list[dict]] = defaultdict(list)
    for (metric, year, _pt), group in groups.items():
        if len({g.document_id for g in group}) < 2:
            continue
        values = {g.value_normalized for g in group}
        if len(values) > 1:
            for g in group:
                flags[g.id].append({"code": "cross_edition_mismatch",
                                    "detail": f"{metric} {year}: {sorted(str(v) for v in values)} across editions"})
    return flags
