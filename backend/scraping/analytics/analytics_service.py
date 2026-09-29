"""
UMOA Banking Intelligence — Analytics Orchestration Service

Orchestrates database queries and on-demand financial analytics calculations
for ratios, growth rates, sector aggregations, and entity comparisons.
"""
from collections import defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.country import Country
from app.models.financial_data import FinancialData
from app.models.institution import Institution
from scraping.analytics.aggregation import SectorAggregator
from scraping.analytics.growth_calculator import CORE_GROWTH_METRICS, GrowthCalculator
from scraping.analytics.models import (
    ComparisonResult,
    GrowthCalculationResult,
    MarketShareResult,
    RatioCalculationResult,
    SectorAggregationResult,
)
from scraping.analytics.ratio_calculator import RATIO_DEFINITIONS, RatioCalculator
from scraping.analytics.sector_analysis import SectorAnalyzer
from scraping.consolidation.duplicate_detector import DuplicateDetector
from scraping.consolidation.models import ObservationSummary


class AnalyticsService:
    """Async database service for on-demand calculation of financial ratios and analytics."""

    def __init__(self) -> None:
        self.ratio_calculator = RatioCalculator()
        self.growth_calculator = GrowthCalculator()
        self.sector_aggregator = SectorAggregator()
        self.sector_analyzer = SectorAnalyzer()
        self.duplicate_detector = DuplicateDetector()

    async def get_ratios(
        self,
        db: AsyncSession,
        *,
        institution_id: str | None = None,
        country_code: str | None = None,
        ratio_code: str | None = None,
        year: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[RatioCalculationResult], int]:
        """
        Calculate and return banking ratios based on available financial data.
        """
        # Determine target ratios
        if ratio_code:
            target_codes = [ratio_code.upper()] if ratio_code.upper() in RATIO_DEFINITIONS else []
        else:
            target_codes = list(RATIO_DEFINITIONS.keys())

        if not target_codes:
            return [], 0

        # Query relevant institutions
        inst_query = select(Institution).options(selectinload(Institution.country))
        if institution_id:
            inst_query = inst_query.where(Institution.id == institution_id)
        if country_code:
            inst_query = inst_query.join(Institution.country).where(
                func.upper(Country.iso_code_2) == country_code.upper()
            )

        institutions = (await db.execute(inst_query)).scalars().all()
        if not institutions:
            return [], 0

        inst_map = {inst.id: inst for inst in institutions}
        inst_ids = list(inst_map.keys())

        # Determine year range needed (if year given, need year and year-1 for averages)
        data_query = (
            select(FinancialData)
            .options(
                selectinload(FinancialData.source),
                selectinload(FinancialData.document),
            )
            .where(
                FinancialData.institution_id.in_(inst_ids),
                FinancialData.deleted_at.is_(None),
            )
        )
        if year is not None:
            data_query = data_query.where(FinancialData.period_year.in_([year, year - 1]))

        rows = (await db.execute(data_query)).scalars().all()

        # Group observations by institution
        obs_by_inst: dict[str, list[ObservationSummary]] = defaultdict(list)
        for r in rows:
            obs_by_inst[r.institution_id].append(self.duplicate_detector.observation_from_orm(r))

        # Determine target years to calculate
        all_results: list[RatioCalculationResult] = []
        for i_id, inst in inst_map.items():
            inst_obs = obs_by_inst.get(i_id, [])
            if year is not None:
                years_to_calc = [year]
            else:
                years_to_calc = sorted({o.period_year for o in inst_obs}, reverse=True)

            c_code = inst.country.iso_code_2 if inst.country else None

            for y in years_to_calc:
                for r_code in target_codes:
                    res = self.ratio_calculator.calculate_ratio(
                        ratio_code=r_code,
                        institution_id=i_id,
                        year=y,
                        observations=inst_obs,
                        institution_name=inst.name,
                        country_code=c_code,
                    )
                    if status and res.status != status:
                        continue
                    all_results.append(res)

        total = len(all_results)
        paginated = all_results[offset : offset + limit]
        return paginated, total

    async def get_growth(
        self,
        db: AsyncSession,
        *,
        institution_id: str | None = None,
        country_code: str | None = None,
        metric_code: str | None = None,
        year: int | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[GrowthCalculationResult], int]:
        """
        Calculate year-over-year variation for core financial metrics.
        """
        target_metrics = [metric_code] if metric_code else CORE_GROWTH_METRICS

        inst_query = select(Institution).options(selectinload(Institution.country))
        if institution_id:
            inst_query = inst_query.where(Institution.id == institution_id)
        if country_code:
            inst_query = inst_query.join(Institution.country).where(
                func.upper(Country.iso_code_2) == country_code.upper()
            )

        institutions = (await db.execute(inst_query)).scalars().all()
        if not institutions:
            return [], 0

        inst_map = {inst.id: inst for inst in institutions}
        inst_ids = list(inst_map.keys())

        data_query = (
            select(FinancialData)
            .options(
                selectinload(FinancialData.source),
                selectinload(FinancialData.document),
            )
            .where(
                FinancialData.institution_id.in_(inst_ids),
                FinancialData.metric_code.in_(target_metrics),
                FinancialData.deleted_at.is_(None),
            )
        )
        if year is not None:
            data_query = data_query.where(FinancialData.period_year.in_([year, year - 1]))

        rows = (await db.execute(data_query)).scalars().all()

        obs_by_inst: dict[str, list[ObservationSummary]] = defaultdict(list)
        for r in rows:
            obs_by_inst[r.institution_id].append(self.duplicate_detector.observation_from_orm(r))

        all_results: list[GrowthCalculationResult] = []
        for i_id, inst in inst_map.items():
            inst_obs = obs_by_inst.get(i_id, [])
            if year is not None:
                years_to_calc = [year]
            else:
                years_to_calc = sorted({o.period_year for o in inst_obs}, reverse=True)

            c_code = inst.country.iso_code_2 if inst.country else None

            for y in years_to_calc:
                for m_code in target_metrics:
                    res = self.growth_calculator.calculate_growth(
                        metric_code=m_code,
                        institution_id=i_id,
                        year=y,
                        observations=inst_obs,
                        institution_name=inst.name,
                        country_code=c_code,
                    )
                    if status and res.status != status:
                        continue
                    all_results.append(res)

        total = len(all_results)
        paginated = all_results[offset : offset + limit]
        return paginated, total

    async def get_aggregations(
        self,
        db: AsyncSession,
        *,
        year: int,
        metric_code: str = "total_actifs",
        country_code: str | None = None,
        scope: str = "country",
        include_needs_review: bool = False,
    ) -> list[SectorAggregationResult]:
        """
        Compute country or regional UMOA totals with institutional deduplication.
        """
        # Fetch country metadata
        c_query = select(Country)
        if country_code:
            c_query = c_query.where(func.upper(Country.iso_code_2) == country_code.upper())

        countries = (await db.execute(c_query)).scalars().all()
        if not countries:
            return []

        # Count institutions per country
        inst_counts_query = (
            select(Institution.country_id, func.count(Institution.id))
            .group_by(Institution.country_id)
        )
        counts_res = (await db.execute(inst_counts_query)).all()
        counts_by_country_id = {row[0]: row[1] for row in counts_res}

        country_results: list[SectorAggregationResult] = []

        for country in countries:
            # Query financial observations for this country
            c_data_query = (
                select(FinancialData)
                .join(Institution, FinancialData.institution_id == Institution.id)
                .options(
                    selectinload(FinancialData.source),
                    selectinload(FinancialData.document),
                )
                .where(
                    Institution.country_id == country.id,
                    FinancialData.metric_code == metric_code,
                    FinancialData.period_year == year,
                    FinancialData.deleted_at.is_(None),
                )
            )
            rows = (await db.execute(c_data_query)).scalars().all()
            parsed_obs = [self.duplicate_detector.observation_from_orm(r) for r in rows]

            tot_inst = counts_by_country_id.get(country.id, 0)

            c_agg = self.sector_aggregator.aggregate_country(
                country_code=country.iso_code_2,
                year=year,
                metric_code=metric_code,
                observations=parsed_obs,
                total_institutions_in_country=tot_inst,
                country_name=country.name_fr,
                include_needs_review=include_needs_review,
            )
            country_results.append(c_agg)

        if scope == "umoa":
            total_umoa_inst = sum(counts_by_country_id.values())
            umoa_agg = self.sector_aggregator.aggregate_umoa(
                year=year,
                metric_code=metric_code,
                country_aggregations=country_results,
                total_institutions_umoa=total_umoa_inst,
            )
            return [umoa_agg]

        return country_results

    async def get_sector_structure(
        self,
        db: AsyncSession,
        *,
        country_code: str,
        year: int,
        metric_code: str = "depots_clients",
    ) -> tuple[SectorAggregationResult | None, list[MarketShareResult]]:
        """
        Calculate market shares for all institutions in a country.
        """
        country_aggs = await self.get_aggregations(
            db, year=year, metric_code=metric_code, country_code=country_code, scope="country"
        )
        if not country_aggs:
            return None, []

        sec_agg = country_aggs[0]

        # Fetch individual institutions and their authoritative values
        c_query = select(Country).where(func.upper(Country.iso_code_2) == country_code.upper())
        country = (await db.execute(c_query)).scalar_one_or_none()
        if not country:
            return sec_agg, []

        inst_query = select(Institution).where(Institution.country_id == country.id)
        institutions = (await db.execute(inst_query)).scalars().all()

        inst_data_query = (
            select(FinancialData)
            .join(Institution, FinancialData.institution_id == Institution.id)
            .options(
                selectinload(FinancialData.source),
                selectinload(FinancialData.document),
            )
            .where(
                Institution.country_id == country.id,
                FinancialData.metric_code == metric_code,
                FinancialData.period_year == year,
                FinancialData.deleted_at.is_(None),
            )
        )
        rows = (await db.execute(inst_data_query)).scalars().all()

        obs_by_inst: dict[str, list[ObservationSummary]] = defaultdict(list)
        for r in rows:
            obs_by_inst[r.institution_id].append(self.duplicate_detector.observation_from_orm(r))

        shares: list[MarketShareResult] = []
        for inst in institutions:
            cand = obs_by_inst.get(inst.id, [])
            best, _ = self.sector_aggregator.eligibility.select_authoritative_observation(cand)
            if best and best.value_normalized is not None:
                ms = self.sector_analyzer.calculate_market_share(
                    institution_id=inst.id,
                    institution_value=best.value_normalized,
                    sector_aggregation=sec_agg,
                    institution_name=inst.name,
                )
                shares.append(ms)

        # Sort market shares descending
        shares.sort(key=lambda s: s.market_share, reverse=True)
        return sec_agg, shares

    async def compare_entities(
        self,
        db: AsyncSession,
        *,
        comparison_type: str,
        entity_a: str,
        entity_b: str,
        metric_or_ratio: str,
        year: int,
    ) -> ComparisonResult:
        """
        Execute factual comparison between two entities.
        """
        if comparison_type == "institution_vs_institution":
            inst_a = (await db.execute(select(Institution).where(Institution.id == entity_a))).scalar_one_or_none()
            inst_b = (await db.execute(select(Institution).where(Institution.id == entity_b))).scalar_one_or_none()
            name_a = inst_a.name if inst_a else entity_a
            name_b = inst_b.name if inst_b else entity_b

            # Try ratio first
            r_def = self.ratio_calculator.get_definition(metric_or_ratio)
            if r_def:
                r_a, _ = await self.get_ratios(db, institution_id=entity_a, ratio_code=metric_or_ratio, year=year)
                r_b, _ = await self.get_ratios(db, institution_id=entity_b, ratio_code=metric_or_ratio, year=year)
                val_a = r_a[0].value_percent if r_a and r_a[0].value_percent is not None else None
                val_b = r_b[0].value_percent if r_b and r_b[0].value_percent is not None else None
                unit = "%"
            else:
                # Query metric
                q_a = select(FinancialData.value_normalized).where(
                    FinancialData.institution_id == entity_a,
                    FinancialData.metric_code == metric_or_ratio,
                    FinancialData.period_year == year,
                    FinancialData.deleted_at.is_(None),
                )
                q_b = select(FinancialData.value_normalized).where(
                    FinancialData.institution_id == entity_b,
                    FinancialData.metric_code == metric_or_ratio,
                    FinancialData.period_year == year,
                    FinancialData.deleted_at.is_(None),
                )
                val_a = (await db.execute(q_a)).scalars().first()
                val_b = (await db.execute(q_b)).scalars().first()
                unit = "XOF"

            return self.sector_analyzer.compare_institutions(
                inst_a_name=name_a,
                val_a=val_a,
                inst_b_name=name_b,
                val_b=val_b,
                metric_or_ratio=metric_or_ratio,
                year=year,
                unit=unit,
            )

        elif comparison_type == "country_vs_umoa":
            country_res = await self.get_aggregations(
                db, year=year, metric_code=metric_or_ratio, country_code=entity_a, scope="country"
            )
            umoa_res = await self.get_aggregations(
                db, year=year, metric_code=metric_or_ratio, scope="umoa"
            )
            c_val = country_res[0].total_value if country_res else None
            u_val = umoa_res[0].total_value if umoa_res else None
            c_name = country_res[0].country_name or entity_a if country_res else entity_a

            return self.sector_analyzer.compare_country_to_umoa(
                country_name=c_name,
                country_total=c_val,
                umoa_total=u_val,
                metric_code=metric_or_ratio,
                year=year,
            )

        return ComparisonResult(
            comparison_type="institution_vs_institution",
            entity_a=entity_a,
            entity_b=entity_b,
            metric_or_ratio=metric_or_ratio,
            year=year,
            description="Comparison type not currently supported.",
        )
