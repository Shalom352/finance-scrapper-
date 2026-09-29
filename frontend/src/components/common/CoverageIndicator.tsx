"use client";

import React from "react";
import { formatPercent } from "@/lib/formatters";

interface CoverageIndicatorProps {
  coverageRatio: number; // 0.0 to 1.0
  representedCount?: number;
  totalCount?: number;
  label?: string;
  showWarningIfPartial?: boolean;
  className?: string;
}

export function CoverageIndicator({
  coverageRatio,
  representedCount,
  totalCount,
  label = "Couverture",
  showWarningIfPartial = true,
  className = "",
}: CoverageIndicatorProps) {
  const pct = Math.min(Math.max(coverageRatio * 100, 0), 100);
  const isPartial = coverageRatio < 0.999;

  const barColor = isPartial ? "bg-amber-500" : "bg-emerald-500";
  const badgeColor = isPartial
    ? "bg-amber-950/60 text-amber-300 border-amber-800/60"
    : "bg-emerald-950/60 text-emerald-300 border-emerald-800/60";

  return (
    <div className={`flex flex-col gap-1.5 ${className}`}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-gray-400 font-medium">{label}</span>
        <div className="flex items-center gap-2">
          {representedCount !== undefined && totalCount !== undefined && (
            <span className="text-gray-400 text-xs">
              {representedCount}/{totalCount}
            </span>
          )}
          <span className={`px-2 py-0.5 rounded border text-xs font-semibold ${badgeColor}`}>
            {formatPercent(pct, 1)}
          </span>
        </div>
      </div>

      {/* Progress bar track */}
      <div className="w-full h-1.5 rounded-full bg-gray-800 overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {isPartial && showWarningIfPartial && (
        <span className="text-[11px] text-amber-400/90 flex items-center gap-1">
          <span>⚠️</span> Données partielles : certaines institutions n&apos;ont pas publié d&apos;états financiers.
        </span>
      )}
    </div>
  );
}
