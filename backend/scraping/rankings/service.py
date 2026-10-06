"""
RankingService — descriptive rankings, rank history and comparisons.

Every ranking uses exactly one indicator, one period_year, one period_type and
one data_scope (defaults: annual + individual, the Phase 8C sector rule). Values
come from the existing qualification layer; nothing is converted, interpolated
or defaulted. Institutions without an admissible value are listed separately and
never ranked.
"""
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import distinct, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.analytics.aggregation import SECTOR_PERIOD_TYPE, SECTOR_SCOPE
from scraping.analytics.analytics_service import AnalyticsService
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.rankings.calculator import (
    competition_ranks,
    compute_coverage,
    is_currency_homogeneous,
    paginate,
)
from scraping.rankings.definitions import RankableIndicator
from scraping.rankings.eligibility import qualify_derived, qualify_metric
from scraping.rankings.models import (
    Candidate,
    ComparisonRow,
    CountryComparison,
    ExclusionSummary,
    InstitutionsComparison,
    RankHistory,
    RankHistoryPoint,
    RankingEntry,
    RankingResult,
    SectorComparison,
    UnavailableEntry,
)
from scraping.rankings.universe import UniverseResolution, resolve_banking_universe

UMOA = "UMOA"
# Rankings compare institutions only: country / regional / market rows are another population.
RANKED_OBSERVATION_LEVEL = "entity"

# Candidate reason -> ExclusionSummary counter.
_REASON_TO_FIELD = {
    "needs_review": "excluded_needs_review",
    "missing": "excluded_missing",
    "conflict": "excluded_conflict",
    "rejected_only": "excluded_rejected",
    "scope_incompatible": "excluded_scope",
    "observation_level_incompatible": "excluded_observation_level",
}
_EXCLUSION_FIELDS = (
    "excluded_needs_review",
    "excluded_missing",
    "excluded_conflict",
    "excluded_rejected",
    "excluded_scope",
    "excluded_observation_level",
    "excluded_currency",
    "excluded_other",
)
_ALL = 10**6  # no pagination when delegating to AnalyticsService


class UnsupportedPeriodTypeError(ValueError):
    """Growth and ratios are annual indicators only."""


