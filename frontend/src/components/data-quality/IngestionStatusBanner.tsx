"use client";

import React, { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { IngestionRun } from "@/types";
import { getLatestIngestionRun } from "@/lib/api";

export function IngestionStatusBanner() {
  const t = useTranslations("data_quality.ingestion");
  const [latestRun, setLatestRun] = useState<IngestionRun | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    getLatestIngestionRun()
      .then((run) => {
        if (mounted) {
          setLatestRun(run);
          setLoading(false);
        }
      })
      .catch(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, []);

  if (loading || !latestRun) {
    return null;
  }

  const statusBadge = {
    completed: "bg-emerald-500/10 text-emerald-400 border-emerald-500/30",
    partial_failure: "bg-amber-500/10 text-amber-400 border-amber-500/30",
    running: "bg-blue-500/10 text-blue-400 border-blue-500/30 animate-pulse",
    failed: "bg-rose-500/10 text-rose-400 border-rose-500/30",
    skipped_concurrent: "bg-gray-800 text-gray-400 border-gray-700",
  }[latestRun.status] ?? "bg-gray-800 text-gray-400 border-gray-700";

  const dateStr = latestRun.started_at
    ? new Date(latestRun.started_at).toLocaleString()
    : "—";

  const statusLabels: Record<string, string> = {
    completed: t("status_completed"),
    partial_failure: t("status_partial_failure"),
    running: t("status_running"),
    failed: t("status_failed"),
    skipped_concurrent: t("status_skipped_concurrent"),
  };

  return (
    <div
      className="p-3.5 rounded-xl border border-gray-800 bg-gray-900/60 flex flex-wrap items-center justify-between gap-3 text-xs"
      data-testid="dq-ingestion-banner"
    >
      <div className="flex items-center gap-2.5">
        <span className="font-semibold text-gray-200">{t("title")}</span>
        <span
          className={`px-2 py-0.5 rounded text-[11px] font-medium border ${statusBadge}`}
          data-testid="dq-ingestion-status"
        >
          {statusLabels[latestRun.status] ?? latestRun.status}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-gray-400 text-[11px]">
        <span>{t("last_run", { time: dateStr })}</span>
        {latestRun.target_years && (
          <span>{t("target_years", { years: latestRun.target_years })}</span>
        )}
        <span>
          {t("stats", {
            docs: latestRun.documents_found,
            metrics: latestRun.data_points_extracted,
          })}
        </span>
        {latestRun.duration_seconds !== null && latestRun.duration_seconds !== undefined && (
          <span>{t("duration", { seconds: latestRun.duration_seconds.toFixed(1) })}</span>
        )}
      </div>
    </div>
  );
}
