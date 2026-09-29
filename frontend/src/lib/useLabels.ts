"use client";

import { useCallback, useMemo } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { Country } from "@/types";

/** Translated labels for codes coming from the API. Unknown codes are shown verbatim, never guessed. */
export function useLabels() {
  const locale = useLocale();
  const tMetric = useTranslations("metrics");
  const tScope = useTranslations("scope");
  const tPeriod = useTranslations("period_type");
  const tCountry = useTranslations("country_names");
  const tDocType = useTranslations("document_types");
  const tInstType = useTranslations("institution_types");

  const lookup = useCallback(
    (t: ReturnType<typeof useTranslations>, code: string | null | undefined) =>
      code && t.has(code) ? t(code) : (code ?? ""),
    [],
  );

  return useMemo(
    () => ({
      metric: (code: string | null | undefined) => lookup(tMetric, code),
      scope: (code: string | null | undefined) => lookup(tScope, code),
      periodType: (code: string | null | undefined) => lookup(tPeriod, code),
      documentType: (code: string | null | undefined) => lookup(tDocType, code),
      institutionType: (code: string | null | undefined) => lookup(tInstType, code),
      /** Country name from the API when present, else the dictionary, else the code. */
      country: (country: Country | null | undefined, code?: string | null) => {
        if (country) return locale === "en" ? country.name_en : country.name_fr;
        return lookup(tCountry, code);
      },
    }),
    [locale, lookup, tMetric, tScope, tPeriod, tCountry, tDocType, tInstType],
  );
}
