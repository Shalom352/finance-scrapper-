"use client";

import { useMemo } from "react";
import { useTranslations } from "next-intl";
import { MISSING } from "@/lib/formatters";

/** Translated deal codes. An unknown code is shown as received (never guessed); a missing one as MISSING. */
export function useDealLabels() {
  const tType = useTranslations("deals.types");
  const tRole = useTranslations("deals.roles");
  const tRate = useTranslations("deals.rate_types");
  const tUnit = useTranslations("deals.units");
  const tCrit = useTranslations("deals.duplicates.criteria_names");
  const tField = useTranslations("deals.detail.fields");
  return useMemo(() => {
    const code = (t: typeof tType) => (v: string | null | undefined) => (v ? (t.has(v) ? t(v) : v) : MISSING);
    return {
      type: code(tType),
      role: code(tRole),
      rateType: code(tRate),
      unit: code(tUnit),
      criterion: code(tCrit),
      field: code(tField),
    };
  }, [tType, tRole, tRate, tUnit, tCrit, tField]);
}
