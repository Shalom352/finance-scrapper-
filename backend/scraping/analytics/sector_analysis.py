"""
UMOA Banking Intelligence — Sector Analysis & Comparisons

Calculates bank market shares within national banking sectors and provides
factual multi-entity comparisons without subjective rankings.
"""
from decimal import Decimal

from scraping.analytics.models import (
    ComparisonResult,
    MarketShareResult,
    SectorAggregationResult,
)


class SectorAnalyzer:
    """Analyzes market structure and computes factual entity comparisons."""

    def calculate_market_share(
        self,
        institution_id: str,
        institution_value: Decimal,
        sector_aggregation: SectorAggregationResult,
        institution_name: str | None = None,
    ) -> MarketShareResult:
        """
        Calculate an institution's market share for a given metric and year.

        Formula: institution_value / sector_total_value
        """
        sector_total = sector_aggregation.total_value

        if sector_total is None or sector_total <= Decimal("0"):
            return MarketShareResult(
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=sector_aggregation.country_code or "UMOA",
                year=sector_aggregation.year,
                metric_code=sector_aggregation.metric_code,
                institution_value=institution_value,
                sector_total_value=None,
                market_share=None,
                market_share_percent=None,
                currency=sector_aggregation.currency,
                coverage_ratio=sector_aggregation.coverage_ratio,
                status="unavailable",
            )

        share = float(institution_value / sector_total)
        share_pct = round(share * 100.0, 4)

        return MarketShareResult(
            institution_id=institution_id,
            institution_name=institution_name,
            country_code=sector_aggregation.country_code or "UMOA",
            year=sector_aggregation.year,
            metric_code=sector_aggregation.metric_code,
            institution_value=institution_value,
            sector_total_value=sector_total,
            market_share=share,
            market_share_percent=share_pct,
            currency=sector_aggregation.currency,
            coverage_ratio=sector_aggregation.coverage_ratio,
            status="calculated" if not sector_aggregation.is_partial else "needs_review",
        )

    def compare_institutions(
        self,
        inst_a_name: str,
        val_a: float | Decimal | None,
        inst_b_name: str,
        val_b: float | Decimal | None,
        metric_or_ratio: str,
        year: int,
        unit: str | None = None,
    ) -> ComparisonResult:
        """Compare a metric or ratio between two banking institutions for the same year."""
        f_a = float(val_a) if val_a is not None else None
        f_b = float(val_b) if val_b is not None else None

        diff = None
        ratio_ab = None
        desc = f"Comparison of {metric_or_ratio} in {year} between {inst_a_name} and {inst_b_name}."

        if f_a is not None and f_b is not None:
            diff = round(f_a - f_b, 4)
            if f_b != 0.0:
                ratio_ab = round(f_a / f_b, 4)
            desc = (
                f"{inst_a_name}: {f_a} {unit or ''} vs {inst_b_name}: {f_b} {unit or ''} "
                f"(Diff: {diff:+0.4f}, Ratio: {ratio_ab if ratio_ab is not None else 'N/A'})."
            )

        return ComparisonResult(
            comparison_type="institution_vs_institution",
            entity_a=inst_a_name,
            entity_b=inst_b_name,
            metric_or_ratio=metric_or_ratio,
            year=year,
            value_a=f_a,
            value_b=f_b,
            unit=unit,
            difference=diff,
            ratio_a_to_b=ratio_ab,
            description=desc,
        )

    def compare_institution_to_country(
        self,
        institution_name: str,
        institution_value: float | Decimal | None,
        country_name: str,
        country_total: float | Decimal | None,
        metric_code: str,
        year: int,
        unit: str = "XOF",
    ) -> ComparisonResult:
        """Compare an institution's metric against the total national sector."""
        f_inst = float(institution_value) if institution_value is not None else None
        f_tot = float(country_total) if country_total is not None else None

        ratio_share = None
        if f_inst is not None and f_tot is not None and f_tot > 0.0:
            ratio_share = round(f_inst / f_tot, 4)

        desc = (
            f"{institution_name} represents {round(ratio_share * 100, 2)}% "
            f"of the {country_name} sector total for {metric_code} in {year}."
            if ratio_share is not None
            else f"Share of {institution_name} in the {country_name} sector total for {metric_code} "
            f"in {year}: not available."
        )

        return ComparisonResult(
            comparison_type="institution_vs_country",
            entity_a=institution_name,
            entity_b=country_name,
            metric_or_ratio=metric_code,
            year=year,
            value_a=f_inst,
            value_b=f_tot,
            unit=unit,
            difference=None,
            ratio_a_to_b=ratio_share,
            description=desc,
        )

    def compare_country_to_umoa(
        self,
        country_name: str,
        country_total: float | Decimal | None,
        umoa_total: float | Decimal | None,
        metric_code: str,
        year: int,
        unit: str = "XOF",
    ) -> ComparisonResult:
        """Compare a country's sector total against the entire UMOA regional aggregate."""
        f_c = float(country_total) if country_total is not None else None
        f_u = float(umoa_total) if umoa_total is not None else None

        ratio_share = None
        if f_c is not None and f_u is not None and f_u > 0.0:
            ratio_share = round(f_c / f_u, 4)

        desc = (
            f"{country_name} represents {round(ratio_share * 100, 2)}% "
            f"of the total UMOA banking sector for {metric_code} in {year}."
            if ratio_share is not None
            else f"Share of {country_name} in the UMOA banking sector for {metric_code} in {year}: not available."
        )

        return ComparisonResult(
            comparison_type="country_vs_umoa",
            entity_a=country_name,
            entity_b="UMOA",
            metric_or_ratio=metric_code,
            year=year,
            value_a=f_c,
            value_b=f_u,
            unit=unit,
            difference=None,
            ratio_a_to_b=ratio_share,
            description=desc,
        )