class RankingService:
    def __init__(self) -> None:
        self.analytics = AnalyticsService()
        self.engine = self.analytics.sector_aggregator.eligibility
        self.detector = DuplicateDetector()

    # ------------------------------------------------------------------
    # Universe & periods
    # ------------------------------------------------------------------

    async def universe_resolution(self, db: AsyncSession, country_code: str | None) -> UniverseResolution:
        """Ranking universe (current official snapshot) and the explicit population exclusions."""
        return await resolve_banking_universe(db, country_code)

    async def universe(self, db: AsyncSession, country_code: str | None) -> list[tuple[Institution, str | None]]:
        """Banks expected in the ranking (current official snapshot): one country, or the 8 UMOA countries."""
        return (await self.universe_resolution(db, country_code)).members

    async def available_years(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        period_type: str,
        data_scope: str,
        institution_ids: list[str],
    ) -> list[int]:
        """Years holding at least one ADMISSIBLE value of the base metric, newest first.

        needs_review values never enter a ranking: a year holding only such values is not a default.
        """
        if not institution_ids:
            return []
        query = select(distinct(FinancialData.period_year)).where(
            FinancialData.metric_code == indicator.base_metric,
            FinancialData.period_type == period_type,
            FinancialData.scope == data_scope,
            FinancialData.consolidation_scope == data_scope,
            FinancialData.observation_level == RANKED_OBSERVATION_LEVEL,
            FinancialData.status.notin_(("rejected", "needs_review")),
            FinancialData.value_normalized.isnot(None),
            FinancialData.deleted_at.is_(None),
            FinancialData.institution_id.in_(institution_ids),
        )
        years = (await db.execute(query)).scalars().all()
        return sorted(years, reverse=True)

    # ------------------------------------------------------------------
    # Candidates (one qualified value per institution)
    # ------------------------------------------------------------------

    async def candidates(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        year: int,
        period_type: str,
        data_scope: str,
        institution_ids: list[str],
    ) -> dict[str, Candidate]:
        if indicator.annual_only and period_type != SECTOR_PERIOD_TYPE:
            raise UnsupportedPeriodTypeError(indicator.code)
        if not institution_ids:
            return {}

        if indicator.kind == "metric":
            query = (
                select(FinancialData)
                .options(selectinload(FinancialData.source), selectinload(FinancialData.document))
                .where(
                    FinancialData.metric_code == indicator.base_metric,
                    FinancialData.period_year == year,
                    FinancialData.period_type == period_type,
                    FinancialData.deleted_at.is_(None),
                    FinancialData.institution_id.in_(institution_ids),
                )
            )
            rows = (await db.execute(query)).scalars().all()
            by_inst = defaultdict(list)
            incompatible: dict[str, str] = {}
            for r in rows:
                if r.scope != data_scope:
                    continue  # another accounting scope is another ranking, not an exclusion
                if r.observation_level != RANKED_OBSERVATION_LEVEL:
                    incompatible.setdefault(r.institution_id, "observation_level_incompatible")
                    continue
                if r.consolidation_scope != data_scope:
                    # scope and consolidation_scope disagree: the row is never ranked
                    incompatible[r.institution_id] = "scope_incompatible"
                    continue
                by_inst[r.institution_id].append(self.detector.observation_from_orm(r))
            out: dict[str, Candidate] = {}
            for i in institution_ids:
                if not by_inst.get(i) and i in incompatible:
                    out[i] = Candidate(institution_id=i, eligible=False, status="unavailable", reason=incompatible[i])
                else:
                    out[i] = qualify_metric(i, by_inst.get(i, []), self.engine)
            return out

        wanted = set(institution_ids)
        out: dict[str, Candidate] = {}
        if indicator.kind == "growth":
            results, _ = await self.analytics.get_growth(
                db, metric_code=indicator.base_metric, year=year, data_scope=data_scope, limit=_ALL
            )
            for g in results:
                if g.institution_id in wanted:
                    out[g.institution_id] = qualify_derived(g, "growth_percent", currency=g.currency)
        else:
            results, _ = await self.analytics.get_ratios(
                db, ratio_code=indicator.code, year=year, data_scope=data_scope, limit=_ALL
            )
            for r in results:
                if r.institution_id in wanted:
                    out[r.institution_id] = qualify_derived(r, "value_percent")
        for i in institution_ids:
            out.setdefault(i, Candidate(institution_id=i, eligible=False, status="unavailable", reason="missing"))
        return out

    # ------------------------------------------------------------------
    # Ranking
    # ------------------------------------------------------------------

    async def rank(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        *,
        period_year: int | None = None,
        period_type: str = SECTOR_PERIOD_TYPE,
        data_scope: str = SECTOR_SCOPE,
        country_code: str | None = None,
        order: str = "desc",
        page: int = 1,
        page_size: int = 20,
    ) -> RankingResult:
        scope_label = (country_code or UMOA).upper()
        resolution = await self.universe_resolution(db, country_code)
        universe = resolution.members
        ids = [inst.id for inst, _ in universe]
        population_entries = sorted(
            (
                UnavailableEntry(
                    institution_id=x.institution.id,
                    institution_name=x.institution.name_official,
                    country_code=x.country_code,
                    status="excluded",
                    reason=x.reason,
                )
                for x in resolution.excluded
            ),
            key=lambda e: (e.institution_name.casefold(), e.institution_id),
        )

        def summary(
            cands: dict[str, Candidate] | None = None,
            currency_blocked: bool = False,
            unevaluated: str = "excluded_other",
        ) -> ExclusionSummary:
            counts = dict.fromkeys(_EXCLUSION_FIELDS, 0)
            eligible_count = 0
            for c in (cands or {}).values():
                if c.eligible:
                    if currency_blocked:
                        counts["excluded_currency"] += 1
                    else:
                        eligible_count += 1
                else:
                    counts[_REASON_TO_FIELD.get(c.reason or "missing", "excluded_other")] += 1
            if cands is None:
                # Ranking not evaluated: no period holds data (missing) or unsupported period type (other).
                counts[unevaluated] = len(universe)
            return ExclusionSummary(
                universe_source=resolution.source,
                universe_reference_date=resolution.reference_date,
                universe_total=len(universe),
                eligible_count=eligible_count,
                excluded_population=len(resolution.excluded),
                **counts,
            )

        def result(**kw) -> RankingResult:
            base = dict(
                metric_code=indicator.code,
                kind=indicator.kind,
                unit=indicator.unit,
                country_code=scope_label,
                period_year=None,
                period_type=period_type,
                data_scope=data_scope,
                order=order,
                reason=None,
                currency=None,
                coverage=compute_coverage(0, len(universe)),
                items=[],
                total_ranked=0,
                page=page,
                page_size=page_size,
                has_next=False,
                has_prev=page > 1,
                unavailable=[],
                available_years=[],
                exclusions=summary(),
                excluded_population=population_entries,
            )
            base.update(kw)
            return RankingResult(**base)

        if indicator.annual_only and period_type != SECTOR_PERIOD_TYPE:
            # Eligibility is not even evaluated: coverage cannot be established (not 0/N).
            return result(
                status="unavailable",
                reason="period_type_not_supported",
                coverage=compute_coverage(0, len(universe), available=False),
            )

        years = await self.available_years(db, indicator, period_type, data_scope, ids)
        year = period_year if period_year is not None else (years[0] if years else None)
        if year is None:
            return result(
                status="unavailable",
                reason="no_period",
                available_years=years,
                exclusions=summary(unevaluated="excluded_missing"),
            )

        cands = await self.candidates(db, indicator, year, period_type, data_scope, ids)
        meta = {inst.id: (inst.name_official, code) for inst, code in universe}

        eligible = [c for c in cands.values() if c.eligible]
        unavailable = [c for c in cands.values() if not c.eligible]

        def unavailable_entry(c: Candidate, reason: str | None = None) -> UnavailableEntry:
            name, code = meta[c.institution_id]
            return UnavailableEntry(
                institution_id=c.institution_id,
                institution_name=name,
                country_code=code,
                status=c.status if reason is None else "needs_review",
                reason=reason or c.reason or "missing",
                detail=c.detail,
                currency=c.currency,
            )

        unavailable_entries = sorted(
            (unavailable_entry(c) for c in unavailable), key=lambda e: (e.institution_name.casefold(), e.institution_id)
        )
        coverage = compute_coverage(len(eligible), len(universe))

        # Heterogeneous currencies: no ranking at all, no implicit conversion.
        # Percentages (ratios, growth) are dimensionless and need no currency check.
        if indicator.unit == "currency":
            if not is_currency_homogeneous([c.currency for c in eligible]):
                blocked = [unavailable_entry(c, reason="heterogeneous_currency") for c in eligible]
                return result(
                    status="needs_review",
                    reason="heterogeneous_currency",
                    period_year=year,
                    exclusions=summary(cands, currency_blocked=True),
                    # Values exist but cannot be ranked: real eligible count, nothing ranked,
                    # coverage unavailable — never 0/N.
                    coverage=compute_coverage(len(eligible), len(universe), available=False),
                    unavailable=sorted(
                        blocked + unavailable_entries, key=lambda e: (e.institution_name.casefold(), e.institution_id)
                    ),
                    available_years=years,
                )

        if not eligible:
            return result(
                status="unavailable",
                reason="no_eligible_data",
                period_year=year,
                exclusions=summary(cands),
                coverage=coverage,
                unavailable=unavailable_entries,
                available_years=years,
            )

        ranked = competition_ranks(
            eligible,
            value=lambda c: c.value,
            name=lambda c: meta[c.institution_id][0],
            ident=lambda c: c.institution_id,
            descending=order != "asc",
        )
        currency = eligible[0].currency if indicator.unit == "currency" else None
        entries = [
            RankingEntry(
                rank=rank,
                institution_id=c.institution_id,
                institution_name=meta[c.institution_id][0],
                country_code=meta[c.institution_id][1],
                metric_code=indicator.code,
                period_year=year,
                period_type=period_type,
                data_scope=data_scope,
                value=c.value,
                unit=indicator.unit if indicator.unit == "%" else (c.currency or ""),
                currency=c.currency,
                status=c.status,
                data_id=c.data_id,
                provenance=c.provenance,
            )
            for rank, c in ranked
        ]
        page_items, has_next, has_prev = paginate(entries, page, page_size)
        return result(
            status="partial" if (coverage.coverage_ratio or 0) < 1 else "calculated",
            period_year=year,
            exclusions=summary(cands),
            currency=currency,
            coverage=coverage,
            items=page_items,
            total_ranked=len(entries),
            has_next=has_next,
            has_prev=has_prev,
            unavailable=unavailable_entries,
            available_years=years,
        )

    async def history(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        institution: Institution,
        *,
        period_type: str = SECTOR_PERIOD_TYPE,
        data_scope: str = SECTOR_SCOPE,
        country_code: str,
    ) -> RankHistory:
        """Observed rank of one institution for every available year (descriptive only)."""
        ids = [inst.id for inst, _ in await self.universe(db, country_code)]
        years = [] if indicator.annual_only and period_type != SECTOR_PERIOD_TYPE else await self.available_years(
            db, indicator, period_type, data_scope, ids
        )
        points: list[RankHistoryPoint] = []
        for year in sorted(years):
            ranking = await self.rank(
                db, indicator, period_year=year, period_type=period_type, data_scope=data_scope,
                country_code=country_code, page=1, page_size=_ALL,
            )
            entry = next((e for e in ranking.items if e.institution_id == institution.id), None)
            missing = next((u for u in ranking.unavailable if u.institution_id == institution.id), None)
            points.append(
                RankHistoryPoint(
                    period_year=year,
                    rank=entry.rank if entry else None,
                    value=entry.value if entry else None,
                    currency=entry.currency if entry else (missing.currency if missing else None),
                    ranking_status=ranking.status,
                    status=entry.status if entry else (missing.status if missing else "unavailable"),
                    reason=None if entry else (missing.reason if missing else ranking.reason),
                    eligible_count=ranking.coverage.eligible_count,
                    ranked_count=ranking.coverage.ranked_count,
                    expected_count=ranking.coverage.expected_count,
                    coverage_ratio=ranking.coverage.coverage_ratio,
                )
            )
        return RankHistory(
            institution_id=institution.id,
            institution_name=institution.name_official,
            metric_code=indicator.code,
            period_type=period_type,
            data_scope=data_scope,
            country_code=country_code.upper(),
            points=points,
        )

    # ------------------------------------------------------------------
    # Comparisons
    # ------------------------------------------------------------------

    async def compare_institutions(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        institutions: list[tuple[Institution, str | None]],
        *,
        period_year: int | None = None,
        period_type: str = SECTOR_PERIOD_TYPE,
        data_scope: str = SECTOR_SCOPE,
    ) -> InstitutionsComparison:
        ids = [inst.id for inst, _ in institutions]
        meta = {inst.id: (inst.name_official, code) for inst, code in institutions}

        def out(**kw) -> InstitutionsComparison:
            base = dict(
                metric_code=indicator.code, kind=indicator.kind, unit=indicator.unit, period_year=None,
                period_type=period_type, data_scope=data_scope, reason=None, currency=None, rows=[],
            )
            base.update(kw)
            return InstitutionsComparison(**base)

        if indicator.annual_only and period_type != SECTOR_PERIOD_TYPE:
            return out(status="unavailable", reason="period_type_not_supported")
        years = await self.available_years(db, indicator, period_type, data_scope, ids)
        year = period_year if period_year is not None else (years[0] if years else None)
        if year is None:
            return out(status="unavailable", reason="no_period")

        cands = await self.candidates(db, indicator, year, period_type, data_scope, ids)
        eligible = [c for c in cands.values() if c.eligible]
        homogeneous = indicator.unit == "%" or is_currency_homogeneous([c.currency for c in eligible])

        rows = []
        for i in ids:
            c = cands[i]
            name, code = meta[i]
            if c.eligible and not homogeneous:
                rows.append(ComparisonRow(
                    institution_id=i, institution_name=name, country_code=code, currency=c.currency,
                    status="needs_review", reason="heterogeneous_currency",
                ))
                continue
            rows.append(ComparisonRow(
                institution_id=i, institution_name=name, country_code=code,
                value=c.value if c.eligible else None, currency=c.currency,
                status=c.status, reason=None if c.eligible else (c.reason or "missing"),
                data_id=c.data_id, provenance=c.provenance,
            ))

        if not homogeneous:
            status, reason = "needs_review", "heterogeneous_currency"
        elif not eligible:
            status, reason = "unavailable", "no_eligible_data"
        else:
            status, reason = ("calculated" if len(eligible) == len(ids) else "partial"), None
        currency = eligible[0].currency if eligible and homogeneous and indicator.unit == "currency" else None
        return out(status=status, reason=reason, period_year=year, currency=currency, rows=rows)

    async def _latest_aggregate_year(
        self, db: AsyncSession, indicator: RankableIndicator, institution_ids: list[str]
    ) -> int | None:
        years = await self.available_years(db, indicator, SECTOR_PERIOD_TYPE, SECTOR_SCOPE, institution_ids)
        return years[0] if years else None

    async def institution_vs_sector(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        institution: Institution,
        country_code: str,
        *,
        period_year: int | None = None,
    ) -> SectorComparison:
        """Institution value vs national sector total (individual + annual, Phase 8C rule)."""
        base = dict(metric_code=indicator.code, period_type=SECTOR_PERIOD_TYPE, data_scope=SECTOR_SCOPE,
                    country_code=country_code)
        if indicator.kind != "metric":
            return SectorComparison(**base, status="unavailable", reason="aggregate_not_supported")

        country_ids = [inst.id for inst, _ in await self.universe(db, country_code)]
        year = period_year if period_year is not None else await self._latest_aggregate_year(
            db, indicator, country_ids
        )
        if year is None:
            return SectorComparison(**base, status="unavailable", reason="no_period")

        cand = (await self.candidates(db, indicator, year, SECTOR_PERIOD_TYPE, SECTOR_SCOPE, [institution.id]))[
            institution.id
        ]
        row = ComparisonRow(
            institution_id=institution.id, institution_name=institution.name_official, country_code=country_code,
            value=cand.value if cand.eligible else None, currency=cand.currency, status=cand.status,
            reason=None if cand.eligible else (cand.reason or "missing"), data_id=cand.data_id,
            provenance=cand.provenance,
        )
        aggs = await self.analytics.get_aggregations(
            db, year=year, metric_code=indicator.code, country_code=country_code, scope="country"
        )
        agg = next((a for a in aggs if a.country_code == country_code.upper()), None)
        sector = dict(
            sector_total=agg.total_value if agg else None,
            sector_currency=agg.currency if agg else None,
            sector_status=agg.status if agg else None,
            sector_coverage_ratio=agg.coverage_ratio if agg else None,
            sector_institution_count=agg.institution_count if agg else None,
            sector_total_institutions=agg.total_institutions if agg else None,
        )

        # A share only exists when the institution's value is part of that very total.
        share, status, reason = None, "calculated", None
        if agg is None or agg.total_value is None:
            status, reason = ("needs_review", "sector_needs_review") if agg and agg.status == "needs_review" else (
                "unavailable", "sector_total_unavailable")
        elif not cand.eligible:
            status, reason = "unavailable", "institution_value_unavailable"
        elif cand.currency != agg.currency:
            status, reason = "needs_review", "heterogeneous_currency"
        elif institution.id not in agg.contributing_institutions or agg.total_value <= Decimal("0"):
            status, reason = "unavailable", "not_in_sector_total"
        else:
            share = round(float(cand.value / agg.total_value) * 100.0, 4)
            status = "partial" if agg.is_partial else "calculated"
        return SectorComparison(**base, **sector, period_year=year, status=status, reason=reason,
                                institution=row, share_percent=share)

    async def country_vs_umoa(
        self,
        db: AsyncSession,
        indicator: RankableIndicator,
        country_code: str,
        *,
        period_year: int | None = None,
    ) -> CountryComparison:
        base = dict(metric_code=indicator.code, period_type=SECTOR_PERIOD_TYPE, data_scope=SECTOR_SCOPE,
                    country_code=country_code.upper())
        if indicator.kind != "metric":
            return CountryComparison(**base, status="unavailable", reason="aggregate_not_supported")
        country_ids = [inst.id for inst, _ in await self.universe(db, country_code)]
        year = period_year if period_year is not None else await self._latest_aggregate_year(
            db, indicator, country_ids
        )
        if year is None:
            return CountryComparison(**base, status="unavailable", reason="no_period")

        country_aggs = await self.analytics.get_aggregations(
            db, year=year, metric_code=indicator.code, country_code=country_code, scope="country"
        )
        c = next((a for a in country_aggs if a.country_code == country_code.upper()), None)
        u = (await self.analytics.get_aggregations(db, year=year, metric_code=indicator.code, scope="umoa"))[0]
        values = dict(
            country_status=c.status if c else None,
            country_coverage_ratio=c.coverage_ratio if c else None,
            umoa_status=u.status,
            umoa_coverage_ratio=u.coverage_ratio,
        )
        if (c and c.status == "needs_review") or u.status == "needs_review":
            return CountryComparison(**base, **values, period_year=year, status="needs_review",
                                     reason="aggregate_needs_review")
        if c is None or c.total_value is None or u.total_value is None:
            return CountryComparison(**base, **values, period_year=year, status="unavailable",
                                     reason="aggregate_unavailable")
        if c.currency != u.currency:
            return CountryComparison(**base, **values, period_year=year, status="needs_review",
                                     reason="heterogeneous_currency")
        share = round(float(c.total_value / u.total_value) * 100.0, 4) if u.total_value > 0 else None
        return CountryComparison(
            **base, **values, period_year=year,
            status="partial" if (c.is_partial or u.is_partial) else "calculated",
            country_total=c.total_value, umoa_total=u.total_value, currency=c.currency, share_percent=share,
        )
