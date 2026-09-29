"use client";

import React, { useEffect, useState } from "react";
import type {
  ComparisonResult,
  GrowthResult,
  Institution,
  RatioDefinition,
  RatioResult,
  SectorAggregation,
} from "@/types";
import {
  getAggregations,
  getComparison,
  getGrowth,
  getInstitutions,
  getRatioDefinitions,
  getRatios,
} from "@/lib/api";
import {
  formatCompactCurrency,
  formatPercent,
} from "@/lib/formatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";

const UMOA_COUNTRIES = [
  { code: "BJ", label: "Bénin" },
  { code: "BF", label: "Burkina Faso" },
  { code: "CI", label: "Côte d'Ivoire" },
  { code: "GW", label: "Guinée-Bissau" },
  { code: "ML", label: "Mali" },
  { code: "NE", label: "Niger" },
  { code: "SN", label: "Sénégal" },
  { code: "TG", label: "Togo" },
];

const CORE_METRICS = [
  { code: "total_actifs", label: "Total Actifs" },
  { code: "depots_clients", label: "Dépôts Clients" },
  { code: "creances_clients", label: "Créances Clients" },
  { code: "produit_net_bancaire", label: "Produit Net Bancaire" },
  { code: "resultat_net", label: "Résultat Net" },
  { code: "capitaux_propres", label: "Capitaux Propres" },
];

