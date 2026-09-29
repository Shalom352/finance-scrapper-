"use client";

import React, { useState } from "react";
import type { RatioResult } from "@/types";
import { formatPercent } from "@/lib/formatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";

interface RatioDataTableProps {
  ratios: RatioResult[];
  title?: string;
  className?: string;
}

export function RatioDataTable({ ratios, title, className = "" }: RatioDataTableProps) {
  const [selectedRatio, setSelectedRatio] = useState<RatioResult | null>(null);

  if (!ratios || ratios.length === 0) {
    return (
      <div className={`p-8 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        Aucun ratio calculé disponible pour cet exercice.
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
              <th className="py-3 px-4">Code</th>
              <th className="py-3 px-4">Ratio Bancaire</th>
              <th className="py-3 px-4">Formule</th>
              <th className="py-3 px-4 text-right">Valeur</th>
              <th className="py-3 px-4 text-center">Statut</th>
              <th className="py-3 px-4 text-center">Composants</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800/60">
            {ratios.map((r, idx) => {
              const isAvailable = r.value_percent !== null && r.value_percent !== undefined;

              return (
                <tr
                  key={idx}
                  className="hover:bg-gray-800/30 transition-colors group cursor-pointer"
                  onClick={() => setSelectedRatio(r)}
                >
                  <td className="py-3.5 px-4 font-mono font-bold text-emerald-400">
                    {r.ratio_code}
                  </td>
                  <td className="py-3.5 px-4 font-medium text-gray-200">
                    <div>{r.ratio_name}</div>
                    {r.reason && (
                      <span className="text-[11px] text-amber-400/90 block mt-0.5">
                        {r.reason}
                      </span>
                    )}
                  </td>
                  <td className="py-3.5 px-4 font-mono text-[11px] text-gray-400">
                    {r.formula_used}
                  </td>
                  <td className="py-3.5 px-4 text-right font-black text-sm">
                    {isAvailable ? (
                      <span className="text-emerald-400">{formatPercent(r.value_percent, 2)}</span>
                    ) : (
                      <span className="text-gray-500">N/A</span>
                    )}
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
                      {r.components.length} composant{r.components.length > 1 ? "s" : ""}
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {selectedRatio && (
        <ProvenancePanel ratioPoint={selectedRatio} onClose={() => setSelectedRatio(null)} />
      )}
    </>
  );
}
