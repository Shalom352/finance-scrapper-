"""
Re-read the stated unit of institution statements already extracted.

Extraction never rewrites an existing row ("an existing row of the same document keeps its value"),
so a parser fix on unit detection does not reach rows stored before it. This repair re-parses each
institution document and, for each row it produced whose stated unit / currency differs from what the
document actually states, corrects the unit and the normalized value. It never touches a human-protected
row (reviewed / verified / rejected), never changes a status and never touches the raw value read
from the page. Each correction is written into the row's notes (before → after) and flagged
``unit_reread`` (non-blocking).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.financial_data import FinancialData
from scraping.pipeline import PROTECTED_STATUSES
from scraping.quality.checks import merge_flags
from scraping.universe.documents import DocumentRegistrar
from scraping.universe.institution_statements import InstitutionStatementParser

UNIT_NOT_STATED = "unit_or_currency_not_stated"


@dataclass
class UnitRepairReport:
    documents_read: int = 0
    documents_missing: list[str] = field(default_factory=list)
    corrected: list[dict] = field(default_factory=list)
    protected_skipped: int = 0

    def summary(self) -> dict:
        return {"documents_read": self.documents_read, "documents_missing": len(self.documents_missing),
                "corrected": len(self.corrected), "protected_skipped": self.protected_skipped,
                "examples": self.corrected[:20]}


async def reread_units(db: AsyncSession, registrar: DocumentRegistrar, *, dry_run: bool = True) -> UnitRepairReport:
    report = UnitRepairReport()
    docs = (await db.execute(select(Document).where(
        Document.document_scope == "institution_specific", Document.extracted_at.is_not(None),
        Document.deleted_at.is_(None)))).scalars().all()
    for doc in docs:
        rows = (await db.execute(select(FinancialData).where(
            FinancialData.document_id == doc.id, FinancialData.extraction_method == "pdf_text",
            FinancialData.deleted_at.is_(None)))).scalars().all()
        if not rows:
            continue
        content = registrar.read_bytes(doc)
        if content is None:
            report.documents_missing.append(doc.id)
            continue
        report.documents_read += 1
        parsed = InstitutionStatementParser().parse_bytes(content, doc.title or "")
        stated = {(v.metric_code, v.year, v.raw.replace(" ", "")): v for v in parsed.values}
        for r in rows:
            v = stated.get((r.metric_code, r.period_year, (r.value_original or "").replace(" ", "")))
            if v is None or (v.unit, v.currency) == (r.unit_original, r.currency_original):
                continue
            if r.status in PROTECTED_STATUSES:
                report.protected_skipped += 1
                continue
            before = (r.unit_original, r.value_normalized)
            after_value = (v.value * v.multiplier) if v.multiplier is not None else None
            report.corrected.append({"data_id": r.id, "document": (doc.title or "")[:80], "metric": r.metric_code,
                                     "year": r.period_year, "raw": r.value_original,
                                     "unit": f"{before[0]} -> {v.unit}",
                                     "normalized": f"{before[1]} -> {after_value}"})
            r.unit_original, r.currency_original = v.unit, v.currency
            r.value_normalized = after_value
            r.unit_normalized = "absolute" if after_value is not None else None
            r.currency_normalized = v.currency
            kept = [f for f in r.quality_flags or [] if f.get("code") != UNIT_NOT_STATED]
            if v.unit is None or v.currency is None:
                kept.append({"code": UNIT_NOT_STATED,
                             "detail": f"p.{v.page_number}: the statement does not state its unit / currency"})
            note = (f"unit re-read p.{v.page_number}: {before[0]} -> {v.unit}; "
                    f"normalized {before[1]} -> {after_value}")
            r.quality_flags = merge_flags(kept, [{"code": "unit_reread", "detail": note}])
            r.notes = f"{r.notes} | {note}"[:4000] if r.notes else note
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report


# ====================================================================== fascicle corroboration
CORROBORATION_REASON = "scope_corroborated_by_regulatory_fascicle"
UNIT_BY_FACTOR = {Decimal(1): "unit", Decimal(1_000): "thousands", Decimal(1_000_000): "millions"}
# The fascicle publishes millions rounded (sometimes truncated): ±2.5 million, or 0.05 % for large values.
ABS_TOLERANCE = Decimal(2_500_000)
REL_TOLERANCE = Decimal("0.0005")


def _agrees(candidate: Decimal, reference: Decimal) -> bool:
    return abs(candidate - reference) <= max(ABS_TOLERANCE, abs(reference) * REL_TOLERANCE)


def _raw_decimal(raw: str | None) -> Decimal | None:
    from scraping.universe.fascicle import parse_amount

    return parse_amount(raw or "")


@dataclass
class CorroborationReport:
    unit_set: list[dict] = field(default_factory=list)
    scope_set: list[dict] = field(default_factory=list)
    disagreements: list[dict] = field(default_factory=list)
    protected_skipped: int = 0

    def summary(self) -> dict:
        return {"unit_established": len(self.unit_set), "scope_established": len(self.scope_set),
                "disagreements": len(self.disagreements), "protected_skipped": self.protected_skipped,
                "examples": (self.unit_set + self.scope_set)[:15], "disagreement_examples": self.disagreements[:15]}


async def corroborate_with_fascicle(db: AsyncSession, *, dry_run: bool = True) -> CorroborationReport:
    """Institution-document rows lacking a stated unit or a scope proof are compared with the BCEAO
    fascicle (same institution, metric, fiscal year). Agreement within the fascicle's rounding
    establishes the unit (the only power of 1000 that agrees) and the per-entity scope (class C,
    never stronger than the fascicle). A disagreement changes nothing and is reported."""
    from app.constants.quality import FASCICLE_CONVENTION_REASON

    report = CorroborationReport()
    fascicle = (await db.execute(select(FinancialData).where(
        FinancialData.scope_reason_code == FASCICLE_CONVENTION_REASON, FinancialData.period_type == "annual",
        FinancialData.value_normalized.is_not(None), FinancialData.status != "rejected",
        FinancialData.deleted_at.is_(None)))).scalars().all()
    reference: dict[tuple, list[FinancialData]] = {}
    for f in fascicle:
        if f.institution_id:
            reference.setdefault((f.institution_id, f.metric_code, f.period_year), []).append(f)

    candidates = (await db.execute(select(FinancialData).join(Document, Document.id == FinancialData.document_id).where(
        Document.document_scope == "institution_specific", FinancialData.extraction_method == "pdf_text",
        FinancialData.period_type == "annual", FinancialData.institution_id.is_not(None),
        FinancialData.deleted_at.is_(None)))).scalars().all()
    for r in candidates:
        needs_unit = r.value_normalized is None
        needs_scope = r.scope_evidence_class not in ("A", "B", "C")
        if not (needs_unit or needs_scope):
            continue
        refs = reference.get((r.institution_id, r.metric_code, r.period_year), [])
        values = {Decimal(str(f.value_normalized)) for f in refs}
        if len(values) != 1:  # no fascicle value, or two editions disagree: nothing is proven
            continue
        (ref_value,) = values
        if ref_value == 0:
            continue
        ref = refs[0]
        if r.status in PROTECTED_STATUSES:
            report.protected_skipped += 1
            continue
        where = f"BCEAO fascicle p.{ref.page_number} ({ref.id})"
        if needs_unit:
            raw = _raw_decimal(r.value_original)
            factors = [k for k in UNIT_BY_FACTOR if raw is not None and _agrees(raw * k, ref_value)]
            if len(factors) != 1:
                report.disagreements.append({"data_id": r.id, "metric": r.metric_code, "year": r.period_year,
                                             "raw": r.value_original, "fascicle": str(ref_value)})
                continue
            k = factors[0]
            r.unit_original, r.currency_original = UNIT_BY_FACTOR[k], "XOF"
            r.value_normalized, r.unit_normalized, r.currency_normalized = raw * k, "absolute", "XOF"
            flags = [f for f in r.quality_flags or [] if f.get("code") != UNIT_NOT_STATED]
            detail = f"unit '{UNIT_BY_FACTOR[k]}' established: {r.value_original} x {k} agrees with {where} = {ref_value}"
            r.quality_flags = merge_flags(flags, [{"code": "unit_corroborated", "detail": detail}])
            r.notes = f"{r.notes} | {detail}"[:4000] if r.notes else detail
            report.unit_set.append({"data_id": r.id, "metric": r.metric_code, "year": r.period_year,
                                    "raw": r.value_original, "unit": UNIT_BY_FACTOR[k]})
        elif not _agrees(Decimal(str(r.value_normalized)), ref_value):
            report.disagreements.append({"data_id": r.id, "metric": r.metric_code, "year": r.period_year,
                                         "value": str(r.value_normalized), "fascicle": str(ref_value)})
            continue
        if needs_scope:
            r.scope_evidence_class, r.scope_reason_code = "C", CORROBORATION_REASON
            r.scope_evidence = f"value equal to {where}; the fascicle publishes per-entity (individual) statements"
            r.scope = r.consolidation_scope = "individual"
            report.scope_set.append({"data_id": r.id, "metric": r.metric_code, "year": r.period_year})
    if dry_run:
        await db.rollback()
    else:
        await db.commit()
    return report
