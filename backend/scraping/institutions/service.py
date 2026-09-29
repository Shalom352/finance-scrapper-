"""
InstitutionProfileService — financial profile of one institution (Phase 10).

Every value comes from the existing qualification layer:
  - published metrics: rankings.eligibility.qualify_metric → EligibilityEngine
    (rejected excluded, verified wins, conflicts and needs_review not certified);
  - ratios / growth: AnalyticsService (RatioCalculator / GrowthCalculator rules);
  - coverage: CoverageAnalyzer fed ONLY with the qualified values of the selection;
  - data quality: Phase 6 quality counters, never the overall score.
One selection = one period_type and one data_scope (defaults annual + individual):
nothing is mixed, nothing is converted, missing data stays unavailable.
"""
from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_data import FinancialData
from scraping.analytics.aggregation import SECTOR_PERIOD_TYPE, SECTOR_SCOPE
from scraping.analytics.analytics_service import AnalyticsService
from scraping.consolidation.consolidator import FinancialDataConsolidator
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import ObservationSummary
from scraping.institutions.models import (
    DataQualityCounts,
    HistoryPoint,
    HistorySeries,
    InstitutionCoverage,
    InstitutionFinancials,
    InstitutionGrowth,
    InstitutionHistory,
    InstitutionRatios,
    ProfileValue,
    Selection,
    SourceDocument,
    UnavailableValue,
)
from scraping.rankings.eligibility import provenance_from_observation, qualify_metric

# Always listed on the profile (value or explicit unavailability), in this order.
PRIORITY_METRICS = (
    "total_actifs",
    "depots_clients",
    "creances_clients",
    "capitaux_propres",
    "produit_net_bancaire",
    "resultat_net",
)

_ALL = 10**6


