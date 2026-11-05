"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { RatioResult } from "@/types";
import { useFormatters } from "@/lib/useFormatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";
import { useRatioDefinitions } from "@/lib/useRatioDefinitions";
import { SortHeader } from "@/components/common/SortHeader";
import { useSort, type SortDir } from "@/lib/useSort";

type RatioSortKey = "code" | "name" | "year" | "value" | "status";
const RATIO_FIRST: Record<RatioSortKey, SortDir> = { code: "asc", name: "asc", year: "desc", value: "desc", status: "asc" };

interface RatioDataTableProps {
  ratios: RatioResult[];
  title?: string;
  className?: string;
}

export function RatioDataTable({ ratios, title, className = "" }: RatioDataTableProps) {
  const t = useTranslations("tables.ratios");
  const fmt = useFormatters();
  const reason = useReasonLabel();
  const { ratioName } = useRatioDefinitions();
  const [selectedRatio, setSelectedRatio] = useState<RatioResult | null>(null);
  const { sorted, sortKey, dir, toggle } = useSort(
    ratios,
    {
      code: (r) => r.ratio_code,
      name: (r) => ratioName(r.ratio_code),
      year: (r) => r.period_year,
      value: (r) => r.value_percent,
      status: (r) => r.status,
    },
    { key: "year", dir: "desc" },
  );
  const head = (key: RatioSortKey, cls = "") => (
    <SortHeader label={t(key)} active={sortKey === key} dir={dir} onClick={() => toggle(key, RATIO_FIRST[key])}
      className={`py-3 px-4 ${cls}`} testId={`ratio-sort-${key}`} />
  );

  if (ratios.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-200 ${className}`}>
        {t("empty")}
      </div>
    );
  }

  return (
    <>
      <div className={`overflow-x-auto rounded-2xl border border-gray-200 bg-white ${className}`}>
        {title && (
          <div className="px-5 py-4 border-b border-gray-200">
            <h4 className="text-sm font-semibold text-gray-800">{title}</h4>
          </div>
        )}

        <table className="w-full min-w-[760px] text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase tracking-wider">
              {head("code")}
              {head("name")}
              {head("year")}
              <th className="py-3 px-4">{t("formula")}</th>
              {head("value", "text-right")}
              {head("status", "text-center")}
              <th className="py-3 px-4 text-center">{t("components")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((r, idx) => (
              <tr
                key={`${r.ratio_code}-${r.institution_id}-${r.period_year}-${idx}`}
                className="hover:bg-gray-50 transition-colors group cursor-pointer"
                onClick={() => setSelectedRatio(r)}
              >
                <td className="py-3.5 px-4 font-mono font-bold text-emerald-700">{r.ratio_code}</td>
                <td className="py-3.5 px-4 font-medium text-gray-800">
                  <div>{ratioName(r.ratio_code)}</div>
                  {r.institution_name && <span className="text-[11px] text-gray-500 block">{r.institution_name}</span>}
                  {r.reason && (
                    // Translated reason; the calculator's technical detail stays in the tooltip.
                    <span className="text-[11px] text-amber-700 block mt-0.5" title={r.reason}>
                      {reason(r.status === "needs_review" ? "needs_review" : "ratio_component_missing")}
                    </span>
                  )}
                </td>
                <td className="py-3.5 px-4 text-gray-700">{r.period_year}</td>
                <td className="py-3.5 px-4 font-mono text-[11px] text-gray-500">{r.formula_used}</td>
                <td className="py-3.5 px-4 text-right font-black text-sm">
                  <span className={r.value_percent === null ? "text-gray-500" : "text-emerald-700"}>
                    {fmt.percent(r.value_percent, 2)}
                  </span>
                </td>
                <td className="py-3.5 px-4 text-center">
                  <StatusBadge status={r.status} size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedRatio(r);
                    }}
                    className="p-1 px-2 rounded-lg bg-gray-100 group-hover:bg-emerald-600 text-gray-700 group-hover:text-white transition-colors text-xs font-semibold"
                  >
                    {t("components_count", { count: r.components.length })}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedRatio && <ProvenancePanel ratioPoint={selectedRatio} onClose={() => setSelectedRatio(null)} />}
    </>
  );
}
