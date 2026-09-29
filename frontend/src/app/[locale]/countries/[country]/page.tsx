"use client";

import React, { useEffect, useState, use } from "react";
import { Link } from "@/i18n/navigation";
import type { Institution, MarketShare, SectorAggregation } from "@/types";
import { getAggregations, getInstitutions, getSectorStructure } from "@/lib/api";
import { formatCompactCurrency, formatPercent } from "@/lib/formatters";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { FinancialBarChart } from "@/components/charts/FinancialBarChart";
import { CardSkeleton, TableSkeleton } from "@/components/common/LoadingSkeleton";

interface PageProps {
  params: Promise<{ country: string; locale: string }>;
}

const COUNTRIES_FLAGS: Record<string, string> = {
  BJ: "🇧🇯",
  BF: "🇧🇫",
  CI: "🇨🇮",
  GW: "🇬🇼",
  ML: "🇲🇱",
  NE: "🇳🇪",
  SN: "🇸🇳",
  TG: "🇹🇬",
};

export default function CountryDetailPage({ params }: PageProps) {
  const { country } = use(params);
  const countryCode = country.toUpperCase();

  const [aggregation, setAggregation] = useState<SectorAggregation | null>(null);
  const [marketShares, setMarketShares] = useState<MarketShare[]>([]);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let isCancelled = false;

    Promise.all([
      getSectorStructure({ country_code: countryCode, year: 2024, metric_code: "depots_clients" }).catch(() => null),
      getAggregations({ country_code: countryCode, year: 2024, metric_code: "total_actifs" }).catch(() => null),
      getInstitutions({ country_code: countryCode, page_size: 50 }).catch(() => null),
    ]).then(([secRes, aggRes, instRes]) => {
      if (!isCancelled) {
        if (secRes) {
          setAggregation(secRes.aggregation);
          setMarketShares(secRes.market_shares || []);
        } else if (aggRes && aggRes.length > 0) {
          setAggregation(aggRes[0]);
        }
        if (instRes) setInstitutions(instRes.items || []);
        setLoading(false);
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [countryCode]);

  if (loading) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={6} cols={4} />
      </div>
    );
  }

  const flag = COUNTRIES_FLAGS[countryCode] || "🌍";
  const countryName = aggregation?.country_name || countryCode;

  const barChartItems = marketShares.slice(0, 8).map((ms) => ({
    label: ms.institution_name || ms.institution_id,
    value: ms.market_share_percent,
    sublabel: `${formatPercent(ms.market_share_percent, 1)}`,
  }));

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Back Link */}
      <div>
        <Link
          href="/countries"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-400 hover:text-emerald-400 transition-colors"
        >
          ← Retour aux pays membres de l&apos;UMOA
        </Link>
      </div>

      {/* Country Header Card */}
      <div className="p-6 md:p-8 rounded-3xl border border-gray-800 bg-gray-900/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <span className="text-5xl">{flag}</span>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="px-2.5 py-0.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 text-emerald-400 text-xs font-bold font-mono">
                  {countryCode}
                </span>
                <span className="text-xs text-gray-400 font-semibold uppercase tracking-wider">
                  Secteur Bancaire National
                </span>
              </div>
              <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight">
                {countryName}
              </h1>
            </div>
          </div>

          <div className="w-full md:w-64">
            <CoverageIndicator
              coverageRatio={aggregation?.coverage_ratio || 0.85}
              representedCount={aggregation?.institution_count}
              totalCount={aggregation?.total_institutions}
              label="Complétude sectorielle"
            />
          </div>
        </div>
      </div>

      {/* Sector KPIs */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-xs text-gray-400 font-medium block mb-1">Total Dépôts Secteur (2024)</span>
          <span className="text-2xl font-black text-emerald-400">
            {formatCompactCurrency(aggregation?.total_value, "XOF")}
          </span>
          <span className="text-[11px] text-gray-500 block mt-1">Consolidation nationale</span>
        </div>

        <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-xs text-gray-400 font-medium block mb-1">Institutions Comptabilisées</span>
          <span className="text-2xl font-black text-white">
            {aggregation?.institution_count || institutions.length}
          </span>
          <span className="text-[11px] text-gray-500 block mt-1">Sur {aggregation?.total_institutions || institutions.length} établissements agréés</span>
        </div>

        <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-xs text-gray-400 font-medium block mb-1">Statut d&apos;agrégation</span>
          <div className="mt-1">
            <span
              className={`inline-flex px-3 py-1 rounded-xl text-xs font-bold border ${
                aggregation?.is_partial
                  ? "bg-amber-950/60 text-amber-300 border-amber-800"
                  : "bg-emerald-950/60 text-emerald-300 border-emerald-800"
              }`}
            >
              {aggregation?.is_partial ? "⚠️ Couverture Partielle" : "✓ Couverture Intégrale"}
            </span>
          </div>
          <span className="text-[11px] text-gray-500 block mt-1">Garantie sans double comptage</span>
        </div>
      </div>

      {/* Market Share Chart & Table */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div>
          <FinancialBarChart
            items={barChartItems}
            title="Parts de Marché des Dépôts (%)"
            isPercent
          />
        </div>

        {/* Market share table */}
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          <div className="px-5 py-4 border-b border-gray-800">
            <h4 className="text-sm font-semibold text-gray-200">
              Décomposition des Parts de Marché
            </h4>
          </div>

          {marketShares.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-500">
              Aucune donnée de part de marché disponible pour cet exercice.
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Établissement</th>
                  <th className="py-3 px-4 text-right">Volume Dépôts</th>
                  <th className="py-3 px-4 text-right">Part (%)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {marketShares.map((ms, idx) => (
                  <tr key={idx} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-3 px-4 font-semibold text-gray-200">
                      <Link
                        href={`/institutions/${ms.institution_id}`}
                        className="hover:text-emerald-400 transition-colors"
                      >
                        {ms.institution_name || ms.institution_id}
                      </Link>
                    </td>
                    <td className="py-3 px-4 text-right font-medium text-gray-300">
                      {formatCompactCurrency(ms.institution_value, "XOF")}
                    </td>
                    <td className="py-3 px-4 text-right font-bold text-emerald-400">
                      {formatPercent(ms.market_share_percent, 2)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* National Banks Directory */}
      <div className="space-y-4">
        <h3 className="text-lg font-bold text-white tracking-tight">
          Établissements Agréés en {countryName} ({institutions.length})
        </h3>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {institutions.map((inst) => (
            <Link
              key={inst.id}
              href={`/institutions/${inst.id}`}
              className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 hover:border-emerald-600/50 hover:bg-gray-900 transition-all flex flex-col justify-between"
            >
              <div>
                <span className="text-xs font-bold text-gray-200 block mb-1">
                  {inst.name_official || inst.name}
                </span>
                {inst.banking_group && (
                  <span className="text-[11px] text-gray-400 block">
                    Groupe : {inst.banking_group.name}
                  </span>
                )}
              </div>
              <div className="flex items-center justify-between mt-4 pt-2 border-t border-gray-800/60 text-[11px]">
                <span className="text-gray-500 capitalize">{inst.institution_type || "Banque"}</span>
                <span className="text-emerald-400 font-semibold">Consulter →</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
