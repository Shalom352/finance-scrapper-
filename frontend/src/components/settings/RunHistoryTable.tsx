"use client";

import React, { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { IngestionRun } from "@/types";
import { useFormatters } from "@/lib/useFormatters";
import { dateKey, useSort } from "@/lib/useSort";
import { SortHeader, SortSelect } from "@/components/common/SortHeader";
import { RunStatusBadge, formatDateTime, formatDuration, formatElapsedDuration } from "@/components/settings/RunStatusBadge";
import { RunErrors } from "@/components/settings/RunStatusCard";
import { dealCollectionTotals, sourceDealSummaries } from "@/components/settings/dealSummary";

/** Number of recorded errors (a run without an error list has none). */
const errorCount = (r: IngestionRun) => (r.errors ? r.errors.length : 0);

type Key = "date" | "trigger" | "status" | "duration" | "docs" | "points" | "deals" | "errors";

const ACCESSORS: Record<Key, (r: IngestionRun) => string | number | null> = {
  date: (r) => dateKey(r.started_at),
  trigger: (r) => r.trigger_type,
  status: (r) => r.status,
  duration: (r) => r.duration_seconds,
  docs: (r) => r.documents_found,
  points: (r) => r.data_points_extracted,
  deals: (r) => {
    const totals = dealCollectionTotals(r.deal_summary);
    return totals.available ? totals.created + totals.enriched + totals.known : null;
  },
  errors: (r) => errorCount(r),
};
const dealCountArgs = (totals: ReturnType<typeof dealCollectionTotals>) => ({
  created: totals.created,
  enriched: totals.enriched,
  known: totals.known,
});
/** Text columns open ascending; dates and quantities open with the largest first. */
const FIRST_DIR: Record<Key, "asc" | "desc"> = {
  date: "desc", trigger: "asc", status: "asc", duration: "desc", docs: "desc", points: "desc", deals: "desc",
  errors: "desc",
};

export function RunHistoryTable({ runs }: { runs: IngestionRun[] }) {
  const t = useTranslations("settings.history");
  const tTrig = useTranslations("settings.triggers");
  const tSources = useTranslations("settings.sources");
  const tSort = useTranslations("common.sort");
  const locale = useLocale();
  const fmt = useFormatters();
  const { sorted, sortKey, dir, toggle, setSort } = useSort(runs, ACCESSORS, { key: "date", dir: "desc" });
  const [open, setOpen] = useState<string | null>(null);
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!runs.some((run) => run.status === "running")) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [runs]);
  const duration = (run: IngestionRun) => run.duration_seconds ?? (
    run.status === "running" ? Math.max(0, (now - Date.parse(run.started_at)) / 1000) : null
  );
  const durationText = (run: IngestionRun) => run.duration_unknown
    ? t("duration_unknown")
    : run.status === "running"
      ? formatElapsedDuration(duration(run))
    : run.duration_is_lower_bound
      ? t("duration_at_least", { time: formatDuration(duration(run)) })
      : formatDuration(duration(run));

  const trigger = (r: IngestionRun) => (tTrig.has(r.trigger_type) ? tTrig(r.trigger_type) : r.trigger_type);
  const docs = (r: IngestionRun) => r.results_incomplete
    ? t("not_finalized")
    : t("docs_detail", { found: r.documents_found, new: r.documents_new, failed: r.documents_failed });
  const deals = (r: IngestionRun) => {
    const totals = dealCollectionTotals(r.deal_summary);
    if (!totals.available) return r.results_incomplete ? t("not_finalized") : "—";
    return r.results_incomplete
      ? t("deal_stats_partial", dealCountArgs(totals))
      : t("deal_stats", dealCountArgs(totals));
  };
  const head = (key: Key, label: string, cls = "") => (
    <SortHeader
      label={label} active={sortKey === key} dir={dir} onClick={() => toggle(key, FIRST_DIR[key])}
      className={`py-3 px-3 ${cls}`} testId={`runs-sort-${key}`}
    />
  );
  const details = (r: IngestionRun) => (
    <div className="space-y-2 text-xs text-gray-600">
      {r.target_years && <p>{t("years", { years: r.target_years })}</p>}
      {r.results_incomplete && <p className="text-amber-800">{t("partial_result")}</p>}
      {r.summary_text && <p className="whitespace-pre-line break-words">{r.summary_text}</p>}
      {sourceDealSummaries(r.deal_summary).map(([source, summary]) => {
        const totals = dealCollectionTotals({ [source]: summary });
        if (!totals.available) return null;
        const sourceName = tSources.has(source) ? tSources(source) : source;
        return (
          <p key={source}>
            <strong>{sourceName}:</strong> {r.results_incomplete
              ? t("deal_stats_partial", dealCountArgs(totals))
              : t("deal_stats", dealCountArgs(totals))}
            {totals.fields > 0 && <> · {t("deal_fields_added", { count: totals.fields })}</>}
            {typeof summary.deferred === "number" && summary.deferred > 0 && <> · {t("deferred", { count: summary.deferred })}</>}
          </p>
        );
      })}
      {r.errors && r.errors.length > 0 && <RunErrors errors={r.errors} />}
    </div>
  );
  const hasDetails = (r: IngestionRun) => Boolean(r.summary_text || r.target_years || r.errors?.length || r.deal_summary);
  const toggleBtn = (r: IngestionRun) =>
    hasDetails(r) ? (
      <button
        type="button"
        onClick={() => setOpen(open === r.id ? null : r.id)}
        aria-expanded={open === r.id}
        className="min-h-9 px-3 rounded-lg border border-gray-200 bg-white text-xs font-medium text-gray-700 hover:bg-gray-50 whitespace-nowrap"
      >
        {open === r.id ? t("hide") : t("details")}
      </button>
    ) : null;

  if (runs.length === 0) return <p className="p-4 text-sm text-gray-500">{t("empty")}</p>;

  return (
    <div data-testid="runs-history">
      {/* Phone and small tablet: cards with a sort selector. */}
      <div className="md:hidden space-y-3 p-3">
        <SortSelect
          options={(Object.keys(ACCESSORS) as Key[]).map((k) => ({ key: k, label: t(k) }))}
          sortKey={sortKey} dir={dir} onChange={setSort}
          label={tSort("label")} ascLabel={tSort("asc")} descLabel={tSort("desc")}
        />
        <ul className="space-y-2.5">
          {sorted.map((r) => (
            <li key={r.id} className="p-3 rounded-xl border border-gray-200 bg-white space-y-2" data-testid="run-card-row">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold text-gray-900">{formatDateTime(r.started_at, locale)}</span>
                <RunStatusBadge status={r.status} />
              </div>
              <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-xs">
                <dt className="text-gray-500">{t("trigger")}</dt><dd className="text-gray-800">{trigger(r)}</dd>
                <dt className="text-gray-500">{t("duration")}</dt><dd className="text-gray-800">{durationText(r)}</dd>
                <dt className="text-gray-500">{t("docs")}</dt><dd className="text-gray-800 break-words">{docs(r)}</dd>
                <dt className="text-gray-500">{t("points")}</dt>
                <dd className="text-gray-800">{r.results_incomplete ? t("not_finalized") : <>{fmt.number(r.data_points_extracted)} ({t("to_review")} : {fmt.number(r.data_points_needing_review)})</>}</dd>
                <dt className="text-gray-500">{t("deals")}</dt><dd className="text-gray-800">{deals(r)}</dd>
                <dt className="text-gray-500">{t("errors")}</dt>
                <dd className={r.errors?.length ? "text-rose-700 font-semibold" : "text-gray-800"}>{errorCount(r)}</dd>
              </dl>
              {toggleBtn(r)}
              {open === r.id && details(r)}
            </li>
          ))}
        </ul>
      </div>

      {/* Desktop: sortable table scrolling inside its own container. */}
      <div className="hidden md:block overflow-x-auto">
        <table className="w-full min-w-[980px] text-left text-xs border-collapse" data-testid="runs-table">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase tracking-wider">
              {head("date", t("date"))}
              {head("trigger", t("trigger"))}
              {head("status", t("status"))}
              {head("duration", t("duration"), "text-right")}
              {head("docs", t("docs"))}
              {head("points", t("points"), "text-right")}
              {head("deals", t("deals"))}
              {head("errors", t("errors"), "text-right")}
              <th className="py-3 px-3" aria-label={t("details")} />
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((r) => (
              <React.Fragment key={r.id}>
                <tr className="hover:bg-gray-50/70 transition-colors" data-testid="run-row">
                  <td className="py-2.5 px-3 font-semibold text-gray-900 whitespace-nowrap">{formatDateTime(r.started_at, locale)}</td>
                  <td className="py-2.5 px-3 text-gray-700">{trigger(r)}</td>
                  <td className="py-2.5 px-3"><RunStatusBadge status={r.status} /></td>
                  <td className="py-2.5 px-3 text-right text-gray-700 whitespace-nowrap">{durationText(r)}</td>
                  <td className="py-2.5 px-3 text-gray-700">{docs(r)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-800">
                    {r.results_incomplete ? t("not_finalized") : fmt.number(r.data_points_extracted)}
                    {!r.results_incomplete && r.data_points_needing_review > 0 && (
                      <span className="block text-[11px] text-amber-700">{t("to_review")} : {fmt.number(r.data_points_needing_review)}</span>
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-gray-700">{deals(r)}</td>
                  <td className={`py-2.5 px-3 text-right ${r.errors?.length ? "text-rose-700 font-semibold" : "text-gray-500"}`}>
                    {errorCount(r)}
                  </td>
                  <td className="py-2.5 px-3 text-right">{toggleBtn(r)}</td>
                </tr>
                {open === r.id && (
                  <tr className="bg-gray-50/60">
                    <td colSpan={9} className="px-3 py-3">{details(r)}</td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
