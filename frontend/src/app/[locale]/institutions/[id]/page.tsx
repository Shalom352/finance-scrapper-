"use client";

import React, { useEffect, useState, use } from "react";
import { Link } from "@/i18n/navigation";
import type {
  Document,
  FinancialDataPoint,
  Institution,
  RatioResult,
} from "@/types";
import {
  getDocuments,
  getFinancialData,
  getInstitutionById,
  getRatios,
} from "@/lib/api";
import { formatCompactCurrency } from "@/lib/formatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { FinancialDataTable } from "@/components/tables/FinancialDataTable";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { FinancialLineChart } from "@/components/charts/FinancialLineChart";
import { CardSkeleton, TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState } from "@/components/common/EmptyState";

interface PageProps {
  params: Promise<{ id: string; locale: string }>;
}

export default function InstitutionDetailPage({ params }: PageProps) {
  const { id } = use(params);

  const [institution, setInstitution] = useState<Institution | null>(null);
  const [financialData, setFinancialData] = useState<FinancialDataPoint[]>([]);
  const [ratios, setRatios] = useState<RatioResult[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"financials" | "ratios" | "charts" | "documents">("financials");

  useEffect(() => {
    let isCancelled = false;

    Promise.all([
      getInstitutionById(id).catch(() => null),
      getFinancialData({ institution_id: id, page_size: 100 }).catch(() => null),
      getRatios({ institution_id: id, page_size: 100 }).catch(() => null),
      getDocuments({ institution_id: id, page_size: 50 }).catch(() => null),
    ]).then(([instRes, finRes, ratioRes, docRes]) => {
      if (!isCancelled) {
        if (instRes) setInstitution(instRes);
        if (finRes) setFinancialData(finRes.items || []);
        if (ratioRes) setRatios(ratioRes.items || []);
        if (docRes) setDocuments(docRes.items || []);
        setLoading(false);
      }
    });

    return () => {
      isCancelled = true;
    };
  }, [id]);

  if (loading) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={6} cols={4} />
      </div>
    );
  }

  if (!institution) {
    return (
      <EmptyState
        title="Institution introuvable"
        description="Cet établissement n'existe pas ou a été désactivé."
        actionText="Retour au répertoire"
        onAction={() => window.history.back()}
      />
    );
  }

  // Extract latest KPIs for summary cards
  const sortedByYear = [...financialData].sort((a, b) => b.period_year - a.period_year);
  const latestYear = sortedByYear[0]?.period_year || 2024;
  const latestData = sortedByYear.filter((d) => d.period_year === latestYear);

  const getMetricVal = (code: string) =>
    latestData.find((d) => d.metric_code === code)?.value_normalized;

  const assetsVal = getMetricVal("total_actifs");
  const depositsVal = getMetricVal("depots_clients");
  const loansVal = getMetricVal("creances_clients");
  const netIncomeVal = getMetricVal("resultat_net");
  const equityVal = getMetricVal("capitaux_propres");
  const nbiVal = getMetricVal("produit_net_bancaire");

  // Prepare chart series without zero interpolation
  const assetsChartData = financialData
    .filter((d) => d.metric_code === "total_actifs")
    .map((d) => ({
      year: d.period_year,
      value: d.value_normalized,
      status: d.status,
    }));

  const depositsChartData = financialData
    .filter((d) => d.metric_code === "depots_clients")
    .map((d) => ({
      year: d.period_year,
      value: d.value_normalized,
      status: d.status,
    }));

  const roaChartData = ratios
    .filter((r) => r.ratio_code === "ROA")
    .map((r) => ({
      year: r.period_year,
      value: r.value_percent,
      status: r.status,
    }));

  const roeChartData = ratios
    .filter((r) => r.ratio_code === "ROE")
    .map((r) => ({
      year: r.period_year,
      value: r.value_percent,
      status: r.status,
    }));

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Back Link */}
      <div>
        <Link
          href="/institutions"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-gray-400 hover:text-emerald-400 transition-colors"
        >
          ← Retour au répertoire des institutions
        </Link>
      </div>

      {/* Institution Header Card */}
      <div className="p-6 md:p-8 rounded-3xl border border-gray-800 bg-gray-900/40">
        <div className="flex flex-col md:flex-row md:items-start justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2 mb-2">
              <span className="px-2.5 py-0.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 text-emerald-400 text-xs font-bold uppercase">
                {institution.country?.iso_code_2 || "UMOA"}
              </span>
              <span className="text-xs text-gray-400 font-medium">
                {institution.country?.name_fr}
              </span>
              <StatusBadge status={institution.status === "active" ? "verified" : "needs_review"} size="sm" />
            </div>

            <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight">
              {institution.name_official || institution.name}
            </h1>
            {institution.name_commercial && (
              <p className="text-sm text-emerald-400 font-medium mt-1">
                Nom commercial : {institution.name_commercial}
              </p>
            )}

            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 text-xs text-gray-400">
              {institution.banking_group && (
                <div>
                  <span className="text-gray-500">Groupe :</span>{" "}
                  <span className="text-gray-200 font-semibold">{institution.banking_group.name}</span>
                </div>
              )}
              {institution.regulatory_id && (
                <div>
                  <span className="text-gray-500">Agrément BCEAO :</span>{" "}
                  <span className="text-gray-200 font-mono font-medium">{institution.regulatory_id}</span>
                </div>
              )}
              {institution.website_url && (
                <div>
                  <a
                    href={institution.website_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-emerald-400 hover:underline inline-flex items-center gap-1 font-medium"
                  >
                    Site officiel ↗
                  </a>
                </div>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Latest Year KPI Bar */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">Total Actifs ({latestYear})</span>
          <span className="text-lg font-black text-white">{formatCompactCurrency(assetsVal)}</span>
        </div>
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">Dépôts Clients</span>
          <span className="text-lg font-black text-white">{formatCompactCurrency(depositsVal)}</span>
        </div>
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">Créances Clients</span>
          <span className="text-lg font-black text-white">{formatCompactCurrency(loansVal)}</span>
        </div>
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">PNB</span>
          <span className="text-lg font-black text-teal-400">{formatCompactCurrency(nbiVal)}</span>
        </div>
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">Résultat Net</span>
          <span className="text-lg font-black text-emerald-400">{formatCompactCurrency(netIncomeVal)}</span>
        </div>
        <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30">
          <span className="text-[11px] text-gray-400 font-medium block mb-1">Capitaux Propres</span>
          <span className="text-lg font-black text-white">{formatCompactCurrency(equityVal)}</span>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-gray-800 gap-4 text-xs font-semibold">
        <button
          onClick={() => setActiveTab("financials")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "financials"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          États Financiers ({financialData.length})
        </button>

        <button
          onClick={() => setActiveTab("ratios")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "ratios"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Ratios & Performance ({ratios.length})
        </button>

        <button
          onClick={() => setActiveTab("charts")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "charts"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Graphiques Temporels
        </button>

        <button
          onClick={() => setActiveTab("documents")}
          className={`pb-3 px-1 border-b-2 transition-colors ${
            activeTab === "documents"
              ? "border-emerald-500 text-emerald-400 font-bold"
              : "border-transparent text-gray-400 hover:text-gray-200"
          }`}
        >
          Documents Rattachés ({documents.length})
        </button>
      </div>

      {/* Tab Contents */}
      {activeTab === "financials" && (
        <FinancialDataTable
          dataPoints={financialData}
          title="Historique des Postes Comptables Normalisés"
        />
      )}

      {activeTab === "ratios" && (
        <RatioDataTable
          ratios={ratios}
          title="Indicateurs de Rentabilité & Ratios Prudentiels"
        />
      )}

      {activeTab === "charts" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <FinancialLineChart
            data={assetsChartData}
            title="Évolution du Total Actifs"
            metricLabel="XOF"
          />
          <FinancialLineChart
            data={depositsChartData}
            title="Évolution des Dépôts Clients"
            metricLabel="XOF"
          />
          <FinancialLineChart
            data={roaChartData}
            title="Évolution du ROA (Rentabilité des Actifs)"
            isPercent
          />
          <FinancialLineChart
            data={roeChartData}
            title="Évolution du ROE (Rentabilité des Capitaux Propres)"
            isPercent
          />
        </div>
      )}

      {activeTab === "documents" && (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          {documents.length === 0 ? (
            <div className="p-8 text-center text-xs text-gray-500">
              Aucun document officiel rattaché à cet établissement.
            </div>
          ) : (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">Titre du Document</th>
                  <th className="py-3 px-4">Type</th>
                  <th className="py-3 px-4">Année</th>
                  <th className="py-3 px-4 text-center">Extraction</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {documents.map((doc) => (
                  <tr key={doc.id} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-3.5 px-4 font-semibold text-gray-200">
                      {doc.title}
                    </td>
                    <td className="py-3.5 px-4 text-gray-400 capitalize">
                      {doc.document_type.replace(/_/g, " ")}
                    </td>
                    <td className="py-3.5 px-4 text-gray-300">
                      {doc.period_year || "—"}
                    </td>
                    <td className="py-3.5 px-4 text-center">
                      <StatusBadge status={doc.extraction_status === "extracted" ? "verified" : "needs_review"} size="sm" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}
    </div>
  );
}
