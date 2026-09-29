"use client";

import { useTranslations } from "next-intl";

/** Translated explanation of why a value / ranking is not available. Unknown codes are shown verbatim. */
export function useReasonLabel() {
  const t = useTranslations("ranking_reasons");
  return (reason: string | null | undefined) => (reason ? (t.has(reason) ? t(reason) : reason) : "");
}
