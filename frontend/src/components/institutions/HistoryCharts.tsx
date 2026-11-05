"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { HistorySeries, InstitutionHistory } from "@/types";
import { MISSING, displayCurrency } from "@/lib/formatters";
import { buildYearSeries } from "@/lib/series";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { FinancialLineChart } from "@/components/charts/FinancialLineChart";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";
import { SortHeader } from "@/components/common/SortHeader";
import { useSort } from "@/lib/useSort";

/** A line needs at least two real points of one currency; otherwise no chart is drawn. */
export function isChartable(series: HistorySeries): boolean {
  return series.status !== "needs_review" && series.status !== "unavailable" && series.points.length >= 2;
}

function SeriesBlock({ series, onProvenance }: { series: HistorySeries; onProvenance: (dataId: string) => void }) {
  const t = useTranslations("explorer");
  const fmt = useFormatters();
  const labels = useLabels();
  const reason = useReasonLabel();
  const unit = series.points[0]?.unit_normalized;
  const currency = displayCurrency(series.currency);
  // One currency per series, so a value sort is meaningful here; newest year first by default.
  const { sorted, sortKey, dir, toggle } = useSort(
    series.points,
    { year: (p) => p.period_year, value: (p) => p.value, status: (p) => p.status },
    { key: "year", dir: "desc" },
  );
  const head = (key: "year" | "value" | "status", first: "asc" | "desc", cls = "") => (
    <SortHeader label={t(key)} active={sortKey === key} dir={dir} onClick={() => toggle(key, first)}
      className={`py-1.5 pr-2 ${cls}`} />
  );

  return (
    <div className="p-4 rounded-2xl border border-gray-200 bg-white space-y-3" data-testid="history-series">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-gray-800">{labels.metric(series.metric_code)}</h3>
        <span className="text-[11px] text-gray-500" data-testid="series-unit">
          {t("unit_currency", { unit: unit || MISSING, currency: currency || MISSING })}
        </span>
      </div>

      {isChartable(series) ? (
        <FinancialLineChart data={buildYearSeries(series.points)} currency={series.currency} height={200} />
      ) : (
        <p className="p-4 rounded-xl border border-dashed border-gray-200 text-xs text-gray-500" data-testid="insufficient-data">
          {series.reason === "heterogeneous_currency" ? reason(series.reason) : t("insufficient_data")}
        </p>
      )}

      <div className="overflow-x-auto">
      <table className="w-full min-w-[320px] text-left text-xs border-collapse">
        <thead>
          <tr className="border-b border-gray-200 text-gray-500 uppercase tracking-wider">
            {head("year", "desc")}
            {head("value", "desc", "text-right")}
            {head("status", "asc")}
            <th className="py-1.5 text-center">{t("provenance")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((p) => (
            <tr key={p.period_year} data-testid="history-point">
              <td className="py-1.5 pr-2 text-gray-700">{p.period_year}</td>
              <td className="py-1.5 pr-2 text-right font-semibold text-gray-900">{fmt.compact(p.value, p.currency)}</td>
              <td className="py-1.5 pr-2">
                <StatusBadge status={p.status} size="sm" />
              </td>
              <td className="py-1.5 text-center">
                <button onClick={() => onProvenance(p.data_id)} className="text-emerald-700" title={t("open_provenance")}>
                  🔍
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      {series.missing_years.length > 0 && (
        <p className="text-[11px] text-gray-500" data-testid="missing-years">
          {t("missing_years", { years: series.missing_years.join(", ") })}
        </p>
      )}
      {series.excluded_years.length > 0 && (
        <ul className="text-[11px] text-amber-700 space-y-0.5" data-testid="excluded-years">
          {series.excluded_years.map((u) => (
            <li key={`${u.metric_code}-${u.period_year}`}>
              {u.period_year} : {reason(u.reason)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function HistoryCharts({
  history,
  onProvenance,
}: {
  history: InstitutionHistory;
  onProvenance: (dataId: string) => void;
}) {
  const t = useTranslations("explorer");
  const reason = useReasonLabel();

  if (history.series.length === 0) {
    return (
      <p className="p-6 rounded-2xl border border-dashed border-gray-200 text-sm text-gray-500" data-testid="history-unavailable">
        {t("history_unavailable")} — {reason(history.reason)}
      </p>
    );
  }
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      {history.series.map((s) => (
        <SeriesBlock key={s.metric_code} series={s} onProvenance={onProvenance} />
      ))}
    </div>
  );
}
