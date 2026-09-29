"""
UMOA Banking Intelligence — Financial Consistency Checker

Validates mathematical and accounting coherence between extracted metric points
for the same period and institution (e.g. Total Actif ≈ Total Passif, component checks).
Never invents data: flags discrepancies with explicit warnings and routes to needs_review.
"""
from scraping.parsing.table_models import ExtractedMetricPoint


class ConsistencyChecker:
    """Verifies accounting coherence across extracted financial metric points."""

    def __init__(self, tolerance_ratio: float = 0.02) -> None:
        """
        Args:
            tolerance_ratio: Maximum relative tolerance for rounding/presentation differences (default 2%).
        """
        self.tolerance_ratio = tolerance_ratio

    def check_extracted_points(
        self,
        points: list[ExtractedMetricPoint],
    ) -> tuple[bool, list[str]]:
        """
        Verify coherence across a set of extracted metric points for a given period.

        Args:
            points: List of ExtractedMetricPoint objects.

        Returns:
            Tuple of (is_consistent, list of warning strings).
        """
        warnings: list[str] = []

        # Index points by (period_year, metric_code) -> normalized value
        by_period: dict[int, dict[str, ExtractedMetricPoint]] = {}
        for p in points:
            if p.value_normalized is not None:
                by_period.setdefault(p.period_year, {})[p.metric_code] = p

        for year, metrics in by_period.items():
            # 1. Balance Sheet: Total Actif vs Total Passif
            if "total_actifs" in metrics and "total_passifs" in metrics:
                act = metrics["total_actifs"].value_normalized or 0.0
                pas = metrics["total_passifs"].value_normalized or 0.0

                if act > 0 and pas > 0:
                    diff = abs(act - pas)
                    rel_diff = diff / max(act, pas)

                    # Check if passif + capitaux_propres equals actif
                    cp = (metrics.get("capitaux_propres") or ExtractedMetricPoint(
                        metric_code="", document_id="", page_number=0, period_year=0, value_original=""
                    )).value_normalized or 0.0

                    pas_plus_cp = pas + cp
                    rel_diff_cp = abs(act - pas_plus_cp) / max(act, pas_plus_cp) if pas_plus_cp > 0 else 1.0

                    if rel_diff > self.tolerance_ratio and rel_diff_cp > self.tolerance_ratio:
                        warn = (
                            f"Year {year}: Balance sheet discrepancy: Total Actif ({act:,.2f}) != "
                            f"Total Passif ({pas:,.2f}, diff={rel_diff:.1%})"
                        )
                        warnings.append(warn)
                        # Route both points to needs_review
                        metrics["total_actifs"].status = "needs_review"
                        metrics["total_actifs"].notes = (metrics["total_actifs"].notes or "") + f" [{warn}]"
                        metrics["total_passifs"].status = "needs_review"
                        metrics["total_passifs"].notes = (metrics["total_passifs"].notes or "") + f" [{warn}]"

            # 2. Monotonicity: Customer loans should not exceed total assets
            if "total_actifs" in metrics and "creances_clients" in metrics:
                act = metrics["total_actifs"].value_normalized or 0.0
                cr = metrics["creances_clients"].value_normalized or 0.0
                if act > 0 and cr > act * (1.0 + self.tolerance_ratio):
                    warn = (
                        f"Year {year}: Créances clients ({cr:,.2f}) exceeds Total Actifs ({act:,.2f})"
                    )
                    warnings.append(warn)
                    metrics["creances_clients"].status = "needs_review"
                    metrics["creances_clients"].notes = (metrics["creances_clients"].notes or "") + f" [{warn}]"

            # 3. Monotonicity: Customer deposits should not exceed total liabilities
            if "total_passifs" in metrics and "depots_clients" in metrics:
                pas = metrics["total_passifs"].value_normalized or 0.0
                dep = metrics["depots_clients"].value_normalized or 0.0
                if pas > 0 and dep > pas * (1.0 + self.tolerance_ratio):
                    warn = (
                        f"Year {year}: Dépôts clients ({dep:,.2f}) exceeds Total Passifs ({pas:,.2f})"
                    )
                    warnings.append(warn)
                    metrics["depots_clients"].status = "needs_review"
                    metrics["depots_clients"].notes = (metrics["depots_clients"].notes or "") + f" [{warn}]"

        is_consistent = len(warnings) == 0
        return is_consistent, warnings
