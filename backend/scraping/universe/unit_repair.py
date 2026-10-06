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
