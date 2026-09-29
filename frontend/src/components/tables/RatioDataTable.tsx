"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { RatioResult } from "@/types";
import { useFormatters } from "@/lib/useFormatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";

interface RatioDataTableProps {
  ratios: RatioResult[];
  title?: string;
  className?: string;
}

export function RatioDataTable({ ratios, title, className = "" }: RatioDataTableProps) {
  const t = useTranslations("tables.ratios");
  const fmt = useFormatters();
  const [selectedRatio, setSelectedRatio] = useState<RatioResult | null>(null);

  if (ratios.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        {t("empty")}
      </div>
    );
  }

  return (
    <>
      <div className={`overflow-x-auto rounded-2xl border border-gray-800 bg-gray-900/30 ${className}`}>
        {title && (
          <div className="px-5 py-4 border-b border-gray-800">
            <h4 className="text-sm font-semibold text-gray-200">{title}</h4>
          </div>
        )}

        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
              <th className="py-3 px-4">{t("code")}</th>
              <th className="py-3 px-4">{t("name")}</th>
              <th className="py-3 px-4">{t("year")}</th>
              <th className="py-3 px-4">{t("formula")}</th>
              <th className="py-3 px-4 text-right">{t("value")}</th>
              <th className="py-3 px-4 text-center">{t("status")}</th>
              <th className="py-3 px-4 text-center">{t("components")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {ratios.map((r, idx) => (
              <tr
                key={`${r.ratio_code}-${r.institution_id}-${r.period_year}-${idx}`}
                className="hover:bg-gray-800/30 transition-colors group cursor-pointer"
                onClick={() => setSelectedRatio(r)}
              >
                <td className="py-3.5 px-4 font-mono font-bold text-emerald-400">{r.ratio_code}</td>
                <td className="py-3.5 px-4 font-medium text-gray-200">
                  <div>{r.ratio_name}</div>
                  {r.institution_name && <span className="text-[11px] text-gray-400 block">{r.institution_name}</span>}
                  {r.reason && <span className="text-[11px] text-amber-400/90 block mt-0.5">{r.reason}</span>}
                </td>
                <td className="py-3.5 px-4 text-gray-300">{r.period_year}</td>
                <td className="py-3.5 px-4 font-mono text-[11px] text-gray-400">{r.formula_used}</td>
                <td className="py-3.5 px-4 text-right font-black text-sm">
                  <span className={r.value_percent === null ? "text-gray-500" : "text-emerald-400"}>
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
                    className="p-1 px-2 rounded-lg bg-gray-800 group-hover:bg-emerald-600 text-gray-300 group-hover:text-white transition-colors text-xs font-semibold"
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