export default function AnalyticsPage() {
  const [activeTab, setActiveTab] = useState<"ratios" | "growth" | "aggregations" | "compare">("ratios");
  const [ratioDefinitions, setRatioDefinitions] = useState<RatioDefinition[]>([]);
  const [ratios, setRatios] = useState<RatioResult[]>([]);
  const [growthData, setGrowthData] = useState<GrowthResult[]>([]);
  const [aggregations, setAggregations] = useState<SectorAggregation[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(false);

  // Filters
  const [selectedRatio, setSelectedRatio] = useState<string>("ROA");
  const [selectedMetric, setSelectedMetric] = useState<string>("total_actifs");
  const [selectedYear, setSelectedYear] = useState<number>(2024);
  const [selectedCountry, setSelectedCountry] = useState<string>("");

  // Compare Tab State
  const [compareEntityA, setCompareEntityA] = useState<string>("");
  const [compareEntityB, setCompareEntityB] = useState<string>("");
  const [compareMetric, setCompareMetric] = useState<string>("ROA");
  const [comparisonResult, setComparisonResult] = useState<ComparisonResult | null>(null);
  const [compareLoading, setCompareLoading] = useState(false);

  // Initial catalog load
  useEffect(() => {
    getRatioDefinitions().then((defs) => setRatioDefinitions(defs || [])).catch(() => {});
    getInstitutions({ page_size: 100 }).then((res) => {
      setInstitutions(res.items || []);
      if (res.items && res.items.length >= 2) {
        setCompareEntityA(res.items[0].id);
        setCompareEntityB(res.items[1].id);
      }
    }).catch(() => {});
  }, []);

  // Fetch active tab data
  useEffect(() => {
    let isCancelled = false;

    if (activeTab === "ratios") {
      getRatios({
        ratio_code: selectedRatio || undefined,
        year: selectedYear,
        country_code: selectedCountry || undefined,
        page_size: 50,
      }).then((res) => {
        if (!isCancelled) {
          setRatios(res.items || []);
          setLoading(false);
        }
      }).catch(() => {
        if (!isCancelled) {
          setRatios([]);
          setLoading(false);
        }
      });
    } else if (activeTab === "growth") {
      getGrowth({
        metric_code: selectedMetric || undefined,
        year: selectedYear,
        country_code: selectedCountry || undefined,
        page_size: 50,
      }).then((res) => {
        if (!isCancelled) {
          setGrowthData(res.items || []);
          setLoading(false);
        }
      }).catch(() => {
        if (!isCancelled) {
          setGrowthData([]);
          setLoading(false);
        }
      });
    } else if (activeTab === "aggregations") {
      getAggregations({
        year: selectedYear,
        metric_code: selectedMetric || "total_actifs",
        scope: "country",
      }).then((res) => {
        if (!isCancelled) {
          setAggregations(res || []);
          setLoading(false);
        }
      }).catch(() => {
        if (!isCancelled) {
          setAggregations([]);
          setLoading(false);
        }
      });
    }

    return () => {
      isCancelled = true;
    };
  }, [activeTab, selectedRatio, selectedMetric, selectedYear, selectedCountry]);

  // Handle Compare Execution
  const handleExecuteComparison = () => {
    if (!compareEntityA || !compareEntityB) return;
    setCompareLoading(true);

    getComparison({
      comparison_type: "institution_vs_institution",
      entity_a: compareEntityA,
      entity_b: compareEntityB,
      metric_or_ratio: compareMetric,
      year: selectedYear,
    }).then((res) => {
      setComparisonResult(res);
      setCompareLoading(false);
    }).catch(() => {
      setComparisonResult(null);
      setCompareLoading(false);
    });
  };

  const currentRatioDef = ratioDefinitions.find((d) => d.ratio_code === selectedRatio);

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
          Analyses Financières & Ratios Prudentiels
        </h1>
        <p className="text-xs text-gray-400 mt-1">
          Calculs certifiés à la demande, variations annuelles sans interpolation et comparateur factuel.
        </p>
      </div>

      {/* Tabs Bar */}
      <div className="flex border-b border-gray-800 gap-4 text-xs font-semibold">
        <button
          onClick={() => setActiveTab("ratios")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "ratios"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Ratios Bancaires
        </button>

        <button
          onClick={() => setActiveTab("growth")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "growth"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Croissance Annuelle (YoY)
        </button>

        <button
          onClick={() => setActiveTab("aggregations")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "aggregations"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Agrégats Sectoriels
        </button>

        <button
          onClick={() => setActiveTab("compare")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "compare"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Comparateur d&apos;Établissements
        </button>
      </div>

      {/* Ratios Tab Content */}
      {activeTab === "ratios" && (
        <div className="space-y-6">
          {/* Controls */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Ratio Bancaire</label>
              <select
                value={selectedRatio}
                onChange={(e) => setSelectedRatio(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                {ratioDefinitions.map((d) => (
                  <option key={d.ratio_code} value={d.ratio_code}>
                    {d.name_fr} ({d.ratio_code})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Exercice Fiscal</label>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value={2024}>2024</option>
                <option value={2023}>2023</option>
                <option value={2022}>2022</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Filtrer par Pays</label>
              <select
                value={selectedCountry}
                onChange={(e) => setSelectedCountry(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value="">Tous les pays UMOA</option>
                {UMOA_COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label} ({c.code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Ratio Definition Card */}
          {currentRatioDef && (
            <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/60 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs">
              <div className="space-y-1">
                <span className="font-bold text-gray-200 text-sm">{currentRatioDef.name_fr}</span>
                <p className="text-gray-400">{currentRatioDef.description_fr}</p>
                <div className="pt-1 flex flex-wrap gap-2 text-[11px]">
                  <span className="text-gray-500">Règles d&apos;éligibilité :</span>
                  {currentRatioDef.eligibility_rules.map((r, i) => (
                    <span key={i} className="text-emerald-400 font-medium">
                      • {r}
                    </span>
                  ))}
                </div>
              </div>

              <div className="shrink-0 p-3 rounded-xl bg-gray-950 border border-gray-800 text-center font-mono">
                <span className="text-[10px] text-gray-500 block uppercase">Formule</span>
                <span className="text-xs text-emerald-300 font-bold">{currentRatioDef.formula}</span>
              </div>
            </div>
          )}

          {loading ? (
            <TableSkeleton rows={8} cols={5} />
          ) : (
            <RatioDataTable ratios={ratios} title={`Calculs certifiés — ${selectedRatio} (${selectedYear})`} />
          )}
        </div>
      )}

      {/* Growth Tab Content */}
      {activeTab === "growth" && (
        <div className="space-y-6">
          {/* Controls */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Métrique Financière</label>
              <select
                value={selectedMetric}
                onChange={(e) => setSelectedMetric(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                {CORE_METRICS.map((m) => (
                  <option key={m.code} value={m.code}>
                    {m.label} ({m.code})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Exercice Fiscal (Année t)</label>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value={2024}>2024 (vs 2023)</option>
                <option value={2023}>2023 (vs 2022)</option>
              </select>
            </div>

            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Filtrer par Pays</label>
              <select
                value={selectedCountry}
                onChange={(e) => setSelectedCountry(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value="">Tous les pays UMOA</option>
                {UMOA_COUNTRIES.map((c) => (
                  <option key={c.code} value={c.code}>
                    {c.label} ({c.code})
                  </option>
                ))}
              </select>
            </div>
          </div>

          {loading ? (
            <TableSkeleton rows={8} cols={6} />
          ) : growthData.length === 0 ? (
            <EmptyState
              title="Aucune variation calculable"
              description="Les exercices consécutifs nécessaires (t et t-1) ne sont pas disponibles pour calculer la croissance sans extrapolation."
            />
          ) : (
            <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
              <table className="w-full text-left text-xs border-collapse">
                <thead>
                  <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                    <th className="py-3 px-4">Établissement</th>
                    <th className="py-3 px-4">Pays</th>
                    <th className="py-3 px-4 text-right">Valeur {selectedYear}</th>
                    <th className="py-3 px-4 text-right">Valeur {selectedYear - 1}</th>
                    <th className="py-3 px-4 text-right">Variation Absolue</th>
                    <th className="py-3 px-4 text-right">Croissance YoY</th>
                    <th className="py-3 px-4 text-center">Statut</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-800/60">
                  {growthData.map((g, idx) => {
                    const isPositive = (g.growth_rate ?? 0) >= 0;
                    return (
                      <tr key={idx} className="hover:bg-gray-800/30 transition-colors">
                        <td className="py-3.5 px-4 font-bold text-gray-200">
                          {g.institution_name || g.institution_id}
                        </td>
                        <td className="py-3.5 px-4 font-mono font-bold text-emerald-400">
                          {g.country_code || "—"}
                        </td>
                        <td className="py-3.5 px-4 text-right font-medium text-gray-300">
                          {formatCompactCurrency(g.current_value, g.currency || "XOF")}
                        </td>
                        <td className="py-3.5 px-4 text-right font-medium text-gray-400">
                          {formatCompactCurrency(g.previous_value, g.currency || "XOF")}
                        </td>
                        <td className="py-3.5 px-4 text-right font-mono text-gray-300">
                          {g.absolute_change !== null && g.absolute_change !== undefined
                            ? formatCompactCurrency(g.absolute_change, g.currency || "XOF")
                            : "—"}
                        </td>
                        <td className="py-3.5 px-4 text-right font-black text-sm">
                          {g.growth_percent !== null && g.growth_percent !== undefined ? (
                            <span className={isPositive ? "text-emerald-400" : "text-rose-400"}>
                              {isPositive ? "+" : ""}
                              {formatPercent(g.growth_percent, 2)}
                            </span>
                          ) : (
                            <span className="text-gray-500">N/A</span>
                          )}
                        </td>
                        <td className="py-3.5 px-4 text-center">
                          <StatusBadge status={g.status} size="sm" />
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Aggregations Tab Content */}
      {activeTab === "aggregations" && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Métrique Consolidée</label>
              <select
                value={selectedMetric}
                onChange={(e) => setSelectedMetric(e.target.value)}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                {CORE_METRICS.map((m) => (
                  <option key={m.code} value={m.code}>
                    {m.label} ({m.code})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[11px] text-gray-400 block mb-1 font-medium">Exercice Fiscal</label>
              <select
                value={selectedYear}
                onChange={(e) => setSelectedYear(Number(e.target.value))}
                className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
              >
                <option value={2024}>2024</option>
                <option value={2023}>2023</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {aggregations.map((agg, idx) => (
              <div
                key={idx}
                className="p-5 rounded-2xl border border-gray-800 bg-gray-900/40 flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="font-bold text-gray-200 text-sm">
                      {agg.country_name || agg.country_code}
                    </span>
                    <span className="px-2 py-0.5 rounded bg-gray-800 text-xs font-mono font-bold text-emerald-400">
                      {agg.country_code}
                    </span>
                  </div>

                  <span className="text-xl font-black text-white block mt-3">
                    {formatCompactCurrency(agg.total_value, agg.currency)}
                  </span>
                  <span className="text-[11px] text-gray-400 block mt-1">
                    {agg.institution_count}/{agg.total_institutions} établissements
                  </span>
                </div>

                <div className="mt-4 pt-3 border-t border-gray-800/80">
                  <CoverageIndicator
                    coverageRatio={agg.coverage_ratio}
                    showWarningIfPartial={false}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Compare Tab Content */}
      {activeTab === "compare" && (
        <div className="space-y-6">
          <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/40">
            <h3 className="text-sm font-bold text-white mb-3">Face-à-Face Établissements</h3>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              <div>
                <label className="text-[11px] text-gray-400 block mb-1 font-medium">Établissement A</label>
                <select
                  value={compareEntityA}
                  onChange={(e) => setCompareEntityA(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
                >
                  {institutions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name_official || i.name} ({i.country?.iso_code_2 || "UMOA"})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-[11px] text-gray-400 block mb-1 font-medium">Établissement B</label>
                <select
                  value={compareEntityB}
                  onChange={(e) => setCompareEntityB(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
                >
                  {institutions.map((i) => (
                    <option key={i.id} value={i.id}>
                      {i.name_official || i.name} ({i.country?.iso_code_2 || "UMOA"})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="text-[11px] text-gray-400 block mb-1 font-medium">Indicateur</label>
                <select
                  value={compareMetric}
                  onChange={(e) => setCompareMetric(e.target.value)}
                  className="w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
                >
                  <optgroup label="Ratios">
                    <option value="ROA">ROA (Rentabilité des actifs)</option>
                    <option value="ROE">ROE (Rentabilité capitaux propres)</option>
                    <option value="DEPOTS_ACTIFS">Dépôts / Actifs</option>
                    <option value="CREDITS_DEPOTS">Crédits / Dépôts</option>
                  </optgroup>
                  <optgroup label="Postes Bilan (XOF)">
                    <option value="total_actifs">Total Actifs</option>
                    <option value="depots_clients">Dépôts Clients</option>
                    <option value="resultat_net">Résultat Net</option>
                  </optgroup>
                </select>
              </div>
            </div>

            <div className="mt-4 flex justify-end">
              <button
                onClick={handleExecuteComparison}
                disabled={compareLoading}
                className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors disabled:opacity-50"
              >
                {compareLoading ? "Calcul en cours..." : "Lancer la comparaison"}
              </button>
            </div>
          </div>

          {/* Comparison Result Display */}
          {comparisonResult && (
            <div className="p-6 rounded-2xl border border-emerald-600/40 bg-gray-900/60 space-y-4">
              <span className="text-xs font-semibold text-emerald-400 uppercase tracking-wider block">
                Résultat Factuel Certifié
              </span>
              <p className="text-sm font-medium text-gray-200 leading-relaxed">
                {comparisonResult.description}
              </p>

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs">
                <div className="p-3 rounded-xl bg-gray-950 border border-gray-800">
                  <span className="text-gray-400 block mb-0.5">{comparisonResult.entity_a}</span>
                  <span className="font-bold text-base text-white">
                    {comparisonResult.value_a != null ? comparisonResult.value_a : "—"}{" "}
                    {comparisonResult.unit || ""}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-gray-950 border border-gray-800">
                  <span className="text-gray-400 block mb-0.5">{comparisonResult.entity_b}</span>
                  <span className="font-bold text-base text-white">
                    {comparisonResult.value_b != null ? comparisonResult.value_b : "—"}{" "}
                    {comparisonResult.unit || ""}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-gray-950 border border-gray-800">
                  <span className="text-gray-400 block mb-0.5">Écart Absolu (A - B)</span>
                  <span className="font-bold text-base text-emerald-400">
                    {comparisonResult.difference != null ? `${comparisonResult.difference > 0 ? "+" : ""}${comparisonResult.difference}` : "—"}{" "}
                    {comparisonResult.unit || ""}
                  </span>
                </div>

                <div className="p-3 rounded-xl bg-gray-950 border border-gray-800">
                  <span className="text-gray-400 block mb-0.5">Ratio A / B</span>
                  <span className="font-bold text-base text-teal-300">
                    {comparisonResult.ratio_a_to_b != null ? comparisonResult.ratio_a_to_b : "—"}
                  </span>
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
