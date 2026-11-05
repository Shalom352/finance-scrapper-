"use client";

import React, { useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import type { IngestionRun } from "@/types";
import { useFormatters } from "@/lib/useFormatters";
import { RunStatusBadge, formatDateTime, formatDuration, formatElapsedDuration } from "@/components/settings/RunStatusBadge";
import { dealCollectionTotals } from "@/components/settings/dealSummary";

export const POLL_SECONDS = 3;

/**
 * Live view of the tracked run: elapsed time ticks every second while it is running.
 * A run whose process died stays "running" in the database: ``onAbort`` lets an operator close it
 * (two-step confirmation), otherwise no new run could be launched.
 */
export function RunStatusCard({ run, onAbort }: { run: IngestionRun | null; onAbort?: (runId: string) => Promise<void> }) {
  const t = useTranslations("settings.live");
  const tTrig = useTranslations("settings.triggers");
  const tSources = useTranslations("settings.sources");
  const locale = useLocale();
  const fmt = useFormatters();
  const running = run?.status === "running";
  const [now, setNow] = useState(() => Date.now());
  const [abortState, setAbortState] = useState<"idle" | "confirm" | "sending" | "error">("idle");

  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [running]);

  if (!run) {
    return (
      <section className="p-4 sm:p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs" data-testid="run-card">
        <h2 className="text-base font-bold text-gray-900">{t("title_last")}</h2>
        <p className="mt-2 text-sm text-gray-500">{t("none")}</p>
      </section>
    );
  }

  const elapsed = (now - Date.parse(run.started_at)) / 1000;
  const errors = run.errors ?? [];
  const deals = dealCollectionTotals(run.deal_summary);
  const finalDuration = run.duration_unknown
    ? t("duration_unknown")
    : run.duration_is_lower_bound
      ? t("duration_at_least", { time: formatDuration(run.duration_seconds) })
      : formatDuration(run.duration_seconds);
  const finalMetric = (value: number) => run.results_incomplete ? t("not_finalized") : value;
  const stats: [string, number | string][] = [
    [t("sources_checked"), run.sources_total > 0 ? `${run.sources_checked}/${run.sources_total}` : run.sources_checked],
    [t("docs_found"), finalMetric(run.documents_found)],
    [t("docs_new"), finalMetric(run.documents_new)],
    [t("docs_downloaded"), finalMetric(run.documents_downloaded)],
    [t("docs_skipped"), finalMetric(run.documents_skipped)],
    [t("docs_failed"), finalMetric(run.documents_failed)],
    [t("points"), finalMetric(run.data_points_extracted)],
    [t("to_review"), finalMetric(run.data_points_needing_review)],
  ];
  const phase = run.current_phase
    ? (t.has(`phases.${run.current_phase}`) ? t(`phases.${run.current_phase}`) : run.current_phase)
    : null;
  const source = run.current_source
    ? (tSources.has(run.current_source) ? tSources(run.current_source) : run.current_source)
    : null;
  const pageProgress = run.current_phase === "discovery" && run.current_source === "umoa-titres"
    && run.current_items_total > 0
    ? t("pages_progress", { done: run.current_items_done, total: run.current_items_total })
    : null;

  return (
    <section
      className={`p-4 sm:p-5 rounded-2xl border bg-white shadow-xs space-y-4 ${running ? "border-blue-200" : "border-gray-200/90"}`}
      data-testid="run-card"
      aria-live="polite"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h2 className="text-base font-bold text-gray-900">{running ? t("title_running") : t("title_last")}</h2>
          <p className="text-xs text-gray-500 mt-0.5 break-words">
            {t("started", { date: formatDateTime(run.started_at, locale) })}
            {" · "}
            {running ? t("elapsed", { time: formatElapsedDuration(elapsed) }) : t("duration", { time: finalDuration })}
          </p>
        </div>
        <RunStatusBadge status={run.status} />
      </div>

      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        {stats.map(([label, value]) => (
          <div key={label} className="p-2.5 rounded-xl bg-gray-50 border border-gray-100 min-w-0">
            <dt className="text-[11px] text-gray-500 truncate" title={label}>{label}</dt>
            <dd className="text-lg font-black text-gray-900">{typeof value === "number" ? fmt.number(value) : value}</dd>
          </div>
        ))}
      </dl>

      <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-600">
        <span>{t("trigger")} : <strong className="font-semibold text-gray-800">{tTrig.has(run.trigger_type) ? tTrig(run.trigger_type) : run.trigger_type}</strong></span>
        {run.target_years && <span>{t("years")} : <strong className="font-semibold text-gray-800">{run.target_years}</strong></span>}
        {running && <span className="text-blue-700">{t("polling", { seconds: POLL_SECONDS })}</span>}
      </div>

      {running && (phase || source || pageProgress) && (
        <p className="text-xs text-blue-800 rounded-lg bg-blue-50 border border-blue-100 px-3 py-2">
          {t("current_task", { task: [phase, source, pageProgress].filter(Boolean).join(" · ") })}
        </p>
      )}

      {deals.available && (
        <p className="text-xs text-gray-700">
          {run.results_incomplete
            ? t("deals_partial", { created: deals.created, enriched: deals.enriched, known: deals.known })
            : t("deals_progress", { created: deals.created, enriched: deals.enriched, known: deals.known })}
          {deals.fields > 0 && <span className="text-gray-500"> · {t("deal_fields_added", { count: deals.fields })}</span>}
        </p>
      )}

      {running && onAbort && (
        <div className="p-3 rounded-xl border border-amber-200 bg-amber-50 space-y-2" data-testid="run-abort">
          <p className="text-xs text-amber-800">{t("abort_hint")}</p>
          {abortState === "confirm" || abortState === "sending" ? (
            <div className="flex flex-wrap gap-2">
              <button
                type="button" disabled={abortState === "sending"} data-testid="run-abort-confirm"
                onClick={() => {
                  setAbortState("sending");
                  onAbort(run.id).then(() => setAbortState("idle")).catch(() => setAbortState("error"));
                }}
                className="min-h-9 px-3 rounded-lg bg-rose-600 hover:bg-rose-700 text-white text-xs font-semibold disabled:opacity-40"
              >
                {t("abort_confirm")}
              </button>
              <button type="button" onClick={() => setAbortState("idle")}
                className="min-h-9 px-3 rounded-lg border border-gray-300 bg-white text-gray-700 text-xs font-semibold">
                {t("abort_cancel")}
              </button>
            </div>
          ) : (
            <button type="button" onClick={() => setAbortState("confirm")} data-testid="run-abort-button"
              className="min-h-9 px-3 rounded-lg border border-amber-300 bg-white text-amber-800 hover:bg-amber-100 text-xs font-semibold">
              {t("abort")}
            </button>
          )}
          {abortState === "error" && <p className="text-xs text-rose-700">{t("abort_error")}</p>}
        </div>
      )}

      {run.summary_text && (
        <div>
          <h3 className="text-xs font-semibold text-gray-700">{t("summary")}</h3>
          <p className="mt-1 text-xs text-gray-600 whitespace-pre-line break-words">{run.summary_text}</p>
        </div>
      )}

      <div>
        <h3 className="text-xs font-semibold text-gray-700">{t("errors", { count: errors.length })}</h3>
        {errors.length === 0 ? (
          <p className="mt-1 text-xs text-gray-500">{t("no_errors")}</p>
        ) : (
          <RunErrors errors={errors} />
        )}
      </div>
    </section>
  );
}

export function RunErrors({ errors }: { errors: NonNullable<IngestionRun["errors"]> }) {
  return (
    <ul className="mt-1.5 space-y-1.5 max-h-64 overflow-y-auto" data-testid="run-errors">
      {errors.map((e, i) => (
        <li key={i} className="p-2 rounded-lg border border-rose-200 bg-rose-50 text-xs text-rose-800 break-words">
          {(e.source || e.phase) && (
            <span className="font-semibold">{[e.source, e.phase].filter(Boolean).join(" · ")} — </span>
          )}
          {e.error}
        </li>
      ))}
    </ul>
  );
}
