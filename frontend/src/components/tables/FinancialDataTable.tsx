"use client";

import React, { useState } from "react";
import type { FinancialDataPoint } from "@/types";
import { formatCurrency } from "@/lib/formatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";

interface FinancialDataTableProps {
  dataPoints: FinancialDataPoint[];
  title?: string;
  className?: string;
}

export function FinancialDataTable({ dataPoints, title, className = "" }: FinancialDataTableProps) {
  const [selectedPoint, setSelectedPoint] = useState<FinancialDataPoint | null>(null);

  if (!dataPoints || dataPoints.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        Aucune donnée financière enregistrée pour cette sélection.
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
              <th className="py-3 px-4">Métrique</th>
              <th className="py-3 px-4">Exercice</th>
              <th className="py-3 px-4 text-right">Valeur Normalisée</th>
              <th className="py-3 px-4">Source & Document</th>
              <th className="py-3 px-4 text-center">Statut</th>
              <th className="py-3 px-4 text-center">Audit</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {dataPoints.map((pt) => (
              <tr
                key={pt.id}
                className="hover:bg-gray-800/30 transition-colors group cursor-pointer"
                onClick={() => setSelectedPoint(pt)}
              >
                <td className="py-3.5 px-4 font-semibold text-gray-200">
                  {pt.metric_code}
                </td>
                <td className="py-3.5 px-4 text-gray-300">
                  {pt.period_year} {pt.period_type !== "annual" ? `(${pt.period_type})` : ""}
                </td>
                <td className="py-3.5 px-4 text-right font-bold text-emerald-400">
                  {formatCurrency(pt.value_normalized, pt.currency_normalized || "XOF")}
                </td>
                <td className="py-3.5 px-4 text-gray-400 max-w-[200px] truncate">
                  <span className="text-gray-300 block truncate">
                    {pt.source?.name || pt.source_id}
                  </span>
                  <span className="text-[11px] text-gray-500 block truncate">
                    {pt.document?.title || pt.document_id}
                    {pt.page_number ? ` • p. ${pt.page_number}` : ""}
                  </span>
                </td>
                <td className="py-3.5 px-4 text-center">
                  <StatusBadge status={pt.status} size="sm" />
                </td>
                <td className="py-3.5 px-4 text-center">
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedPoint(pt);
                    }}
                    className="p-1 rounded-lg bg-gray-800 group-hover:bg-emerald-600 text-gray-300 group-hover:text-white transition-colors text-xs"
                    title="Consulter la piste d'audit"
                  >
                    🔍
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selectedPoint && (
        <ProvenancePanel dataPoint={selectedPoint} onClose={() => setSelectedPoint(null)} />
      )}
    </>
  );
}
