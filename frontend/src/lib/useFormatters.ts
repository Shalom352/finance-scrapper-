"use client";

import { useMemo } from "react";
import { useLocale } from "next-intl";
import {
  formatCompactCurrency,
  formatCurrency,
  formatDate,
  formatNumber,
  formatPercent,
  formatSignedPercent,
} from "@/lib/formatters";

/** Formatters bound to the active next-intl locale. */
export function useFormatters() {
  const locale = useLocale();
  return useMemo(
    () => ({
      locale,
      number: (v: number | null | undefined, decimals = 0) => formatNumber(v, locale, decimals),
      currency: (v: number | null | undefined, currency: string | null | undefined, decimals = 0) =>
        formatCurrency(v, currency, locale, decimals),
      compact: (v: number | null | undefined, currency: string | null | undefined) =>
        formatCompactCurrency(v, currency, locale),
      percent: (v: number | null | undefined, decimals = 2) => formatPercent(v, locale, decimals),
      signedPercent: (v: number | null | undefined, decimals = 2) => formatSignedPercent(v, locale, decimals),
      date: (v: string | null | undefined) => formatDate(v, locale),
    }),
    [locale],
  );
}
