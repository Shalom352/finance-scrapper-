import type { ExplorerSort, FinancialDataExplorerQuery } from "@/lib/api";
import { isUmoaCountry } from "@/lib/countries";

/** Backend export bound (backend `EXPORT_MAX_ROWS`): above it the CSV is refused. */
export const EXPORT_MAX_ROWS = 5000;

export const EXPLORER_PAGE_SIZE = 25;

/** Institutions selectable at once in the explorer filter (keeps the URL and query bounded). */
export const MAX_SELECTED_INSTITUTIONS = 20;

export function parseInstitutionIds(value: string): string[] {
  return [...new Set(value.split(",").map((s) => s.trim()).filter(Boolean))].slice(0, MAX_SELECTED_INSTITUTIONS);
}

export const EXPLORER_SORTS: readonly ExplorerSort[] = ["institution", "country", "indicator", "year", "value"];

/** Explorer defaults: one period type and one scope at a time — never mixed. */
export const DEFAULT_PERIOD_TYPE = "annual";
export const DEFAULT_SCOPE = "individual";

export interface ExplorerParams {
  query: FinancialDataExplorerQuery;
  page: number;
  institutionIds: string[];
}

/** Explorer state read from the URL (deep links survive reload and locale switch). */
export function parseExplorerParams(
  get: (key: string) => string,
  { dimensionDefaults = true }: { dimensionDefaults?: boolean } = {},
): ExplorerParams {
  const year = Number.parseInt(get("year"), 10);
  const page = Number.parseInt(get("page"), 10);
  const country = get("country").toUpperCase();
  const sort = get("sort") as ExplorerSort;
  const institutionIds = parseInstitutionIds(get("inst"));
  return {
    page: Number.isInteger(page) && page > 0 ? page : 1,
    institutionIds,
    query: {
      institution_ids: institutionIds.length > 0 ? institutionIds : undefined,
      country_code: isUmoaCountry(country) ? country : undefined,
      metric_code: get("metric") || undefined,
      period_year: Number.isInteger(year) ? year : undefined,
      period_type: get("period") || (dimensionDefaults ? DEFAULT_PERIOD_TYPE : undefined),
      scope: get("scope") || (dimensionDefaults ? DEFAULT_SCOPE : undefined),
      currency_normalized: get("currency") || undefined,
      status: get("status") || undefined,
      sort: EXPLORER_SORTS.includes(sort) ? sort : undefined,
      order: get("order") === "desc" ? "desc" : "asc",
    },
  };
}
