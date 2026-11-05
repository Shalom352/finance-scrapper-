"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ProfileValue, UnavailableValue } from "@/types";
import { MISSING, displayCurrency } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";
import { SortHeader } from "@/components/common/SortHeader";
import { useSort, type SortDir } from "@/lib/useSort";

type FinSortKey = "metric" | "year" | "status";
const FIN_FIRST: Record<FinSortKey, SortDir> = { metric: "asc", year: "desc", status: "asc" };

interface FinancialDataTableProps {
  /** Values qualified by the backend (GET /institutions/{id}/financials). */
  values: ProfileValue[];
  /** Indicators without an admissible value, with their reason. */
  unavailable?: UnavailableValue[];
  onProvenance: (dataId: string) => void;
  title?: string;
  className?: string;
}

export function FinancialDataTable({ values, unavailable = [], onProvenance, title, className = "" }: FinancialDataTableProps) {
  const t = useTranslations("tables.financial");
  const fmt = useFormatters();
  const labels = useLabels();
  const reason = useReasonLabel();
  // Values are not sortable by amount (currencies are never mixed); newest year first by default.
  const { sorted, sortKey, dir, toggle } = useSort(
    values,
    { metric: (v) => labels.metric(v.metric_code), year: (v) => v.period_year, status: (v) => v.status },
    { key: "year", dir: "desc" },
  );
  const head = (key: FinSortKey, cls = "") => (
    <SortHeader label={t(key)} active={sortKey === key} dir={dir} onClick={() => toggle(key, FIN_FIRST[key])}
      className={`py-3 px-4 ${cls}`} testId={`fin-sort-${key}`} />
  );

  if (values.length === 0 && unavailable.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-200 ${className}`}>
        {t("empty")}
      </div>
    );
  }

  return (
    <div className={`overflow-x-auto rounded-2xl border border-gray-200 bg-white ${className}`}>
      {title && (
        <div className="px-5 py-4 border-b border-gray-200">
          <h4 className="text-sm font-semibold text-gray-800">{title}</h4>
        </div>
      )}
      <table className="w-full min-w-[720px] text-left text-xs border-collapse" data-testid="financial-table">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase tracking-wider">
            {head("metric")}
            {head("year")}
            <th className="py-3 px-4">{t("original")}</th>
            <th className="py-3 px-4 text-right">{t("value")}</th>
            <th className="py-3 px-4">{t("currency")}</th>
            {head("status", "text-center")}
            <th className="py-3 px-4 text-center">{t("audit")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((v) => (
            <tr key={v.data_id} className="hover:bg-gray-50 transition-colors" data-testid="financial-row">
              <td className="py-3 px-4 font-semibold text-gray-800">{labels.metric(v.metric_code)}</td>
              <td className="py-3 px-4 text-gray-700">{v.period_year}</td>
              <td className="py-3 px-4 font-mono text-gray-500">
                {[v.value_original, v.unit_original].filter(Boolean).join(" ") || MISSING}
              </td>
              <td className="py-3 px-4 text-right font-bold text-emerald-700">{fmt.currency(v.value_normalized, v.currency)}</td>
              <td className="py-3 px-4 text-gray-500">{displayCurrency(v.currency) || MISSING}</td>
              <td className="py-3 px-4 text-center">
                <StatusBadge status={v.status} size="sm" />
              </td>
              <td className="py-3 px-4 text-center">
                <button
                  onClick={() => onProvenance(v.data_id)}
                  className="p-1 px-2 rounded-lg bg-gray-100 hover:bg-emerald-600 text-gray-700 hover:text-white text-xs"
                  title={t("audit_title")}
                >
                  🔍
                </button>
              </td>
            </tr>
          ))}
          {unavailable.map((u) => (
            <tr key={`${u.metric_code}-${u.period_year ?? ""}`} data-testid="financial-unavailable-row">
              <td className="py-3 px-4 font-semibold text-gray-500">{labels.metric(u.metric_code)}</td>
              <td className="py-3 px-4 text-gray-500">{u.period_year ?? MISSING}</td>
              <td className="py-3 px-4 text-gray-500">{MISSING}</td>
              <td className="py-3 px-4 text-right text-gray-500">{MISSING}</td>
              <td className="py-3 px-4 text-gray-500">{MISSING}</td>
              <td className="py-3 px-4 text-center">
                <StatusBadge status={u.status} size="sm" />
              </td>
              <td className="py-3 px-4 text-center text-[11px] text-gray-500">{reason(u.reason)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