class InstitutionProfileService:
    def __init__(self) -> None:
        self.analytics = AnalyticsService()
        self.engine = self.analytics.sector_aggregator.eligibility
        self.detector = DuplicateDetector()
        self.consolidator = FinancialDataConsolidator()

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    async def observations(self, db: AsyncSession, institution_id: str) -> list[ObservationSummary]:
        """Every stored (non-deleted) observation of the institution, all statuses."""
        query = (
            select(FinancialData)
            .options(selectinload(FinancialData.source), selectinload(FinancialData.document))
            .where(FinancialData.institution_id == institution_id, FinancialData.deleted_at.is_(None))
        )
        rows = (await db.execute(query)).scalars().all()
        return [self.detector.observation_from_orm(r) for r in rows]

    # ------------------------------------------------------------------
    # Pure helpers (unit-testable without a database)
    # ------------------------------------------------------------------

    @staticmethod
    def selection(obs: list[ObservationSummary]) -> Selection:
        usable = [o for o in obs if o.status != "rejected" and o.value_normalized is not None]
        return Selection(
            scopes=sorted({o.scope for o in usable if o.scope}),
            period_types=sorted({o.period_type for o in usable if o.period_type}),
            years=sorted({o.period_year for o in usable}, reverse=True),
        )

    @staticmethod
    def select_rows(obs: list[ObservationSummary], period_type: str, data_scope: str) -> list[ObservationSummary]:
        """One period type and one scope — never mixed."""
        return [o for o in obs if o.period_type == period_type and o.scope == data_scope]

    def qualify(
        self, rows: list[ObservationSummary]
    ) -> tuple[dict[tuple[str, int], ProfileValue], dict[tuple[str, int], UnavailableValue]]:
        """One authoritative value per (metric, year) via the existing eligibility rules."""
        by_key: dict[tuple[str, int], list[ObservationSummary]] = defaultdict(list)
        for o in rows:
            by_key[(o.metric_code, o.period_year)].append(o)

        values: dict[tuple[str, int], ProfileValue] = {}
        unavailable: dict[tuple[str, int], UnavailableValue] = {}
        for (metric, year), group in by_key.items():
            cand = qualify_metric("", group, self.engine)
            if not cand.eligible:
                unavailable[(metric, year)] = UnavailableValue(
                    metric_code=metric, period_year=year, status=cand.status, reason=cand.reason or "missing"
                )
                continue
            best = next(o for o in group if o.id == cand.data_id)
            values[(metric, year)] = ProfileValue(
                metric_code=metric,
                period_year=year,
                period_type=best.period_type,
                period_label=best.period_label,
                data_scope=best.scope or "",
                value_original=best.value_original,
                unit_original=best.unit_original,
                currency_original=best.currency_original,
                value_normalized=best.value_normalized,
                unit_normalized=best.unit_normalized,
                currency=best.currency_normalized,
                status=best.status,
                data_id=best.id,
                provenance=provenance_from_observation(best),
            )
        return values, unavailable

    # ------------------------------------------------------------------
    # Financials (one year)
    # ------------------------------------------------------------------

    def build_financials(
        self,
        institution_id: str,
        obs: list[ObservationSummary],
        *,
        period_year: int | None,
        period_type: str,
        data_scope: str,
        indicator: str | None = None,
    ) -> InstitutionFinancials:
        sel = self.selection(obs)
        rows = self.select_rows(obs, period_type, data_scope)
        values, unavailable = self.qualify(rows)
        qualified_years = sorted({y for (_, y) in values}, reverse=True)
        year = period_year if period_year is not None else (qualified_years[0] if qualified_years else None)

        base = dict(institution_id=institution_id, period_type=period_type, data_scope=data_scope, selection=sel)
        if year is None:
            reason = "no_data" if not obs else "no_data_for_selection"
            missing = [UnavailableValue(metric_code=m, status="unavailable", reason=reason) for m in PRIORITY_METRICS]
            return InstitutionFinancials(**base, period_year=None, status="unavailable", reason=reason, values=[],
                                         unavailable=missing if indicator is None else [])

        metrics = list(PRIORITY_METRICS) + sorted({m for (m, _) in values} | {m for (m, _) in unavailable})
        metrics = list(dict.fromkeys(metrics))
        if indicator:
            metrics = [m for m in metrics if m == indicator] or [indicator]

        out_values, out_missing = [], []
        for m in metrics:
            if (m, year) in values:
                out_values.append(values[(m, year)])
            elif (m, year) in unavailable:
                out_missing.append(unavailable[(m, year)])
            else:
                out_missing.append(UnavailableValue(metric_code=m, period_year=year, status="unavailable",
                                                    reason="missing"))
        status = "available" if not out_missing else ("partial" if out_values else "unavailable")
        return InstitutionFinancials(**base, period_year=year, status=status, values=out_values,
                                     unavailable=out_missing)

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    def build_history(
        self,
        institution_id: str,
        obs: list[ObservationSummary],
        *,
        period_type: str,
        data_scope: str,
        indicator: str | None = None,
    ) -> InstitutionHistory:
        sel = self.selection(obs)
        values, unavailable = self.qualify(self.select_rows(obs, period_type, data_scope))
        metrics = sorted({m for (m, _) in values} | {m for (m, _) in unavailable})
        if indicator:
            metrics = [m for m in metrics if m == indicator]

        series: list[HistorySeries] = []
        for m in metrics:
            points = [
                HistoryPoint(
                    period_year=y, value=v.value_normalized, currency=v.currency, unit_normalized=v.unit_normalized,
                    status=v.status, data_id=v.data_id, provenance=v.provenance,
                )
                for (mm, y), v in sorted(values.items(), key=lambda kv: kv[0][1])
                if mm == m
            ]
            excluded = sorted((u for (mm, _), u in unavailable.items() if mm == m), key=lambda u: u.period_year or 0)
            years = [p.period_year for p in points]
            missing = sorted(set(range(min(years), max(years) + 1)) - set(years)) if years else []
            currencies = {p.currency for p in points}
            if not points:
                status, reason, currency = "unavailable", "no_qualified_value", None
            elif len(currencies) > 1:
                # Values stay visible with their own currency, but no series is drawn across currencies.
                status, reason, currency = "needs_review", "heterogeneous_currency", None
            else:
                status = "partial" if (missing or excluded) else "available"
                reason, currency = None, next(iter(currencies))
            series.append(HistorySeries(metric_code=m, status=status, reason=reason, currency=currency,
                                        points=points, missing_years=missing, excluded_years=excluded))

        if not series:
            return InstitutionHistory(institution_id=institution_id, period_type=period_type, data_scope=data_scope,
                                      status="unavailable", reason="no_data" if not obs else "no_data_for_selection",
                                      selection=sel, series=[])
        status = "available" if all(s.status == "available" for s in series) else "partial"
        return InstitutionHistory(institution_id=institution_id, period_type=period_type, data_scope=data_scope,
                                  status=status, selection=sel, series=series)

    # ------------------------------------------------------------------
    # Coverage & data quality
    # ------------------------------------------------------------------

    def build_coverage(
        self,
        institution_id: str,
        obs: list[ObservationSummary],
        *,
        period_type: str,
        data_scope: str,
    ) -> InstitutionCoverage:
        rows = self.select_rows(obs, period_type, data_scope)
        values, _ = self.qualify(rows)
        qualified = [o for o in rows if o.id in {v.data_id for v in values.values()}]

        # Existing Phase 6 analyzers, fed only with this selection.
        cov = next(iter(self.consolidator.get_coverage(qualified)), None)
        report = self.consolidator.get_quality_report(rows)
        missing_years = list(cov.missing_years) if cov else []
        quality = DataQualityCounts(
            total_observations=len(rows),
            verified=report.verified_count,
            reviewed=report.reviewed_count,
            extracted=report.extracted_count,
            needs_review=report.needs_review_count,
            rejected=report.rejected_count,
            conflicts=report.conflicts_count,
            missing_years=len(missing_years),
        )

        docs: dict[str, dict] = {}
        for v in values.values():
            p = v.provenance
            if not p.document_id:
                continue  # no valid provenance → no document shown
            d = docs.setdefault(p.document_id, {"title": p.document_title, "source_name": p.source_name,
                                                "years": set(), "pages": set(), "count": 0})
            d["years"].add(v.period_year)
            if p.page_number:
                d["pages"].add(p.page_number)
            d["count"] += 1
        documents = [
            SourceDocument(document_id=k, title=d["title"], source_name=d["source_name"],
                           period_years=sorted(d["years"]), pages=sorted(d["pages"]), values_count=d["count"])
            for k, d in sorted(docs.items(), key=lambda kv: (kv[1]["title"] or "", kv[0]))
        ]

        base = dict(institution_id=institution_id, period_type=period_type, data_scope=data_scope,
                    quality=quality, documents=documents)
        if cov is None or cov.first_year is None:
            return InstitutionCoverage(**base, status="unavailable",
                                       reason="no_data" if not obs else "no_data_for_selection",
                                       available_years=[], missing_years=[], available_years_count=0)
        expected = cov.last_year - cov.first_year + 1
        return InstitutionCoverage(
            **base,
            status="available" if not missing_years else "partial",
            first_year=cov.first_year,
            last_year=cov.last_year,
            available_years=list(cov.available_years),
            missing_years=missing_years,
            available_years_count=len(cov.available_years),
            expected_years_count=expected,
            coverage_ratio=cov.coverage_ratio,
        )

    # ------------------------------------------------------------------
    # Async entry points
    # ------------------------------------------------------------------

    async def financials(self, db, institution_id, *, period_year=None, period_type=SECTOR_PERIOD_TYPE,
                         data_scope=SECTOR_SCOPE, indicator=None) -> InstitutionFinancials:
        obs = await self.observations(db, institution_id)
        return self.build_financials(institution_id, obs, period_year=period_year, period_type=period_type,
                                     data_scope=data_scope, indicator=indicator)

    async def history(self, db, institution_id, *, period_type=SECTOR_PERIOD_TYPE, data_scope=SECTOR_SCOPE,
                      indicator=None) -> InstitutionHistory:
        obs = await self.observations(db, institution_id)
        return self.build_history(institution_id, obs, period_type=period_type, data_scope=data_scope,
                                  indicator=indicator)

    async def coverage(self, db, institution_id, *, period_type=SECTOR_PERIOD_TYPE,
                       data_scope=SECTOR_SCOPE) -> InstitutionCoverage:
        obs = await self.observations(db, institution_id)
        return self.build_coverage(institution_id, obs, period_type=period_type, data_scope=data_scope)

    def latest_qualified_year(self, obs: list[ObservationSummary], period_type: str, data_scope: str) -> int | None:
        """Default year shared by the key figures, ratios and growth of one selection."""
        values, _ = self.qualify(self.select_rows(obs, period_type, data_scope))
        return max((y for (_, y) in values), default=None)

    async def _default_year(self, db, institution_id, period_year, period_type, data_scope) -> int | None:
        if period_year is not None:
            return period_year
        return self.latest_qualified_year(await self.observations(db, institution_id), period_type, data_scope)

    async def ratios(self, db, institution_id, *, period_year=None, period_type=SECTOR_PERIOD_TYPE,
                     data_scope=SECTOR_SCOPE) -> InstitutionRatios:
        base = dict(institution_id=institution_id, period_type=period_type, data_scope=data_scope)
        if period_type != SECTOR_PERIOD_TYPE:
            return InstitutionRatios(**base, period_year=period_year, status="unavailable",
                                     reason="period_type_not_supported", items=[])
        year = await self._default_year(db, institution_id, period_year, period_type, data_scope)
        if year is None:
            return InstitutionRatios(**base, period_year=None, status="unavailable", reason="no_data_for_selection",
                                     items=[])
        base["period_year"] = year
        items, _ = await self.analytics.get_ratios(db, institution_id=institution_id, year=year,
                                                   data_scope=data_scope, limit=_ALL)
        return InstitutionRatios(**base, **_derived_status(items, "value_percent"), items=items)

    async def growth(self, db, institution_id, *, period_year=None, period_type=SECTOR_PERIOD_TYPE,
                     data_scope=SECTOR_SCOPE, indicator=None) -> InstitutionGrowth:
        base = dict(institution_id=institution_id, period_type=period_type, data_scope=data_scope)
        if period_type != SECTOR_PERIOD_TYPE:
            return InstitutionGrowth(**base, period_year=period_year, status="unavailable",
                                     reason="period_type_not_supported", items=[])
        year = await self._default_year(db, institution_id, period_year, period_type, data_scope)
        if year is None:
            return InstitutionGrowth(**base, period_year=None, status="unavailable", reason="no_data_for_selection",
                                     items=[])
        base["period_year"] = year
        items, _ = await self.analytics.get_growth(db, institution_id=institution_id, metric_code=indicator,
                                                   year=year, data_scope=data_scope, limit=_ALL)
        return InstitutionGrowth(**base, **_derived_status(items, "growth_percent"), items=items)


def _derived_status(items: list, value_attr: str) -> dict:
    """Overall status of ratio / growth results, from the calculators' own values (never computed here)."""
    computed = [i for i in items if getattr(i, value_attr, None) is not None]
    if not items or not computed:
        return {"status": "unavailable", "reason": "no_computable_value"}
    return {"status": "available" if len(computed) == len(items) else "partial", "reason": None}
