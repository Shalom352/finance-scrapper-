"use client";

import React, { Suspense, useEffect, useMemo, useState, use } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Document, FinancialDataPoint, Institution, RatioResult } from "@/types";
import { getDocuments, getFinancialDataAll, getInstitutionById, getRatios } from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { useQueryParams } from "@/lib/useQueryParams";
import {
  buildYearSeries,
  distinctField,
  findObservation,
  latestYear,
  qualifyObservations,
} from "@/lib/series";
import { StateBadge } from "@/components/common/StatusBadge";
import { FinancialDataTable } from "@/components/tables/FinancialDataTable";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { FinancialLineChart } from "@/components/charts/FinancialLineChart";
import { DocumentsTable } from "@/components/tables/DocumentsTable";
import { CardSkeleton, TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";

interface PageProps {
  params: Promise<{ id: string; locale: string }>;
}

const KPI_METRICS = [
  "total_actifs",
  "depots_clients",
  "creances_clients",
  "produit_net_bancaire",
  "resultat_net",
  "capitaux_propres",
] as const;

const CHART_METRICS = ["total_actifs", "depots_clients"] as const;
const CHART_RATIOS = ["ROA", "ROE"] as const;

type Tab = "financials" | "ratios" | "charts" | "documents";

interface InstitutionData {
  institution: Institution | null;
  rows: FinancialDataPoint[] | null;
  documents: Document[] | null;
}

/** Preferred default when available; otherwise the first value present in the data. */
function pickDefault(options: string[], preferred: string): string | null {
  if (options.includes(preferred)) return preferred;
  return options[0] ?? null;
}

const TABS: Tab[] = ["financials", "ratios", "charts", "documents"];

export default function InstitutionDetailPage({ params }: PageProps) {
  const { id } = use(params);
  return (
    <Suspense fallback={<CardSkeleton />}>
      <InstitutionDetail id={id} />
    </Suspense>
  );
}

function InstitutionDetail({ id }: { id: string }) {
  const t = useTranslations("institutions.detail");
  const tInst = useTranslations("institution_status");
  const fmt = useFormatters();
  const labels = useLabels();

  const [data, setData] = useState<InstitutionData | null>(null);
  const [attempt, setAttempt] = useState(0);
  // Tab, scope and period live in the URL: kept on reload and on locale switch.
  const { get, set } = useQueryParams();
  const activeTab: Tab = (TABS as string[]).includes(get("tab")) ? (get("tab") as Tab) : "financials";
  const setActiveTab = (tab: Tab) => set({ tab });
  const scope = get("scope") || null;
  const periodType = get("period") || null;
  const setScope = (v: string) => set({ scope: v });
  const setPeriodType = (v: string) => set({ period: v });

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setData(null);
    Promise.all([
      getInstitutionById(id).catch(() => null),
      getFinancialDataAll({ institution_id: id }).catch(() => null),
      getDocuments({ institution_id: id, page_size: 100 })
        .then((r) => r.items)
        .catch(() => null),
    ]).then(([institution, rows, documents]) => {
      if (!cancelled) setData({ institution, rows, documents });
    });
    return () => {
      cancelled = true;
    };
  }, [id, attempt]);

  const rows = useMemo(() => data?.rows ?? [], [data]);
  const scopes = useMemo(() => distinctField(rows, "scope"), [rows]);
  const periodTypes = useMemo(() => distinctField(rows, "period_type"), [rows]);
  const activeScope = scope && scopes.includes(scope) ? scope : pickDefault(scopes, "individual");
  const activePeriod = periodType && periodTypes.includes(periodType) ? periodType : pickDefault(periodTypes, "annual");

  // Ratios are requested in the selected accounting scope (backend data_scope): never mixed.
  const [ratiosState, setRatiosState] = useState<{ scope: string; items: RatioResult[] | null } | null>(null);
  useEffect(() => {
    if (!activeScope) return;
    let cancelled = false;
    getRatios({ institution_id: id, page_size: 100, data_scope: activeScope })
      .then((r) => !cancelled && setRatiosState({ scope: activeScope, items: r.items }))
      .catch(() => !cancelled && setRatiosState({ scope: activeScope, items: null }));
    return () => {
      cancelled = true;
    };
  }, [id, activeScope, attempt]);

  // Single qualified dataset for KPIs, table and charts.
  const qualified = useMemo(
    () =>
      activeScope && activePeriod ? qualifyObservations(rows, { scope: activeScope, periodType: activePeriod }) : [],
    [rows, activeScope, activePeriod],
  );

  if (!data) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={6} cols={4} />
      </div>
    );
  }

  const { institution } = data;
  if (!institution) {
    return <EmptyState title={t("not_found_title")} description={t("not_found")} />;
  }

  const kpiYear = latestYear(qualified);
  const years = qualified.map((o) => o.period_year);
  const range = years.length > 0 ? { from: Math.min(...years), to: Math.max(...years) } : undefined;

  // Ratios are annual indicators in one accounting scope: only those matching the page selection.
  const ratiosError = ratiosState?.scope === activeScope && ratiosState.items === null;
  const ratios = (ratiosState?.scope === activeScope ? (ratiosState.items ?? []) : []).filter(
    (r) => r.period_type === activePeriod && r.data_scope === activeScope,
  );
  const ratioSeries = (code: string) => {
    const pts = ratios.filter((r) => r.ratio_code === code);
    if (pts.length === 0) return [];
    const ys = pts.map((r) => r.period_year);
    const out = [];
    for (let y = Math.min(...ys); y <= Math.max(...ys); y++) {
      const r = pts.find((p) => p.period_year === y);
      out.push({ year: y, value: r ? r.value_percent : null, status: r ? r.status : "unavailable" });
    }
    return out;
  };

  const tabs: { key: Tab; label: string }[] = [
    { key: "financials", label: `${t("tabs.financials")} (${qualified.length})` },
    { key: "ratios", label: `${t("tabs.ratios")} (${ratios.length})` },
    { key: "charts", label: t("tabs.charts") },
    { key: "documents", label: `${t("tabs.documents")} (${data.documents?.length ?? MISSING})` },
  ];

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <Link href="/institutions" className="inline-flex text-xs font-semibold text-gray-400 hover:text-emerald-400 transition-colors">
        ← {t("back")}
      </Link>

      <div className="p-6 md:p-8 rounded-3xl border border-gray-800 bg-gray-900/40">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <span
            data-testid="country-badge"
            className="px-2.5 py-0.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 text-emerald-400 text-xs font-bold uppercase"
          >
            {institution.country?.code ?? MISSING}
          </span>
          <span className="text-xs text-gray-400 font-medium">{labels.country(institution.country, institution.country?.code)}</span>
          <StateBadge
            label={tInst.has(institution.status) ? tInst(institution.status) : institution.status}
            tone={institution.status === "active" ? "ok" : "warn"}
          />
        </div>

        <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight">{institution.name_official}</h1>
        {institution.name_commercial && (
          <p className="text-sm text-emerald-400 font-medium mt-1">
            {t("commercial_name")} : {institution.name_commercial}
          </p>
        )}

        <div className="flex flex-wrap items-center gap-x-6 gap-y-2 mt-4 text-xs text-gray-400">
          <div>
            <span className="text-gray-500">{t("group")} :</span>{" "}
            <span className="text-gray-200 font-semibold">{institution.banking_group?.name ?? MISSING}</span>
          </div>
          <div>
            <span className="text-gray-500">{t("regulatory_id")} :</span>{" "}
            <span className="text-gray-200 font-mono">{institution.regulatory_id ?? MISSING}</span>
          </div>
          {institution.website_url && (
            <a href={institution.website_url} target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">
              {t("website")} ↗
            </a>
          )}
        </div>
      </div>

      {data.rows === null && <ErrorState onRetry={() => setAttempt((a) => a + 1)} />}

      {/* Dataset selectors: one period type and one scope at a time — never mixed. */}
      <div className="flex flex-wrap items-center gap-4 p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs">
        <label className="flex items-center gap-2 text-gray-400">
          {t("scope")}
          <select
            value={activeScope ?? ""}
            onChange={(e) => setScope(e.target.value)}
            disabled={scopes.length === 0}
            className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-950 text-gray-200"
          >
            {scopes.length === 0 && <option value="">{MISSING}</option>}
            {scopes.map((s) => (
              <option key={s} value={s}>
                {labels.scope(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="flex items-center gap-2 text-gray-400">
          {t("period_type")}
          <select
            value={activePeriod ?? ""}
            onChange={(e) => setPeriodType(e.target.value)}
            disabled={periodTypes.length === 0}
            className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-950 text-gray-200"
          >
            {periodTypes.length === 0 && <option value="">{MISSING}</option>}
            {periodTypes.map((p) => (
              <option key={p} value={p}>
                {labels.periodType(p)}
              </option>
            ))}
          </select>
        </label>
        <span className="text-gray-500">{t("dataset_hint")}</span>
      </div>

      <div>
        <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
          {kpiYear === null ? t("kpi_title_none") : t("kpi_title", { year: kpiYear })}
        </h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {KPI_METRICS.map((code) => {
            const o = findObservation(qualified, code, kpiYear);
            return (
              <div key={code} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30" data-testid={`kpi-${code}`}>
                <span className="text-[11px] text-gray-400 font-medium block mb-1">{labels.metric(code)}</span>
                <span className="text-lg font-black text-white">{fmt.compact(o?.value, o?.currency)}</span>
                {o?.conflict && <span className="text-[11px] text-amber-400 block">{t("conflict")}</span>}
              </div>
            );
          })}
        </div>
      </div>

      <div className="flex flex-wrap border-b border-gray-800 gap-4 text-xs font-semibold">
        {tabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`pb-3 px-1 border-b-2 transition-colors ${
              activeTab === tab.key
                ? "border-emerald-500 text-emerald-400 font-bold"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {activeTab === "financials" && <FinancialDataTable observations={qualified} title={t("financials_title")} />}

      {activeTab === "ratios" &&
        (ratiosError ? (
          <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
        ) : (
          <RatioDataTable ratios={ratios} title={t("ratios_title")} />
        ))}

      {activeTab === "charts" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {CHART_METRICS.map((code) => {
            const series = buildYearSeries(qualified, code, range);
            const currency = qualified.find((o) => o.metric_code === code && o.currency)?.currency ?? null;
            return (
              <FinancialLineChart
                key={code}
                data={series}
                title={t("chart_title", { metric: labels.metric(code) })}
                currency={currency}
              />
            );
          })}
          {CHART_RATIOS.map((code) => (
            <FinancialLineChart key={code} data={ratioSeries(code)} title={t("chart_title", { metric: code })} isPercent />
          ))}
        </div>
      )}

      {activeTab === "documents" &&
        (data.documents === null ? (
          <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
        ) : (
          <DocumentsTable documents={data.documents} emptyText={t("documents_empty")} />
        ))}
    </div>
  );
}
