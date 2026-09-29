/**
 * Rankable indicators (mirror of backend scraping/rankings/definitions.py).
 * Rankings are descriptive numerical orderings only — never a judgement.
 */

export const VOLUME_INDICATORS = [
  "total_actifs",
  "depots_clients",
  "creances_clients",
  "capitaux_propres",
  "produit_net_bancaire",
  "resultat_net",
] as const;

/** growth_<alias> → underlying published metric. */
export const GROWTH_INDICATORS: Record<string, string> = {
  growth_total_actifs: "total_actifs",
  growth_depots_clients: "depots_clients",
  growth_creances_clients: "creances_clients",
  growth_pnb: "produit_net_bancaire",
  growth_resultat_net: "resultat_net",
  growth_capitaux_propres: "capitaux_propres",
};

export const RATIO_INDICATORS = ["ROA", "ROE", "DEPOTS_ACTIFS", "CREDITS_DEPOTS", "DETTES_ACTIFS", "COST_TO_INCOME"] as const;

export const DEFAULT_INDICATOR = "total_actifs";
export const PERIOD_TYPES = ["annual", "semi_annual", "quarterly"] as const;
export const DATA_SCOPES = ["individual", "consolidated"] as const;
export const UMOA = "UMOA";

export type IndicatorKind = "metric" | "growth" | "ratio";

export function indicatorKind(code: string): IndicatorKind | null {
  if ((VOLUME_INDICATORS as readonly string[]).includes(code)) return "metric";
  if (code in GROWTH_INDICATORS) return "growth";
  if ((RATIO_INDICATORS as readonly string[]).includes(code)) return "ratio";
  return null;
}

export function isRankableIndicator(code: string): boolean {
  return indicatorKind(code) !== null;
}

/** Growth and ratios are annual indicators only. */
export function supportsPeriodType(code: string, periodType: string): boolean {
  return indicatorKind(code) === "metric" || periodType === "annual";
}

export function pick<T extends string>(value: string, allowed: readonly T[], fallback: T): T {
  return (allowed as readonly string[]).includes(value) ? (value as T) : fallback;
}

export interface RankingParams {
  metric: string;
  year: number | null;
  country: string;
  scope: (typeof DATA_SCOPES)[number];
  period: (typeof PERIOD_TYPES)[number];
  order: "desc" | "asc";
  page: number;
  institution: string | null;
}

/**
 * Ranking filters read from the URL (kept on reload and locale switch).
 * Invalid values fall back to the documented safe defaults — never to an invented year.
 */
export function parseRankingParams(get: (key: string) => string): RankingParams {
  const metric = get("metric");
  const year = get("year");
  const country = get("country").toUpperCase();
  return {
    metric: isRankableIndicator(metric) ? metric : DEFAULT_INDICATOR,
    year: /^\d{4}$/.test(year) ? Number(year) : null,
    country: country === UMOA || /^[A-Z]{2}$/.test(country) ? country : UMOA,
    scope: pick(get("scope"), DATA_SCOPES, "individual"),
    period: pick(get("period"), PERIOD_TYPES, "annual"),
    order: get("order") === "asc" ? "asc" : "desc",
    page: Math.max(Number(get("page")) || 1, 1),
    institution: get("institution") || null,
  };
}

export const MIN_COMPARED = 2;
export const MAX_COMPARED = 5;

/** Selected institution ids from `?ids=a,b,c`: distinct, at most MAX_COMPARED. */
export function parseIds(value: string): string[] {
  return [...new Set(value.split(",").map((s) => s.trim()).filter(Boolean))].slice(0, MAX_COMPARED);
}
