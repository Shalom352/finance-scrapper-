/**
 * URL helpers.
 */

/**
 * Locale-free href for the current page that keeps every query parameter
 * (search, filters, pagination, selected year) when switching language.
 *   buildLocaleHref("/search", "q=banque&page=2") → "/search?q=banque&page=2"
 */
export function buildLocaleHref(
  pathname: string,
  searchParams: URLSearchParams | { toString(): string } | string | null | undefined,
): string {
  const qs = searchParams ? searchParams.toString().replace(/^\?/, "") : "";
  return qs ? `${pathname}?${qs}` : pathname;
}

/** Parse a `?year=` value: a positive integer, otherwise null. */
export function parseYearParam(value: string | string[] | null | undefined): number | null {
  const raw = Array.isArray(value) ? value[0] : value;
  if (!raw || !/^\d{4}$/.test(raw)) return null;
  return Number(raw);
}

/**
 * Year to display: the requested year if the backend actually holds data for
 * it, otherwise the latest available year, otherwise null (nothing to show).
 */
export function resolveYear(requested: number | null, availableYears: number[]): number | null {
  if (requested !== null && availableYears.includes(requested)) return requested;
  return availableYears.length > 0 ? Math.max(...availableYears) : null;
}
