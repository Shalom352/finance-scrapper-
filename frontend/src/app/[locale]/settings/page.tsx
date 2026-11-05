"use client";

import React, { useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { IngestionRun, PaginatedResponse, ReviewCenterCounts } from "@/types";
import { abortIngestionRun, getApiHealth, getDataQualityCounts, getIngestionRun, getLatestIngestionRun, listIngestionRuns } from "@/lib/api";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorState } from "@/components/common/EmptyState";
import { TriggerForm } from "@/components/settings/TriggerForm";
import { POLL_SECONDS, RunStatusCard } from "@/components/settings/RunStatusCard";
import { KpiTiles } from "@/components/settings/KpiTiles";
import { RunHistoryTable } from "@/components/settings/RunHistoryTable";

const PAGE_SIZE = 20;

/**
 * Collection control console. Uses only the existing ingestion endpoints: trigger, runs,
 * runs/latest, runs/{id}. "Live" = polling of the tracked run (no push channel in the API).
 */
export default function SettingsPage() {
  const t = useTranslations("settings");
  const [page, setPage] = useState(1);
  const [runs, setRuns] = useState<PaginatedResponse<IngestionRun> | null>(null);
  const [runsError, setRunsError] = useState(false);
  const [tracked, setTracked] = useState<IngestionRun | null>(null);
  const [counts, setCounts] = useState<ReviewCenterCounts | null>(null);
  const [apiUp, setApiUp] = useState<boolean | null>(null);
  const [reload, setReload] = useState(0);
  const refresh = useCallback(() => setReload((n) => n + 1), []);
  const mergeRun = useCallback((run: IngestionRun) => {
    setRuns((current) => {
      if (!current) return current;
      const index = current.items.findIndex((item) => item.id === run.id);
      if (index >= 0) {
        const items = [...current.items];
        items[index] = run;
        return { ...current, items };
      }
      if (page !== 1) return current;
      return { ...current, items: [run, ...current.items].slice(0, PAGE_SIZE), total: current.total + 1 };
    });
  }, [page]);

  // History page (follows pagination).
  useEffect(() => {
    let cancelled = false;
    listIngestionRuns(page, PAGE_SIZE)
      .then((res) => {
        if (cancelled) return;
        setRuns(res);
        setRunsError(false);
      })
      .catch(() => !cancelled && setRunsError(true));
    return () => {
      cancelled = true;
    };
  }, [page, reload]);

  // Latest run, counters and API state.
  useEffect(() => {
    let cancelled = false;
    getLatestIngestionRun().then((run) => !cancelled && setTracked(run));
    getDataQualityCounts().then((c) => !cancelled && setCounts(c)).catch(() => !cancelled && setCounts(null));
    getApiHealth().then((ok) => !cancelled && setApiUp(ok));
    return () => {
      cancelled = true;
    };
  }, [reload]);

  // Live follow-up of a running run; once it ends, everything is reloaded.
  const trackedId = tracked?.id;
  const running = tracked?.status === "running";
  useEffect(() => {
    if (!trackedId || !running) return;
    const id = setInterval(() => {
      getIngestionRun(trackedId)
        .then((run) => {
          setTracked(run);
          mergeRun(run);
          if (run.status !== "running") refresh();
        })
        .catch(() => undefined);
    }, POLL_SECONDS * 1000);
    return () => clearInterval(id);
  }, [trackedId, running, refresh, mergeRun]);

  const onStarted = (runId: string | null) => {
    if (runId) getIngestionRun(runId).then((run) => { setTracked(run); mergeRun(run); }).catch(() => undefined);
    setPage(1);
    refresh();
  };

  return (
    <div className="space-y-6 animate-fade-in pb-12" data-testid="settings-page">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-black text-gray-900 tracking-tight break-words">{t("title")}</h1>
          <p className="text-xs text-gray-500 mt-1 max-w-3xl">{t("subtitle")}</p>
        </div>
        <button
          type="button"
          onClick={refresh}
          className="min-h-10 px-4 rounded-xl border border-gray-200 bg-white text-sm font-medium text-gray-700 hover:bg-gray-50 shadow-xs"
          data-testid="settings-refresh"
        >
          {t("refresh")}
        </button>
      </div>

      <KpiTiles latest={tracked} sample={runs?.items ?? []} counts={counts} apiUp={apiUp} />

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 sm:gap-6 items-start">
        <TriggerForm busy={running} onStarted={onStarted} />
        <RunStatusCard
          run={tracked}
          onAbort={async (runId) => {
            setTracked(await abortIngestionRun(runId));
            refresh();
          }}
        />
      </div>

      <section className="rounded-2xl border border-gray-200/90 bg-white shadow-xs overflow-hidden">
        <div className="px-4 sm:px-5 py-3.5 border-b border-gray-200/80 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-base font-bold text-gray-900">{t("history.title")}</h2>
        </div>
        {runsError ? (
          <div className="p-4"><ErrorState onRetry={refresh} /></div>
        ) : !runs ? (
          <TableSkeleton rows={6} cols={6} />
        ) : (
          <>
            <RunHistoryTable runs={runs.items} />
            {runs.total > PAGE_SIZE && (
              <Pagination currentPage={page} pageSize={PAGE_SIZE} total={runs.total} onPageChange={setPage} />
            )}
          </>
        )}
      </section>
    </div>
  );
}
