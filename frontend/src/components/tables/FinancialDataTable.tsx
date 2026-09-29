"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { QualifiedObservation } from "@/lib/series";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";

interface FinancialDataTableProps {
  /** Qualified observations (see qualifyObservations) — same dataset as KPIs and charts. */
  observations: QualifiedObservation[];
  title?: string;
  className?: string;
}

export function FinancialDataTable({ observations, title, className = "" }: FinancialDataTableProps) {
  const t = useTranslations("tables.financial");
  const fmt = useFormatters();
  const labels = useLabels();
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (observations.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        {t("empty")}
      </div>
    );
  }

  const rows = [...observations].sort(
    (a, b) => b.period_year - a.period_year || a.metric_code.localeCompare(b.metric_code),
  );

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
              <th className="py-3 px-4">{t("metric")}</th>
              <th className="py-3 px-4">{t("year")}</th>
              <th className="py-3 px-4 text-right">{t("value")}</th>
              <th className="py-3 px-4 text-center">{t("status")}</th>
              <th className="py-3 px-4 text-center">{t("audit")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {rows.map((o) => (
              <tr key={`${o.metric_code}-${o.period_year}`} className="hover:bg-gray-800/30 transition-colors group">
                <td className="py-3.5 px-4 font-semibold text-gray-200">{labels.metric(o.metric_code)}</td>
                <td className="py-3.5 px-4 text-gray-300">{o.period_year}</td>
                <td className="py-3.5 px-4 text-right font-bold text-emerald-400">
                  {o.conflict ? MISSING : fmt.currency(o.value, o.currency)}
                  {o.conflict && <span className="block text-[11px] font-normal text-amber-400">{t("conflict")}</span>}
                </td>
                <td className="py-3.5 px-4 text-center">
                  <StatusBadge status={o.conflict ? "conflict" : o.status} size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center">
                  {o.data_id ? (
                    <button
                      onClick={() => setSelectedId(o.data_id)}
                      className="p-1 px-2 rounded-lg bg-gray-800 group-hover:bg-emerald-600 text-gray-300 group-hover:text-white transition-colors text-xs"
                      title={t("audit_title")}
                    >
                      🔍
                    </button>
                  ) : (
                    MISSING
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedId && <ProvenancePanel dataId={selectedId} onClose={() => setSelectedId(null)} />}
    </>
  );
}
