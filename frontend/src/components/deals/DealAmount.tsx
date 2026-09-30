"use client";

import { displayCurrency, MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useDealLabels } from "@/components/deals/DealLabels";

/** Amount exactly as stored: value + unit as published + currency. Never converted, never 0 when missing. */
export function useDealAmount() {
  const fmt = useFormatters();
  const labels = useDealLabels();
  return (amount: number | null, currency: string | null, unit: string | null) => {
    if (amount === null || amount === undefined || Number.isNaN(amount)) return MISSING;
    const parts = [fmt.number(amount, Number.isInteger(amount) ? 0 : 2)];
    if (unit && unit !== "units") parts.push(labels.unit(unit));
    const cur = displayCurrency(currency);
    if (cur) parts.push(cur);
    return parts.join(" ");
  };
}
