"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type {
  GrowthResult,
  RatioDefinition,
  RatioResult,
  SectorAggregation,
} from "@/types";
import {
  getAggregations,
  getAvailableYears,
  getGrowth,
  getRatioDefinitions,
  getRatios,
} from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { useQueryParams } from "@/lib/useQueryParams";
import { parseYearParam, resolveYear } from "@/lib/url";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { StatusBadge } from "@/components/common/StatusBadge";
import { RatioDataTable } from "@/components/tables/RatioDataTable";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

const CORE_METRICS = [
  "total_actifs",
  "depots_clients",
  "creances_clients",
  "produit_net_bancaire",
  "resultat_net",
  "capitaux_propres",
] as const;

type Tab = "ratios" | "growth" | "aggregations" | "compare";
const TABS: Tab[] = ["ratios", "growth", "aggregations", "compare"];

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

const selectCls =
  "mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none";

export default function AnalyticsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={5} />}>
      <AnalyticsContent />
    </Suspense>
  );
}

function AnalyticsContent() {
  const t = useTranslations("analytics");
  const tCountries = useTranslations("country_names");
  const { get, set } = useQueryParams();

  const tab = (TABS as string[]).includes(get("tab")) ? (get("tab") as Tab) : "ratios";
  const country = get("country");
  const requestedYear = parseYearParam(get("year"));

  const [years, setYears] = useState<number[] | null>(null);
  const [yearsError, setYearsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setYears(null);
    setYearsError(false);
    getAvailableYears({ country_code: country || undefined })
      .then((y) => !cancelled && setYears(y))
      .catch(() => !cancelled && setYearsError(true));
    return () => {
      cancelled = true;
    };
  }, [country]);

  const year = years ? resolveYear(requestedYear, years) : null;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <div className="flex flex-wrap border-b border-gray-800 gap-4 text-xs font-semibold">
        {TABS.map((key) => (
          <button
            key={key}
            onClick={() => set({ tab: key })}
            className={`pb-3 px-1 border-b-2 transition-colors ${
              tab === key ? "border-emerald-500 text-emerald-400 font-bold" : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {t(`tabs.${key}`)}
          </button>
        ))}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <label className="text-[11px] text-gray-400 font-medium">
          {t("fiscal_year")}
          <select
            value={year ?? ""}
            onChange={(e) => set({ year: e.target.value })}
            disabled={!years || years.length === 0}
            className={selectCls}
          >
            {(!years || years.length === 0) && <option value="">{MISSING}</option>}
            {(years ?? []).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        {tab !== "compare" && (
          <label className="text-[11px] text-gray-400 font-medium">
            {t("country_filter")}
            <select value={country} onChange={(e) => set({ country: e.target.value })} className={selectCls}>
              <option value="">{t("all_countries")}</option>
              {UMOA_COUNTRY_CODES.map((c) => (
                <option key={c} value={c}>
                  {tCountries(c)} ({c})
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      <p className="text-[11px] text-gray-500">{t("scope_note")}</p>

      {yearsError ? (
        <ErrorState />
      ) : years === null ? (
        <TableSkeleton rows={6} cols={5} />
      ) : year === null ? (
        <EmptyState title={t("no_years_title")} description={t("no_years")} />
      ) : (
        <>
          {tab === "ratios" && <RatiosTab year={year} country={country} />}
          {tab === "growth" && <GrowthTab year={year} country={country} />}
          {tab === "aggregations" && <AggregationsTab year={year} country={country} />}
          {tab === "compare" && <CompareTab />}
        </>
      )}
    </div>
  );
}

function RatiosTab({ year, country }: { year: number; country: string }) {
  const t = useTranslations("analytics.ratios");
  const locale = useLocale();
  const { get, set } = useQueryParams();
  const [definitions, setDefinitions] = useState<RatioDefinition[]>([]);
  const [state, setState] = useState<Load<RatioResult[]>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const ratioCode = get("ratio") || definitions[0]?.ratio_code || "";

  useEffect(() => {
    getRatioDefinitions()
      .then(setDefinitions)
      .catch(() => setDefinitions([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setState({ status: "loading" });
    getRatios({ ratio_code: ratioCode || undefined, year, country_code: country || undefined, page_size: 100 })
      .then((res) => !cancelled && setState({ status: "ready", data: res.items }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [ratioCode, year, country, attempt]);

  const def = definitions.find((d) => d.ratio_code === ratioCode);

  return (
    <div className="space-y-6">
      <label className="block text-[11px] text-gray-400 font-medium max-w-md">
        {t("select_ratio")}
        <select value={ratioCode} onChange={(e) => set({ ratio: e.target.value })} className={selectCls}>
          {definitions.map((d) => (
            <option key={d.ratio_code} value={d.ratio_code}>
              {locale === "en" ? d.name_en : d.name_fr} ({d.ratio_code})
            </option>
          ))}
        </select>
      </label>

      {def && (
        <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/60 flex flex-col md:flex-row md:items-center justify-between gap-4 text-xs">
          <div className="space-y-1">
            <span className="font-bold text-gray-200 text-sm">{locale === "en" ? def.name_en : def.name_fr}</span>
            <p className="text-gray-400">{locale === "en" ? def.description_en : def.description_fr}</p>
            <div className="pt-1 flex flex-wrap gap-2 text-[11px]">
              <span className="text-gray-500">{t("rules")}</span>
              {def.eligibility_rules.map((r, i) => (
                <span key={i} className="text-emerald-400 font-medium">
                  • {r}
                </span>
              ))}
            </div>
          </div>
          <div className="shrink-0 p-3 rounded-xl bg-gray-950 border border-gray-800 text-center font-mono">
            <span className="text-[10px] text-gray-500 block uppercase">{t("formula")}</span>
            <span className="text-xs text-emerald-300 font-bold">{def.formula}</span>
          </div>
        </div>
      )}

      {state.status === "loading" ? (
        <TableSkeleton rows={8} cols={5} />
      ) : state.status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : (
        <RatioDataTable ratios={state.data} title={t("table_title", { ratio: ratioCode, year })} />
      )}
    </div>
  );
}

function GrowthTab({ year, country }: { year: number; country: string }) {
  const t = useTranslations("analytics.growth");
  const reasonLabel = useReasonLabel();
  const fmt = useFormatters();
  const labels = useLabels();
  const { get, set } = useQueryParams();
  const metric = (CORE_METRICS as readonly string[]).includes(get("metric")) ? get("metric") : CORE_METRICS[0];
  const [state, setState] = useState<Load<GrowthResult[]>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setState({ status: "loading" });
    getGrowth({ metric_code: metric, year, country_code: country || undefined, page_size: 100 })
      .then((res) => !cancelled && setState({ status: "ready", data: res.items }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [metric, year, country, attempt]);

  return (
    <div className="space-y-6">
      <label className="block text-[11px] text-gray-400 font-medium max-w-md">
        {t("select_metric")}
        <select value={metric} onChange={(e) => set({ metric: e.target.value })} className={selectCls}>
          {CORE_METRICS.map((m) => (
            <option key={m} value={m}>
              {labels.metric(m)}
            </option>
          ))}
        </select>
      </label>
      <p className="text-[11px] text-gray-500">{t("period_hint", { year, previous: year - 1 })}</p>

      {state.status === "loading" ? (
        <TableSkeleton rows={8} cols={6} />
      ) : state.status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : state.data.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty")} />
      ) : (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">{t("table.institution")}</th>
                <th className="py-3 px-4">{t("table.country")}</th>
                <th className="py-3 px-4 text-right">{t("table.current_val")}</th>
                <th className="py-3 px-4 text-right">{t("table.previous_val")}</th>
                <th className="py-3 px-4 text-right">{t("table.abs_change")}</th>
                <th className="py-3 px-4 text-right">{t("table.growth_pct")}</th>
                <th className="py-3 px-4 text-center">{t("table.status")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-800/60">
              {state.data.map((g, idx) => {
                const pct = g.growth_percent;
                // Neutral colours: a variation is a fact, not a judgement (the arrow gives the sign).
                const tone = pct === null ? "text-gray-500" : "text-gray-200";
                const arrow = pct === null ? "" : pct > 0 ? "▲ " : pct < 0 ? "▼ " : "";
                return (
                  <tr key={`${g.institution_id}-${idx}`} className="hover:bg-gray-800/30 transition-colors">
                    <td className="py-3.5 px-4 font-bold text-gray-200">
                      {g.institution_name ?? g.institution_id}
                      {g.reason && <span className="block text-[11px] font-normal text-amber-400/90">{reasonLabel(g.reason)}</span>}
                    </td>
                    <td className="py-3.5 px-4 font-mono font-bold text-emerald-400">{g.country_code ?? MISSING}</td>
                    <td className="py-3.5 px-4 text-right text-gray-300">
                      <span className="block text-[10px] text-gray-500">{g.current_year}</span>
                      {fmt.compact(g.current_value, g.currency)}
                    </td>
                    <td className="py-3.5 px-4 text-right text-gray-400">
                      <span className="block text-[10px] text-gray-500">{g.previous_year}</span>
                      {fmt.compact(g.previous_value, g.currency)}
                    </td>
                    <td className="py-3.5 px-4 text-right font-mono text-gray-300">{fmt.compact(g.absolute_change, g.currency)}</td>
                    <td className={`py-3.5 px-4 text-right font-black text-sm ${tone}`}>
                      {arrow}
                      {fmt.signedPercent(pct, 2)}
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
  );
}

function AggregationsTab({ year, country }: { year: number; country: string }) {
  const t = useTranslations("analytics.aggregations");
  const tCountries = useTranslations("country_names");
  const fmt = useFormatters();
  const labels = useLabels();
  const { get, set } = useQueryParams();
  const metric = (CORE_METRICS as readonly string[]).includes(get("metric")) ? get("metric") : CORE_METRICS[0];
  const [state, setState] = useState<Load<SectorAggregation[]>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setState({ status: "loading" });
    getAggregations({ year, metric_code: metric, scope: "country", country_code: country || undefined })
      .then((res) => {
        // Only aggregations of the requested metric and year are displayed.
        const matching = res.filter((a) => a.metric_code === metric && a.year === year);
        if (!cancelled) setState({ status: "ready", data: matching });
      })
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [metric, year, country, attempt]);

  return (
    <div className="space-y-6">
      <label className="block text-[11px] text-gray-400 font-medium max-w-md">
        {t("select_metric")}
        <select value={metric} onChange={(e) => set({ metric: e.target.value })} className={selectCls}>
          {CORE_METRICS.map((m) => (
            <option key={m} value={m}>
              {labels.metric(m)}
            </option>
          ))}
        </select>
      </label>

      {state.status === "loading" ? (
        <TableSkeleton rows={4} cols={4} />
      ) : state.status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : state.data.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty")} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {state.data.map((agg, idx) => (
            <div key={`${agg.country_code}-${idx}`} className="p-5 rounded-2xl border border-gray-800 bg-gray-900/40 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between mb-2">
                  <span className="font-bold text-gray-200 text-sm">
                    {agg.country_code && tCountries.has(agg.country_code) ? tCountries(agg.country_code) : (agg.country_name ?? MISSING)}
                  </span>
                  <span className="px-2 py-0.5 rounded bg-gray-800 text-xs font-mono font-bold text-emerald-400">
                    {agg.country_code ?? MISSING}
                  </span>
                </div>
                <span className="text-[11px] text-gray-500">
                  {labels.metric(agg.metric_code)} · {agg.year}
                </span>
                <span className="text-xl font-black text-white block mt-2">{fmt.compact(agg.total_value, agg.currency)}</span>
                {agg.status === "needs_review" && <StatusBadge status="needs_review" size="sm" className="mt-1" />}
              </div>
              <div className="mt-4 pt-3 border-t border-gray-800/80">
                <CoverageIndicator
                  coverageRatio={agg.coverage_ratio}
                  isPartial={agg.is_partial}
                  representedCount={agg.institution_count}
                  totalCount={agg.total_institutions}
                />
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function CompareTab() {
  const t = useTranslations("analytics.compare");
  return (
    <div className="p-6 rounded-2xl border border-gray-800 bg-gray-900/40 flex flex-col sm:flex-row sm:items-center justify-between gap-4">
      <p className="text-sm text-gray-300">{t("moved")}</p>
      <Link
        href="/comparisons"
        className="px-5 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors"
      >
        {t("open")}
      </Link>
    </div>
  );
}
