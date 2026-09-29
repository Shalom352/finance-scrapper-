"use client";

import React from "react";
import type { FinancialDataPoint, RatioResult } from "@/types";
import { StatusBadge } from "@/components/common/StatusBadge";
import { formatCurrency, formatPercent } from "@/lib/formatters";

interface ProvenancePanelProps {
  dataPoint?: FinancialDataPoint | null;
  ratioPoint?: RatioResult | null;
  onClose: () => void;
}

export function ProvenancePanel({ dataPoint, ratioPoint, onClose }: ProvenancePanelProps) {
  if (!dataPoint && !ratioPoint) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
      role="dialog"
      aria-modal="true"
      aria-labelledby="provenance-title"
    >
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-3xl border border-gray-800 bg-gray-950 p-6 md:p-8 shadow-2xl">
        {/* Header */}
        <div className="flex items-start justify-between pb-4 border-b border-gray-800">
          <div>
            <div className="inline-flex items-center gap-2 mb-1">
              <span className="text-emerald-400 text-sm font-semibold tracking-wide uppercase">
                Piste d&apos;audit & Traçabilité
              </span>
              {(dataPoint || ratioPoint) && (
                <StatusBadge status={dataPoint?.status || ratioPoint?.status || "extracted"} />
              )}
            </div>
            <h3 id="provenance-title" className="text-xl font-bold text-white">
              {ratioPoint ? ratioPoint.ratio_name : dataPoint?.metric_code}
            </h3>
            <p className="text-xs text-gray-400 mt-0.5">
              Exercice {dataPoint?.period_year || ratioPoint?.period_year} —{" "}
              {dataPoint?.institution?.name || ratioPoint?.institution_name || "Institution"}
            </p>
          </div>
          <button
            onClick={onClose}
            className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800 transition-colors"
            aria-label="Fermer le panneau de provenance"
          >
            ✕
          </button>
        </div>

        {/* Content for Financial Data Point */}
        {dataPoint && (
          <div className="space-y-6 pt-6">
            {/* Primary Value Block */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 p-4 rounded-2xl bg-gray-900/60 border border-gray-800">
              <div>
                <span className="text-[11px] text-gray-400 block mb-0.5">Valeur normalisée</span>
                <span className="text-lg font-bold text-emerald-400">
                  {formatCurrency(dataPoint.value_normalized, dataPoint.currency_normalized || "XOF")}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block mb-0.5">Valeur brute publiée</span>
                <span className="text-sm font-mono text-gray-200">
                  {dataPoint.value_original} {dataPoint.unit_original || ""}
                </span>
              </div>
              <div>
                <span className="text-[11px] text-gray-400 block mb-0.5">Périmètre comptable</span>
                <span className="text-sm capitalize text-gray-300">
                  {dataPoint.scope === "individual" ? "Comptes sociaux (Individuel)" : "Comptes consolidés"}
                </span>
              </div>
            </div>

            {/* Documentary Metadata */}
            <div className="space-y-3">
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
                Document source certifié
              </h4>
              <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Source officielle :</span>
                  <span className="font-medium text-gray-200">{dataPoint.source?.name || dataPoint.source_id}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Document :</span>
                  <span className="font-medium text-gray-200">{dataPoint.document?.title || dataPoint.document_id}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Numéro de page :</span>
                  <span className="font-medium text-emerald-400">
                    {dataPoint.page_number ? `Page ${dataPoint.page_number}` : "Non spécifiée"}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-gray-800/60">
                  <span className="text-gray-400">Méthode d&apos;extraction :</span>
                  <span className="font-mono text-gray-300">{dataPoint.extraction_method}</span>
                </div>
                {dataPoint.verified_by && (
                  <div className="flex justify-between py-1">
                    <span className="text-gray-400">Validateur humain :</span>
                    <span className="font-medium text-emerald-400">{dataPoint.verified_by}</span>
                  </div>
                )}
              </div>
            </div>

            {dataPoint.notes && (
              <div className="p-3 rounded-xl bg-gray-900 border border-gray-800 text-xs text-gray-400">
                <span className="font-medium text-gray-300 block mb-1">Notes d&apos;extraction :</span>
                {dataPoint.notes}
              </div>
            )}
          </div>
        )}

        {/* Content for Ratio Result */}
        {ratioPoint && (
          <div className="space-y-6 pt-6">
            {/* Primary Ratio Value */}
            <div className="p-5 rounded-2xl bg-gray-900/60 border border-gray-800 flex items-center justify-between">
              <div>
                <span className="text-xs text-gray-400 block mb-1">Valeur calculée</span>
                <span className="text-2xl font-black text-emerald-400">
                  {ratioPoint.value_percent !== null && ratioPoint.value_percent !== undefined
                    ? formatPercent(ratioPoint.value_percent, 2)
                    : "N/A"}
                </span>
                {ratioPoint.reason && (
                  <span className="text-xs text-amber-400 block mt-1">
                    {ratioPoint.reason}
                  </span>
                )}
              </div>
              <div className="text-right">
                <span className="text-xs text-gray-400 block mb-1">Formule appliquée</span>
                <code className="text-xs px-2.5 py-1 rounded bg-gray-950 border border-gray-800 text-emerald-300 font-mono">
                  {ratioPoint.formula_used}
                </code>
              </div>
            </div>

            {/* Constituent Components Tree */}
            <div>
              <h4 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">
                Composants du calcul ({ratioPoint.components.length})
              </h4>
              <div className="space-y-3">
                {ratioPoint.components.map((comp, idx) => (
                  <div
                    key={idx}
                    className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-gray-200">{comp.metric_code}</span>
                        <span className="text-gray-400">({comp.period_year})</span>
                        {comp.role && (
                          <span className="px-1.5 py-0.5 rounded bg-gray-800 text-[10px] text-gray-400 uppercase">
                            {comp.role}
                          </span>
                        )}
                      </div>
                      <StatusBadge status={comp.status} size="sm" />
                    </div>

                    <div className="flex items-center justify-between pt-1">
                      <span className="text-gray-400">
                        {comp.source_name || comp.source_id || "Source"}
                        {comp.page_number && ` • Page ${comp.page_number}`}
                      </span>
                      <span className="font-semibold text-emerald-400 text-sm">
                        {formatCurrency(comp.value_normalized, comp.currency || "XOF")}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Footer */}
        <div className="mt-8 pt-4 border-t border-gray-800 flex justify-end">
          <button
            onClick={onClose}
            className="px-5 py-2 rounded-xl bg-gray-800 hover:bg-gray-700 text-white text-xs font-medium transition-colors"
          >
            Fermer
          </button>
        </div>
      </div>
    </div>
  );
}
