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

/** Keep the current and previous calendar years selectable even before data arrives. */
export function getSelectableYears(availableYears: number[], currentYear = new Date().getFullYear()): number[] {
  return [...new Set([...availableYears, currentYear, currentYear - 1])].sort((a, b) => b - a);
}

/**
 * Year to display: the requested year if the backend actually holds data for
 * it, otherwise the latest available year, otherwise null (nothing to show).
 */
export function resolveYear(requested: number | null, availableYears: number[]): number | null {
  if (requested !== null && availableYears.includes(requested)) return requested;
  return availableYears.length > 0 ? Math.max(...availableYears) : null;
}

/**
 * An external link taken from the data (source, document, website): only http(s) is ever linked.
 * Anything else (javascript:, data:, a relative path) gives no link (security tests of 22/10/2026).
 */
export function externalHref(url: string | null | undefined): string | undefined {
  if (!url) return undefined;
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:" ? parsed.href : undefined;
  } catch {
    return undefined;
  }
}
