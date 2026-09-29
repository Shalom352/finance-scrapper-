/**
 * UMOA Banking Intelligence — Chart series helpers (display only).
 *
 * Qualification (period type, scope, rejected, conflicts, needs_review, authority
 * rule) is done by the backend only — GET /api/v1/institutions/{id}/history
 * (Phase 10, scraping/institutions/service.py, EligibilityEngine). These helpers
 * never select, filter or compute a value: they only lay out the points returned
 * by the API so that a missing year is drawn as a gap, never as zero.
 */

export interface TimeSeriesPoint {
  year: number;
  value: number | null;
  status?: string;
}

/**
 * Dense yearly series from API points: every year between the first and the last
 * point is present; a year without a point is `value: null` (a gap).
 */
export function buildYearSeries(
  points: { period_year: number; value: number | null; status?: string }[],
  range?: { from: number; to: number },
): TimeSeriesPoint[] {
  if (points.length === 0 && !range) return [];
  const years = points.map((p) => p.period_year);
  const from = range?.from ?? Math.min(...years);
  const to = range?.to ?? Math.max(...years);

  const series: TimeSeriesPoint[] = [];
  for (let year = from; year <= to; year++) {
    const p = points.find((x) => x.period_year === year);
    series.push({ year, value: p ? p.value : null, status: p ? p.status : "unavailable" });
  }
  return series;
}

/**
 * Split a series into drawable segments. A segment breaks on a null value AND
 * on any missing year between two points, so a line never bridges a gap even
 * if the caller passes a sparse series.
 */
export function toSegments(points: TimeSeriesPoint[]): TimeSeriesPoint[][] {
  const sorted = [...points].sort((a, b) => a.year - b.year);
  const segments: TimeSeriesPoint[][] = [];
  let current: TimeSeriesPoint[] = [];

  for (const p of sorted) {
    const usable = p.value !== null && p.value !== undefined && !Number.isNaN(p.value);
    const prev = current[current.length - 1];
    if (!usable || (prev && p.year !== prev.year + 1)) {
      if (current.length > 0) segments.push(current);
      current = [];
    }
    if (usable) current.push(p);
  }
  if (current.length > 0) segments.push(current);
  return segments;
}
