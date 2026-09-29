"use client";

import { useFormatters } from "@/lib/useFormatters";

/** Format a ranked / compared value: percentages for ratios and growth, amounts otherwise. */
export function useIndicatorValue() {
  const fmt = useFormatters();
  return (value: number | null | undefined, unit: string, currency: string | null | undefined) =>
    unit === "%" ? fmt.percent(value, 2) : fmt.compact(value, currency);
}
