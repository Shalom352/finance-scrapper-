"""
Rankable indicators.

Three kinds, all built on existing definitions (nothing new is computed here):
  - "metric": a published financial item (value in its currency);
  - "growth": year-over-year variation from GrowthCalculator (percent);
  - "ratio":  a ratio from RatioCalculator / RATIO_DEFINITIONS (percent).
Growth and ratios are annual indicators only (RATIO_DEFINITIONS frequency="annual").
"""
from dataclasses import dataclass
from typing import Literal

from scraping.analytics.growth_calculator import CORE_GROWTH_METRICS
from scraping.analytics.ratio_calculator import RATIO_DEFINITIONS

RankKind = Literal["metric", "growth", "ratio"]

ANNUAL = "annual"
PERIOD_TYPES = ("annual", "semi_annual", "quarterly")


@dataclass(frozen=True)
class RankableIndicator:
    code: str
    kind: RankKind
    # Financial metric whose observations determine the available periods.
    base_metric: str
    # Unit of the ranked value: "currency" (value in its own currency) or "%".
    unit: str

    @property
    def annual_only(self) -> bool:
        return self.kind in ("growth", "ratio")


VOLUME_METRICS = (
    "total_actifs",
    "depots_clients",
    "creances_clients",
    "capitaux_propres",
    "produit_net_bancaire",
    "resultat_net",
)

# growth_<alias> → base metric; only metrics GrowthCalculator actually supports are exposed.
_GROWTH_ALIASES = {
    "growth_total_actifs": "total_actifs",
    "growth_depots_clients": "depots_clients",
    "growth_creances_clients": "creances_clients",
    "growth_pnb": "produit_net_bancaire",
    "growth_resultat_net": "resultat_net",
    "growth_capitaux_propres": "capitaux_propres",
}


def _build() -> dict[str, RankableIndicator]:
    indicators: dict[str, RankableIndicator] = {}
    for code in VOLUME_METRICS:
        indicators[code] = RankableIndicator(code=code, kind="metric", base_metric=code, unit="currency")
    for code, base in _GROWTH_ALIASES.items():
        if base in CORE_GROWTH_METRICS:
            indicators[code] = RankableIndicator(code=code, kind="growth", base_metric=base, unit="%")
    for code, definition in RATIO_DEFINITIONS.items():
        indicators[code] = RankableIndicator(
            code=code, kind="ratio", base_metric=definition.numerator_metric, unit="%"
        )
    return indicators


RANKABLE_INDICATORS: dict[str, RankableIndicator] = _build()


def get_indicator(code: str) -> RankableIndicator | None:
    return RANKABLE_INDICATORS.get(code) or RANKABLE_INDICATORS.get(code.upper())
