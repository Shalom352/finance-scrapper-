"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { useLabels } from "@/lib/useLabels";
import { useRatioDefinitions } from "@/lib/useRatioDefinitions";
import { GROWTH_INDICATORS, RATIO_INDICATORS, VOLUME_INDICATORS } from "@/lib/rankings";

const selectCls =
  "mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none";

/**
 * User-facing label of a rankable indicator. Internal codes (DEPOTS_ACTIFS, growth_pnb…)
 * stay in the API and the URL; ratio names come from the backend ratio catalogue.
 */
export function useIndicatorLabel() {
  const t = useTranslations("rankings");
  const labels = useLabels();
  const { ratioName } = useRatioDefinitions();
  return (code: string) =>
    code in GROWTH_INDICATORS
      ? t("growth_of", { metric: labels.metric(GROWTH_INDICATORS[code]) })
      : (RATIO_INDICATORS as readonly string[]).includes(code)
        ? ratioName(code)
        : labels.metric(code);
}

/** Grouped selector of rankable indicators (published metrics, growth, ratios). */
export function IndicatorSelect({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  const t = useTranslations("rankings");
  const indicatorLabel = useIndicatorLabel();

  return (
    <label className="text-[11px] text-gray-400 font-medium">
      {label}
      <select value={value} onChange={(e) => onChange(e.target.value)} className={selectCls}>
        <optgroup label={t("groups.metric")}>
          {VOLUME_INDICATORS.map((c) => (
            <option key={c} value={c}>
              {indicatorLabel(c)}
            </option>
          ))}
        </optgroup>
        <optgroup label={t("groups.growth")}>
          {Object.keys(GROWTH_INDICATORS).map((c) => (
            <option key={c} value={c}>
              {indicatorLabel(c)}
            </option>
          ))}
        </optgroup>
        <optgroup label={t("groups.ratio")}>
          {RATIO_INDICATORS.map((c) => (
            <option key={c} value={c}>
              {indicatorLabel(c)}
            </option>
          ))}
        </optgroup>
      </select>
    </label>
  );
}

export { selectCls };
