"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { IngestionStatus } from "@/types";

const STATUS_CLS: Record<IngestionStatus, string> = {
  completed: "bg-emerald-50 text-emerald-700 border-emerald-200",
  partial_failure: "bg-amber-50 text-amber-700 border-amber-200",
  running: "bg-blue-50 text-blue-700 border-blue-200",
  failed: "bg-rose-50 text-rose-700 border-rose-200",
  skipped_concurrent: "bg-gray-100 text-gray-600 border-gray-300",
};

export function RunStatusBadge({ status }: { status: IngestionStatus | string }) {
  const t = useTranslations("settings.status");
  const known = status in STATUS_CLS;
  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md border text-[11px] font-semibold whitespace-nowrap ${
        known ? STATUS_CLS[status as IngestionStatus] : "bg-gray-100 text-gray-600 border-gray-300"
      }`}
      data-testid="run-status"
    >
      {status === "running" && <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" aria-hidden="true" />}
      {known ? t(status) : status}
    </span>
  );
}

/** "45 s", "3 min 05 s", "1 h 02 min"; null stays "—". */
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const s = Math.max(0, Math.round(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min ${String(s % 60).padStart(2, "0")} s`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, "0")} min`;
}

/** Live durations include seconds so a running collection visibly advances in real time. */
export function formatElapsedDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) return "—";
  const total = Math.max(0, Math.round(seconds));
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const remainder = String(total % 60).padStart(2, "0");
  if (hours > 0) return `${hours} h ${String(minutes).padStart(2, "0")} min ${remainder} s`;
  if (minutes > 0) return `${minutes} min ${remainder} s`;
  return `${total} s`;
}

/** Date and time of a run, in the active locale. */
export function formatDateTime(iso: string | null | undefined, locale: string): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(locale === "en" ? "en-GB" : "fr-FR", { dateStyle: "medium", timeStyle: "short" });
}
