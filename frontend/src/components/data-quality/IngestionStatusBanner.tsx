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
    completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
    partial_failure: "bg-amber-50 text-amber-700 border-amber-200",
    running: "bg-blue-50 text-blue-700 border-blue-200 animate-pulse",
    failed: "bg-rose-50 text-rose-700 border-rose-200",
    skipped_concurrent: "bg-gray-100 text-gray-500 border-gray-300",
  }[latestRun.status] ?? "bg-gray-100 text-gray-500 border-gray-300";

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
      className="p-3.5 rounded-xl border border-gray-200 bg-gray-50/80 flex flex-wrap items-center justify-between gap-3 text-xs"
      data-testid="dq-ingestion-banner"
    >
      <div className="flex items-center gap-2.5">
        <span className="font-semibold text-gray-800">{t("title")}</span>
        <span
          className={`px-2 py-0.5 rounded text-[11px] font-medium border ${statusBadge}`}
          data-testid="dq-ingestion-status"
        >
          {statusLabels[latestRun.status] ?? latestRun.status}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-gray-500 text-[11px]">
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
