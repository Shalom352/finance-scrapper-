/**
 * Strict label ↔ metric ↔ API response mapping for sector KPIs.
 *
 * A KPI only ever receives an aggregation whose `metric_code` and `year` match
 * its binding. Anything else (failed call, other metric, other year) resolves
 * to null and is displayed as "—" — a total of assets can never be shown under
 * a deposits label.
 */

import type { SectorAggregation } from "@/types";

export interface KpiBinding {
  /** Translation key under `kpi.*`. */
  labelKey: "total_assets" | "total_deposits" | "total_loans";
  metric_code: string;
}

export const SECTOR_KPI_BINDINGS: readonly KpiBinding[] = [
  { labelKey: "total_assets", metric_code: "total_actifs" },
  { labelKey: "total_deposits", metric_code: "depots_clients" },
  { labelKey: "total_loans", metric_code: "creances_clients" },
] as const;

export function resolveKpi(
  binding: KpiBinding,
  year: number,
  aggregations: (SectorAggregation | null | undefined)[],
): SectorAggregation | null {
  return (
    aggregations.find(
      (a): a is SectorAggregation => !!a && a.metric_code === binding.metric_code && a.year === year,
    ) ?? null
  );
}
