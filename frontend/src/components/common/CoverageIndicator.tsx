"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";

interface CoverageIndicatorProps {
  /** 0.0 to 1.0, exactly as returned by the API. null/undefined = unknown → "—". */
  coverageRatio: number | null | undefined;
  /** Backend `is_partial` flag — the only source of the partial-data warning. */
  isPartial?: boolean | null;
  representedCount?: number | null;
  totalCount?: number | null;
  label?: string;
  /** Explanation shown when coverage is unknown (replaces the generic API message). */
  unavailableReason?: string;
  className?: string;
}

export function CoverageIndicator({
  coverageRatio,
  isPartial,
  representedCount,
  totalCount,
  label,
  unavailableReason,
  className = "",
}: CoverageIndicatorProps) {
  const t = useTranslations("coverage");
  const fmt = useFormatters();
  const known = coverageRatio !== null && coverageRatio !== undefined && !Number.isNaN(coverageRatio);
  const pct = known ? Math.min(Math.max(coverageRatio * 100, 0), 100) : null;
  const partial = isPartial === true;

  const badgeColor = !known
    ? "bg-white text-gray-500 border-gray-200"
    : partial
      ? "bg-amber-50 text-amber-700 border-amber-200"
      : "bg-emerald-50 text-emerald-700 border-emerald-200";

  return (
    <div className={`flex flex-col gap-1.5 ${className}`} data-testid="coverage-indicator">
      <div className="flex flex-wrap items-center justify-between gap-x-2 gap-y-1 text-xs">
        <span className="min-w-0 text-gray-500 font-medium">{label ?? t("label")}</span>
        <div className="flex shrink-0 items-center gap-2">
          {representedCount != null && totalCount != null && (
            <span className="text-gray-500 text-xs">
              {representedCount}/{totalCount}
            </span>
          )}
          <span data-testid="coverage-value" className={`px-2 py-0.5 rounded border text-xs font-semibold ${badgeColor}`}>
            {pct === null ? MISSING : fmt.percent(pct, 1)}
          </span>
        </div>
      </div>

      {pct !== null && (
        <div className="w-full h-1.5 rounded-full bg-gray-100 overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-500 ${partial ? "bg-amber-500" : "bg-emerald-500"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {pct === null && (
        <span className="text-[11px] text-gray-500" data-testid="coverage-unknown">
          {unavailableReason ?? t("unknown")}
        </span>
      )}

      {partial && <span className="text-[11px] text-amber-700">⚠️ {t("partial_warning")}</span>}
    </div>
  );
}
