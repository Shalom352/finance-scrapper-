"use client";

import React from "react";
import { useLocale, useTranslations } from "next-intl";
import type { IngestionRun, ReviewCenterCounts } from "@/types";
import { useFormatters } from "@/lib/useFormatters";
import { formatDateTime, formatDuration } from "@/components/settings/RunStatusBadge";

interface KpiTilesProps {
  latest: IngestionRun | null;
  /** Runs of the history page currently loaded (the API exposes no aggregate). */
  sample: IngestionRun[];
  counts: ReviewCenterCounts | null;
  apiUp: boolean | null;
}

export function KpiTiles({ latest, sample, counts, apiUp }: KpiTilesProps) {
  const t = useTranslations("settings.kpi");
  const locale = useLocale();
  const fmt = useFormatters();

  const finished = sample.filter((r) => r.status !== "running" && r.status !== "skipped_concurrent");
  const ok = finished.filter((r) => r.status === "completed").length;
  const durations = finished.map((r) => r.duration_seconds).filter((d): d is number => typeof d === "number");
  const avg = durations.length ? durations.reduce((a, b) => a + b, 0) / durations.length : null;
  const sampleHint = t("sample_hint", { count: sample.length });

  const tiles: { label: string; value: string; hint?: string; tone?: string }[] = [
    { label: t("last_run"), value: latest ? formatDateTime(latest.started_at, locale) : t("never") },
    {
      label: t("api"),
      value: apiUp === null ? "—" : apiUp ? t("api_ok") : t("api_down"),
      tone: apiUp === null ? "" : apiUp ? "text-emerald-700" : "text-rose-700",
    },
    { label: t("docs_found"), value: fmt.number(latest?.documents_found), hint: t("last_run_hint") },
    { label: t("docs_new"), value: fmt.number(latest?.documents_new), hint: t("last_run_hint") },
    {
      label: t("docs_failed"),
      value: fmt.number(latest?.documents_failed),
      hint: t("last_run_hint"),
      tone: latest && latest.documents_failed > 0 ? "text-rose-700" : "",
    },
    { label: t("points"), value: fmt.number(latest?.data_points_extracted), hint: t("last_run_hint") },
    { label: t("success_rate"), value: finished.length ? fmt.percent((ok / finished.length) * 100, 0) : "—", hint: sampleHint },
    { label: t("avg_duration"), value: formatDuration(avg), hint: sampleHint },
    { label: t("observations"), value: fmt.number(counts?.total) },
    { label: t("verified"), value: fmt.number(counts?.verified) },
    { label: t("needs_review"), value: fmt.number(counts?.needs_review), tone: counts && counts.needs_review > 0 ? "text-amber-700" : "" },
    { label: t("deals"), value: fmt.number(counts?.deals_total) },
  ];

  return (
    <section className="space-y-3" data-testid="kpi-tiles">
      <h2 className="text-base font-bold text-gray-900">{t("title")}</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2.5 sm:gap-3">
        {tiles.map((tile) => (
          <div key={tile.label} className="p-3 sm:p-4 rounded-2xl border border-gray-200/90 bg-white shadow-xs min-w-0">
            <div className="text-[11px] font-medium text-gray-500 leading-snug">{tile.label}</div>
            <div className={`mt-1 text-base sm:text-lg font-black break-words ${tile.tone || "text-gray-900"}`}>{tile.value}</div>
            {tile.hint && <div className="mt-0.5 text-[10px] text-gray-500 leading-snug">{tile.hint}</div>}
          </div>
        ))}
      </div>
    </section>
  );
}
