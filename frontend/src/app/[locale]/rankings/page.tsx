"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { RankHistory, RankingEntry, RankingResult } from "@/types";
import { getRankHistory, getRankings } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { DATA_SCOPES, PERIOD_TYPES, UMOA, parseRankingParams, supportsPeriodType } from "@/lib/rankings";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { IndicatorSelect, selectCls, useIndicatorLabel } from "@/components/rankings/IndicatorSelect";
import { RankHistoryTable, RankingTable, UnavailableList } from "@/components/rankings/RankingTable";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

const PAGE_SIZE = 20;

export default function RankingsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={6} />}>
      <RankingsContent />
    </Suspense>
  );
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

function RankingsContent() {
  const t = useTranslations("rankings");
  const tCountries = useTranslations("country_names");
  const labels = useLabels();
  const reason = useReasonLabel();
  const indicatorLabel = useIndicatorLabel();
  const { get, set } = useQueryParams();
  const p = parseRankingParams(get);

  const [state, setState] = useState<Load<RankingResult>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [provenance, setProvenance] = useState<RankingEntry | null>(null);
  const [history, setHistory] = useState<Load<RankHistory> | null>(null);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setState({ status: "loading" });
    getRankings({
      metric_code: p.metric,
      period_year: p.year ?? undefined,
      period_type: p.period,
      data_scope: p.scope,
      country_code: p.country,
      order: p.order,
      page: p.page,
      page_size: PAGE_SIZE,
    })
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [p.metric, p.year, p.period, p.scope, p.country, p.order, p.page, attempt]);

  useEffect(() => {
    if (!p.institution) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- history closed
      setHistory(null);
      return;
    }
    let cancelled = false;
    setHistory({ status: "loading" });
    getRankHistory({
      institution_id: p.institution,
      metric_code: p.metric,
      period_type: p.period,
      data_scope: p.scope,
      country_code: p.country,
    })
      .then((data) => !cancelled && setHistory({ status: "ready", data }))
      .catch(() => !cancelled && setHistory({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [p.institution, p.metric, p.period, p.scope, p.country]);

  const result = state.status === "ready" ? state.data : null;
  const years = result?.available_years ?? [];

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <div className="sm:col-span-2">
          <IndicatorSelect
            label={t("filters.metric")}
            value={p.metric}
            onChange={(metric) =>
              set({
                metric,
                page: null,
                period: supportsPeriodType(metric, p.period) ? p.period : "annual",
              })
            }
          />
        </div>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filters.year")}
          <select value={p.year ?? ""} onChange={(e) => set({ year: e.target.value, page: null })} className={selectCls}>
            <option value="">{t("filters.latest_year")}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filters.country")}
          <select value={p.country} onChange={(e) => set({ country: e.target.value, page: null })} className={selectCls}>
            <option value={UMOA}>{t("filters.umoa")}</option>
            {UMOA_COUNTRY_CODES.map((c) => (
              <option key={c} value={c}>
                {tCountries(c)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filters.scope")}
          <select value={p.scope} onChange={(e) => set({ scope: e.target.value, page: null })} className={selectCls}>
            {DATA_SCOPES.map((s) => (
              <option key={s} value={s}>
                {labels.scope(s)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filters.period")}
          <select value={p.period} onChange={(e) => set({ period: e.target.value, page: null })} className={selectCls}>
            {PERIOD_TYPES.filter((pt) => supportsPeriodType(p.metric, pt)).map((pt) => (
              <option key={pt} value={pt}>
                {labels.periodType(pt)}
              </option>
            ))}
          </select>
        </label>
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filters.order")}
          <select value={p.order} onChange={(e) => set({ order: e.target.value, page: null })} className={selectCls}>
            <option value="desc">{t("filters.order_desc")}</option>
            <option value="asc">{t("filters.order_asc")}</option>
          </select>
        </label>
      </div>

      <p className="text-[11px] text-gray-500">{t("method_note")}</p>

      {state.status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : !result ? (
        <TableSkeleton rows={8} cols={6} />
      ) : (
        <>
          <div className="flex flex-wrap items-end justify-between gap-4">
            <div>
              <h2 className="text-lg font-bold text-white" data-testid="ranking-heading">
                {indicatorLabel(result.metric_code)} —{" "}
                {result.country_code === UMOA ? t("filters.umoa") : tCountries(result.country_code)}
                {result.period_year !== null ? ` — ${result.period_year}` : ""}
              </h2>
              <p className="text-[11px] text-gray-500">
                {labels.scope(result.data_scope)} · {labels.periodType(result.period_type)}
              </p>
            </div>
            <div className="w-full sm:w-72 space-y-1">
              {result.coverage.coverage_status === "unavailable" ? (
                // Ranking not computable although values may exist: no 0/N, no 0 %.
                <CoverageIndicator
                  label={t("coverage")}
                  coverageRatio={null}
                  unavailableReason={t("coverage_unavailable", { reason: reason(result.reason) })}
                />
              ) : (
                <CoverageIndicator
                  label={t("coverage")}
                  coverageRatio={result.coverage.coverage_ratio}
                  isPartial={result.status === "partial"}
                  representedCount={result.coverage.ranked_count}
                  totalCount={result.coverage.expected_count}
                />
              )}
              <p className="text-[11px] text-gray-500" data-testid="eligible-ranked">
                {t("eligible_ranked", {
                  eligible: result.coverage.eligible_count,
                  ranked: result.coverage.ranked_count,
                  expected: result.coverage.expected_count,
                })}
              </p>
            </div>
          </div>

          {(result.status === "needs_review" || result.status === "unavailable") && (
            <div role="alert" data-testid="ranking-blocked" className="p-4 rounded-2xl border border-amber-800/60 bg-amber-950/30 text-sm text-amber-200">
              <strong className="block">{t(result.status === "needs_review" ? "blocked_needs_review" : "blocked_unavailable")}</strong>
              <span className="text-xs">{reason(result.reason)}</span>
            </div>
          )}

          {result.items.length > 0 ? (
            <div className="rounded-2xl overflow-hidden">
              <RankingTable
                items={result.items}
                onProvenance={setProvenance}
                onHistory={(institution) => set({ institution })}
              />
              <Pagination
                currentPage={result.page}
                pageSize={result.page_size}
                total={result.total_ranked}
                onPageChange={(page) => set({ page })}
              />
            </div>
          ) : (
            result.status !== "needs_review" &&
            result.status !== "unavailable" && <EmptyState title={t("empty_title")} description={t("empty")} />
          )}

          <UnavailableList entries={result.unavailable} />

          {history && (
            <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3">
              <div className="flex justify-end">
                <button onClick={() => set({ institution: null })} className="text-xs text-gray-400 hover:text-white">
                  ✕ {t("history_close")}
                </button>
              </div>
              {history.status === "error" ? (
                <ErrorState />
              ) : history.status === "loading" ? (
                <TableSkeleton rows={3} cols={4} />
              ) : (
                <RankHistoryTable history={history.data} unit={result.unit} />
              )}
            </div>
          )}
        </>
      )}

      {provenance && (
        <ProvenancePanel
          dataId={provenance.provenance.length > 1 ? null : provenance.data_id}
          sources={provenance.provenance.length > 1 || !provenance.data_id ? provenance.provenance : null}
          onClose={() => setProvenance(null)}
        />
      )}
    </div>
  );
}
