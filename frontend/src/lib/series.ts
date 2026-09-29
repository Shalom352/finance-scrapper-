/**
 * UMOA Banking Intelligence — Qualified financial series
 *
 * Single qualification layer shared by KPIs, tables and charts, so that every
 * view of an institution displays exactly the same dataset.
 *
 * Mirrors the backend authority rule (scraping/analytics/eligibility.py,
 * `select_authoritative_observation`):
 *   1. keep only the selected period_type and scope (never mix them);
 *   2. drop `rejected` observations and null values;
 *   3. a `verified` observation wins;
 *   4. otherwise rank reviewed > extracted > needs_review;
 *   5. divergent values without a single verified value are a conflict.
 * The frontend has no source priority in list payloads, so a conflict is never
 * resolved arbitrarily: the value becomes `null` and is flagged.
 */

import type { FinancialDataPoint } from "@/types";

export interface QualificationFilter {
  periodType: string;
  scope: string;
}

export interface QualifiedObservation {
  metric_code: string;
  period_year: number;
  /** Authoritative value, or null when absent or in conflict. */
  value: number | null;
  currency: string | null;
  status: string;
  /** Divergent values without a verified observation. */
  conflict: boolean;
  /** Financial data row backing the value (for provenance), null on conflict. */
  data_id: string | null;
}

export interface TimeSeriesPoint {
  year: number;
  value: number | null;
  status?: string;
}

const STATUS_RANK: Record<string, number> = { reviewed: 1, extracted: 2, needs_review: 3 };

function key(metric: string, year: number): string {
  return `${metric}|${year}`;
}

function distinctValues(points: FinancialDataPoint[]): number[] {
  return [...new Set(points.map((p) => p.value_normalized as number))];
}

function pickAuthoritative(candidates: FinancialDataPoint[]): QualifiedObservation {
  const { metric_code, period_year } = candidates[0];
  const conflict = (status: string): QualifiedObservation => ({
    metric_code,
    period_year,
    value: null,
    currency: null,
    status,
    conflict: true,
    data_id: null,
  });
  const chosen = (p: FinancialDataPoint): QualifiedObservation => ({
    metric_code,
    period_year,
    value: p.value_normalized,
    currency: p.currency_normalized ?? null,
    status: p.status,
    conflict: false,
    data_id: p.id,
  });

  const verified = candidates.filter((p) => p.status === "verified");
  if (verified.length > 0) {
    return distinctValues(verified).length === 1 ? chosen(verified[0]) : conflict("verified");
  }

  if (distinctValues(candidates).length > 1) return conflict("needs_review");

  const ranked = [...candidates].sort(
    (a, b) => (STATUS_RANK[a.status] ?? 4) - (STATUS_RANK[b.status] ?? 4),
  );
  return chosen(ranked[0]);
}

/** Qualify raw list rows into one authoritative observation per (metric, year). */
export function qualifyObservations(
  points: FinancialDataPoint[],
  filter: QualificationFilter,
): QualifiedObservation[] {
  const groups = new Map<string, FinancialDataPoint[]>();

  for (const p of points) {
    if (p.period_type !== filter.periodType) continue;
    if (p.scope !== filter.scope) continue;
    if (p.status === "rejected") continue;
    if (p.value_normalized === null || p.value_normalized === undefined || Number.isNaN(p.value_normalized)) continue;

    const k = key(p.metric_code, p.period_year);
    const group = groups.get(k);
    if (group) group.push(p);
    else groups.set(k, [p]);
  }

  return [...groups.values()]
    .map(pickAuthoritative)
    .sort((a, b) => a.metric_code.localeCompare(b.metric_code) || a.period_year - b.period_year);
}

/** Observation for one metric and year, if any (conflicts included, value null). */
export function findObservation(
  qualified: QualifiedObservation[],
  metricCode: string,
  year: number | null,
): QualifiedObservation | undefined {
  if (year === null) return undefined;
  return qualified.find((o) => o.metric_code === metricCode && o.period_year === year);
}

/** Most recent year holding at least one usable value, or null. */
export function latestYear(qualified: QualifiedObservation[]): number | null {
  const years = qualified.filter((o) => o.value !== null).map((o) => o.period_year);
  return years.length > 0 ? Math.max(...years) : null;
}

/**
 * Dense yearly series for one metric: every year between the first and last
 * observation is present; a year without a usable value is `value: null`.
 */
export function buildYearSeries(
  qualified: QualifiedObservation[],
  metricCode: string,
  range?: { from: number; to: number },
): TimeSeriesPoint[] {
  const obs = qualified.filter((o) => o.metric_code === metricCode);
  if (obs.length === 0 && !range) return [];

  const years = obs.map((o) => o.period_year);
  const from = range?.from ?? Math.min(...years);
  const to = range?.to ?? Math.max(...years);

  const series: TimeSeriesPoint[] = [];
  for (let year = from; year <= to; year++) {
    const o = obs.find((x) => x.period_year === year);
    series.push({
      year,
      value: o ? o.value : null,
      status: o ? (o.conflict ? "conflict" : o.status) : "unavailable",
    });
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

/** Distinct values of a field present in the raw rows (for filter selectors). */
export function distinctField(points: FinancialDataPoint[], field: "scope" | "period_type"): string[] {
  return [...new Set(points.map((p) => String(p[field])))].sort();
}
