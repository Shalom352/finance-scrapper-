"""
UMOA Banking Intelligence — Financial Ratio Calculator

Calculates official banking ratios with strict eligibility checks,
unit and currency consistency, zero-division protection, and full component provenance.
"""
from decimal import Decimal
from typing import Any

from scraping.analytics.eligibility import EligibilityEngine
from scraping.analytics.exceptions import (
    CurrencyMismatchError,
    ScopeMismatchError,
    mismatch_kind,
)
from scraping.analytics.models import (
    RatioCalculationResult,
    RatioDefinition,
)
from scraping.consolidation.models import ObservationSummary

# Official definitions of supported financial ratios
RATIO_DEFINITIONS: dict[str, RatioDefinition] = {
    "ROA": RatioDefinition(
        ratio_code="ROA",
        name_fr="Rentabilité des actifs (ROA)",
        name_en="Return on Assets (ROA)",
        description_fr="Rapport du résultat net aux actifs totaux moyens. Mesure l'efficacité avec laquelle la banque utilise ses actifs pour générer du profit.",
        description_en="Ratio of net income to average total assets. Measures how efficiently bank assets generate profit.",
        formula="resultat_net / ((total_actifs_t + total_actifs_t-1) / 2)",
        numerator_metric="resultat_net",
        denominator_metric="total_actifs",
        requires_average_denominator=True,
        unit="%",
        frequency="annual",
        required_metrics=["resultat_net", "total_actifs"],
        eligibility_rules=[
            "Numérateur et dénominateur doivent être libellés dans la même devise (XOF)",
            "L'exercice précédent (t-1) est obligatoire pour calculer les actifs moyens",
            "Les actifs totaux moyens doivent être strictement positifs",
        ],
    ),
    "ROE": RatioDefinition(
        ratio_code="ROE",
        name_fr="Rentabilité des capitaux propres (ROE)",
        name_en="Return on Equity (ROE)",
        description_fr="Rapport du résultat net aux capitaux propres moyens. Mesure le rendement des fonds investis par les actionnaires.",
        description_en="Ratio of net income to average equity. Measures the return on shareholders' funds.",
        formula="resultat_net / ((capitaux_propres_t + capitaux_propres_t-1) / 2)",
        numerator_metric="resultat_net",
        denominator_metric="capitaux_propres",
        requires_average_denominator=True,
        unit="%",
        frequency="annual",
        required_metrics=["resultat_net", "capitaux_propres"],
        eligibility_rules=[
            "Numérateur et dénominateur doivent être libellés dans la même devise (XOF)",
            "L'exercice précédent (t-1) est obligatoire pour calculer les capitaux propres moyens",
            "Des capitaux propres négatifs signalent une détresse financière et rendent le ROE standard ininterprétable",
        ],
    ),
    "DEPOTS_ACTIFS": RatioDefinition(
        ratio_code="DEPOTS_ACTIFS",
        name_fr="Ratio dépôts sur actifs",
        name_en="Deposits to Assets Ratio",
        description_fr="Part des actifs financée par les dépôts de la clientèle. Indicateur de structure de financement bancaire.",
        description_en="Share of assets funded by customer deposits. Core bank funding structure indicator.",
        formula="depots_clients / total_actifs",
        numerator_metric="depots_clients",
        denominator_metric="total_actifs",
        requires_average_denominator=False,
        unit="%",
        frequency="annual",
        required_metrics=["depots_clients", "total_actifs"],
        eligibility_rules=[
            "Même exercice comptable et même devise",
            "Total des actifs strictement positif",
        ],
    ),
    "CREDITS_DEPOTS": RatioDefinition(
        ratio_code="CREDITS_DEPOTS",
        name_fr="Ratio crédits sur dépôts (Loan-to-Deposit)",
        name_en="Loan to Deposit Ratio (LTD)",
        description_fr="Rapport des créances clientèle sur les dépôts reçus. Mesure la transformation bancaire et la liquidité relative.",
        description_en="Ratio of customer loans to customer deposits. Measures liquidity and bank intermediation.",
        formula="creances_clients / depots_clients",
        numerator_metric="creances_clients",
        denominator_metric="depots_clients",
        requires_average_denominator=False,
        unit="%",
        frequency="annual",
        required_metrics=["creances_clients", "depots_clients"],
        eligibility_rules=[
            "Même exercice comptable et même devise",
            "Dépôts clientèle strictement positifs",
        ],
    ),
    "DETTES_ACTIFS": RatioDefinition(
        ratio_code="DETTES_ACTIFS",
        name_fr="Ratio d'endettement financier sur actifs",
        name_en="Debt to Assets Ratio",
        description_fr="Poids des dettes financières totales (emprunts bancaires et titres de créance émis) par rapport au total des actifs.",
        description_en="Proportion of total financial debt relative to total assets.",
        formula="dettes_totales / total_actifs",
        numerator_metric="dettes_totales",
        denominator_metric="total_actifs",
        requires_average_denominator=False,
        unit="%",
        frequency="annual",
        required_metrics=["dettes_totales", "total_actifs"],
        eligibility_rules=[
            "Même exercice comptable et même devise",
            "Total des actifs strictement positif",
        ],
    ),
    "COST_TO_INCOME": RatioDefinition(
        ratio_code="COST_TO_INCOME",
        name_fr="Coefficient d'exploitation (Cost-to-Income)",
        name_en="Cost to Income Ratio (CIR)",
        description_fr="Rapport des charges d'exploitation au produit net bancaire. Mesure l'efficacité opérationnelle.",
        description_en="Operating expenses divided by net banking income. Key efficiency metric.",
        formula="charges_exploitation / produit_net_bancaire",
        numerator_metric="charges_exploitation",
        denominator_metric="produit_net_bancaire",
        requires_average_denominator=False,
        unit="%",
        frequency="annual",
        required_metrics=["produit_net_bancaire"],
        eligibility_rules=[
            "Requiert des charges d'exploitation explicites (charges_totales n'est pas équivalent comptablement)",
            "PNB strictement positif",
        ],
    ),
}


