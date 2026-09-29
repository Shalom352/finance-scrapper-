"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { GrowthResult } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

/** Year-over-year changes as computed by GrowthCalculator; an unavailable change shows its reason, never 0 %. */
export function GrowthTable({ items }: { items: GrowthResult[] }) {
  const t = useTranslations("explorer");
  const fmt = useFormatters();
  const labels = useLabels();
  const reason = useReasonLabel();

  if (items.length === 0) {
    return <p className="text-xs text-gray-500">{t("growth_empty")}</p>;
  }

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse" data-testid="growth-table">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
            <th className="py-3 px-4">{t("indicator")}</th>
            <th className="py-3 px-4">{t("periods")}</th>
            <th className="py-3 px-4 text-right">{t("value_current")}</th>
            <th className="py-3 px-4 text-right">{t("value_previous")}</th>
            <th className="py-3 px-4 text-right">{t("change_abs")}</th>
            <th className="py-3 px-4 text-right">{t("change_pct")}</th>
            <th className="py-3 px-4 text-center">{t("status")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {items.map((g) => {
            const pct = g.growth_percent;
            return (
              <tr key={`${g.metric_code}-${g.current_year}`} data-testid="growth-row">
                <td className="py-3 px-4 font-semibold text-gray-200">{labels.metric(g.metric_code)}</td>
                <td className="py-3 px-4 text-gray-400">
                  {g.previous_year} → {g.current_year}
                </td>
                <td className="py-3 px-4 text-right text-gray-300">{fmt.compact(g.current_value, g.currency)}</td>
                <td className="py-3 px-4 text-right text-gray-400">{fmt.compact(g.previous_value, g.currency)}</td>
                <td className="py-3 px-4 text-right text-gray-300">{fmt.compact(g.absolute_change, g.currency)}</td>
                <td className={`py-3 px-4 text-right font-bold ${pct === null ? "text-gray-500" : "text-white"}`} data-testid="growth-pct">
                  {pct === null ? MISSING : fmt.signedPercent(pct, 2)}
                  {pct === null && (
                    // Translated reason; the calculator's technical detail stays in the tooltip.
                    <span className="block text-[10px] font-normal text-gray-500" title={g.reason ?? undefined}>
                      {reason(g.status === "needs_review" ? "needs_review" : "growth_period_missing")}
                    </span>
                  )}
                </td>
                <td className="py-3 px-4 text-center">
                  <StatusBadge status={g.status} size="sm" />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