class RatioCalculator:
    """Calculates banking ratios with strict data quality invariants."""

    def __init__(self) -> None:
        self.eligibility = EligibilityEngine()

    def get_definitions(self) -> list[RatioDefinition]:
        """Return the catalogue of all supported ratio definitions."""
        return list(RATIO_DEFINITIONS.values())

    def get_definition(self, ratio_code: str) -> RatioDefinition | None:
        """Return definition for a specific ratio code."""
        return RATIO_DEFINITIONS.get(ratio_code.upper())

    def calculate_ratio(
        self,
        ratio_code: str,
        institution_id: str,
        year: int,
        observations: list[ObservationSummary | Any],
        institution_name: str | None = None,
        country_code: str | None = None,
    ) -> RatioCalculationResult:
        """
        Calculate a specific financial ratio for an institution and year.

        Args:
            ratio_code: Ratio identifier (e.g. "ROA", "ROE", "DEPOTS_ACTIFS", etc.)
            institution_id: Unique bank identifier
            year: Fiscal year (t)
            observations: Set of candidate observations covering needed metrics and periods
            institution_name: Optional bank label
            country_code: Optional ISO country code

        Returns:
            RatioCalculationResult with value, status, explanation, and components
        """
        definition = self.get_definition(ratio_code)
        if not definition:
            return RatioCalculationResult(
                ratio_code=ratio_code,
                ratio_name=ratio_code,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason=f"Unknown ratio code: {ratio_code}",
                formula_used="N/A",
            )

        # Special case: COST_TO_INCOME accounting limitation
        if definition.ratio_code == "COST_TO_INCOME":
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason="unsupported_accounting_component: charges_exploitation is not separated from charges_totales in standard 26 metric catalogue",
                formula_used=definition.formula,
            )

        # Standard ratios
        if definition.requires_average_denominator:
            return self._calculate_average_denominator_ratio(
                definition=definition,
                institution_id=institution_id,
                year=year,
                observations=observations,
                institution_name=institution_name,
                country_code=country_code,
            )
        else:
            return self._calculate_synchronous_ratio(
                definition=definition,
                institution_id=institution_id,
                year=year,
                observations=observations,
                institution_name=institution_name,
                country_code=country_code,
            )

    def _calculate_synchronous_ratio(
        self,
        definition: RatioDefinition,
        institution_id: str,
        year: int,
        observations: list[ObservationSummary | Any],
        institution_name: str | None,
        country_code: str | None,
    ) -> RatioCalculationResult:
        """Calculate synchronous single-year ratio (e.g. depots_clients / total_actifs)."""
        num_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == definition.numerator_metric
            and getattr(obs, "period_year", None) == year
        ]
        den_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == definition.denominator_metric
            and getattr(obs, "period_year", None) == year
        ]

        best_num, num_conflict = self.eligibility.select_authoritative_observation(num_candidates)
        best_den, den_conflict = self.eligibility.select_authoritative_observation(den_candidates)

        if not best_num or not best_den:
            missing = []
            if not best_num:
                missing.append(f"{definition.numerator_metric} ({year})")
            if not best_den:
                missing.append(f"{definition.denominator_metric} ({year})")
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason=f"Missing required component(s): {', '.join(missing)}",
                formula_used=definition.formula,
            )

        comp_num = self.eligibility.to_component_provenance(best_num, role="numerator")
        comp_den = self.eligibility.to_component_provenance(best_den, role="denominator")
        components = [comp_num, comp_den]

        # Check currency compatibility
        try:
            self.eligibility.validate_currency_compatibility(components)
            self.eligibility.validate_scope_compatibility(components)
        except (CurrencyMismatchError, ScopeMismatchError) as e:
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason=f"{mismatch_kind(e)}_mismatch: {e}",
                formula_used=definition.formula,
                components=components,
            )

        num_val = comp_num.value_normalized
        den_val = comp_den.value_normalized

        if den_val is None or den_val == Decimal("0"):
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason="zero_denominator: Denominator is zero or missing",
                formula_used=definition.formula,
                components=components,
            )

        if den_val < Decimal("0"):
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="needs_review",
                reason="negative_denominator: Denominator value is negative",
                formula_used=definition.formula,
                components=components,
            )

        raw_ratio = num_val / den_val
        val_pct = float(raw_ratio * Decimal("100"))

        status = self.eligibility.determine_ratio_status(
            components, has_conflict=(num_conflict or den_conflict)
        )

        return RatioCalculationResult(
            ratio_code=definition.ratio_code,
            ratio_name=definition.name_fr,
            institution_id=institution_id,
            institution_name=institution_name,
            country_code=country_code,
            period_year=year,
            value=raw_ratio,
            value_percent=val_pct,
            unit=definition.unit,
            status=status,
            formula_used=definition.formula,
            components=components,
        )

    def _calculate_average_denominator_ratio(
        self,
        definition: RatioDefinition,
        institution_id: str,
        year: int,
        observations: list[ObservationSummary | Any],
        institution_name: str | None,
        country_code: str | None,
    ) -> RatioCalculationResult:
        """Calculate ratio with multi-year average denominator (ROA and ROE)."""
        prev_year = year - 1

        num_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == definition.numerator_metric
            and getattr(obs, "period_year", None) == year
        ]
        den_curr_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == definition.denominator_metric
            and getattr(obs, "period_year", None) == year
        ]
        den_prev_candidates = [
            obs for obs in observations
            if getattr(obs, "metric_code", None) == definition.denominator_metric
            and getattr(obs, "period_year", None) == prev_year
        ]

        best_num, num_conflict = self.eligibility.select_authoritative_observation(num_candidates)
        best_den_curr, den_curr_conflict = self.eligibility.select_authoritative_observation(den_curr_candidates)
        best_den_prev, den_prev_conflict = self.eligibility.select_authoritative_observation(den_prev_candidates)

        missing = []
        if not best_num:
            missing.append(f"{definition.numerator_metric} ({year})")
        if not best_den_curr:
            missing.append(f"{definition.denominator_metric} ({year})")
        if not best_den_prev:
            missing.append(f"{definition.denominator_metric} ({prev_year})")

        if missing:
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason=f"Missing component for average calculation: {', '.join(missing)}",
                formula_used=definition.formula,
            )

        comp_num = self.eligibility.to_component_provenance(best_num, role="numerator")
        comp_den_curr = self.eligibility.to_component_provenance(best_den_curr, role="denominator_current_year")
        comp_den_prev = self.eligibility.to_component_provenance(best_den_prev, role="denominator_previous_year")
        components = [comp_num, comp_den_curr, comp_den_prev]

        # Validate currencies
        try:
            self.eligibility.validate_currency_compatibility(components)
            self.eligibility.validate_scope_compatibility(components)
        except (CurrencyMismatchError, ScopeMismatchError) as e:
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason=f"{mismatch_kind(e)}_mismatch: {e}",
                formula_used=definition.formula,
                components=components,
            )

        num_val = comp_num.value_normalized
        avg_den = (comp_den_curr.value_normalized + comp_den_prev.value_normalized) / Decimal("2")

        if avg_den == Decimal("0"):
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="unavailable",
                reason="zero_denominator: Average denominator is zero",
                formula_used=definition.formula,
                components=components,
            )

        if avg_den < Decimal("0"):
            return RatioCalculationResult(
                ratio_code=definition.ratio_code,
                ratio_name=definition.name_fr,
                institution_id=institution_id,
                institution_name=institution_name,
                country_code=country_code,
                period_year=year,
                status="needs_review",
                reason=f"negative_denominator: Average {definition.denominator_metric} is negative ({avg_den})",
                formula_used=definition.formula,
                components=components,
            )

        raw_ratio = num_val / avg_den
        val_pct = float(raw_ratio * Decimal("100"))

        status = self.eligibility.determine_ratio_status(
            components, has_conflict=(num_conflict or den_curr_conflict or den_prev_conflict)
        )

        return RatioCalculationResult(
            ratio_code=definition.ratio_code,
            ratio_name=definition.name_fr,
            institution_id=institution_id,
            institution_name=institution_name,
            country_code=country_code,
            period_year=year,
            value=raw_ratio,
            value_percent=val_pct,
            unit=definition.unit,
            status=status,
            formula_used=definition.formula,
            components=components,
        )
