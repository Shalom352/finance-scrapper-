"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { toSegments, type TimeSeriesPoint } from "@/lib/series";

export type { TimeSeriesPoint };

interface FinancialLineChartProps {
  /** Dense yearly series (see buildYearSeries): a missing year is `value: null`. */
  data: TimeSeriesPoint[];
  title?: string;
  metricLabel?: string;
  isPercent?: boolean;
  currency?: string | null;
  height?: number;
  className?: string;
}

export function FinancialLineChart({
  data,
  title,
  metricLabel,
  isPercent = false,
  currency = null,
  height = 240,
  className = "",
}: FinancialLineChartProps) {
  const t = useTranslations("charts");
  const tStatus = useTranslations("status");
  const fmt = useFormatters();
  const [hoveredPoint, setHoveredPoint] = useState<TimeSeriesPoint | null>(null);

  const sorted = [...data].sort((a, b) => a.year - b.year);
  const segments = toSegments(sorted);
  const validPoints = segments.flat();

  const formatValue = (v: number | null | undefined) =>
    isPercent ? fmt.percent(v, 2) : fmt.compact(v, currency);

  if (validPoints.length === 0) {
    return (
      <div
        className={`flex items-center justify-center border border-gray-800 rounded-2xl bg-gray-900/40 text-gray-400 text-xs p-8 ${className}`}
        style={{ height }}
      >
        <span>
          {title ? `${title} — ` : ""}
          {t("no_history")}
        </span>
      </div>
    );
  }

  const values = validPoints.map((p) => p.value as number);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const valRange = maxVal === minVal ? (maxVal === 0 ? 1 : Math.abs(maxVal) * 0.2) : maxVal - minVal;

  const paddingX = 45;
  const paddingY = 30;
  const chartWidth = 550;
  const chartHeight = height;
  const innerW = chartWidth - paddingX * 2;
  const innerH = chartHeight - paddingY * 2;

  // The X domain covers every year of the series, including years without data.
  const minYear = sorted[0].year;
  const maxYear = sorted[sorted.length - 1].year;
  const yearSpan = Math.max(maxYear - minYear, 1);

  const getX = (year: number) => paddingX + ((year - minYear) / yearSpan) * innerW;
  const getY = (val: number) => paddingY + innerH - ((val - minVal) / valRange) * innerH;

  const toPath = (pts: TimeSeriesPoint[]): string =>
    pts.length === 1
      ? `M ${getX(pts[0].year)} ${getY(pts[0].value as number)} l 0.1 0`
      : pts.map((p, i) => `${i === 0 ? "M" : "L"} ${getX(p.year)} ${getY(p.value as number)}`).join(" ");

  const missingYears = sorted.filter((p) => p.value === null || p.value === undefined);

  return (
    <div className={`flex flex-col rounded-2xl border border-gray-800 bg-gray-900/40 p-4 ${className}`}>
      {title && (
        <div className="flex items-center justify-between mb-2">
          <h4 className="text-sm font-semibold text-gray-200">{title}</h4>
          {metricLabel && <span className="text-xs text-gray-400">{metricLabel}</span>}
        </div>
      )}

      <div className="relative w-full overflow-hidden">
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          className="w-full h-auto overflow-visible select-none"
          preserveAspectRatio="none"
          role="img"
          aria-label={title}
        >
          {[0, 0.5].map((f) => (
            <line
              key={f}
              x1={paddingX}
              y1={paddingY + innerH * f}
              x2={chartWidth - paddingX}
              y2={paddingY + innerH * f}
              stroke="#374151"
              strokeDasharray="3 3"
              strokeWidth="0.8"
            />
          ))}
          <line x1={paddingX} y1={paddingY + innerH} x2={chartWidth - paddingX} y2={paddingY + innerH} stroke="#4b5563" strokeWidth="1" />

          <text x={paddingX - 8} y={paddingY + 4} textAnchor="end" fill="#9ca3af" fontSize="10">
            {formatValue(maxVal)}
          </text>
          <text x={paddingX - 8} y={paddingY + innerH} textAnchor="end" fill="#9ca3af" fontSize="10">
            {formatValue(minVal)}
          </text>

          {/* One path per continuous run of years: a missing year is never bridged. */}
          {segments.map((seg, sIdx) => (
            <path
              key={sIdx}
              data-testid="line-segment"
              d={toPath(seg)}
              fill="none"
              stroke="#10b981"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}

          {validPoints.map((pt) => {
            const cx = getX(pt.year);
            const cy = getY(pt.value as number);
            const isHovered = hoveredPoint?.year === pt.year;
            return (
              <g key={pt.year}>
                <circle
                  cx={cx}
                  cy={cy}
                  r={isHovered ? 6 : 4}
                  fill="#065f46"
                  stroke="#34d399"
                  strokeWidth="2"
                  className="cursor-pointer transition-all"
                  onMouseEnter={() => setHoveredPoint(pt)}
                  onMouseLeave={() => setHoveredPoint(null)}
                />
                <text x={cx} y={paddingY + innerH + 16} textAnchor="middle" fill="#9ca3af" fontSize="10">
                  {pt.year}
                </text>
              </g>
            );
          })}

          {/* Years without a usable value: labelled on the axis, marked "—", no point drawn. */}
          {missingYears.map((pt) => (
            <g key={`missing-${pt.year}`} data-testid="missing-year">
              <text x={getX(pt.year)} y={paddingY + innerH + 16} textAnchor="middle" fill="#6b7280" fontSize="10">
                {pt.year}
              </text>
              <text x={getX(pt.year)} y={paddingY + innerH - 6} textAnchor="middle" fill="#6b7280" fontSize="12">
                {MISSING}
              </text>
            </g>
          ))}
        </svg>

        {hoveredPoint && (
          <div className="absolute top-2 right-2 px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-gray-950/90 text-xs shadow-xl backdrop-blur pointer-events-none">
            <div className="text-gray-400 font-medium mb-0.5">{hoveredPoint.year}</div>
            <div className="text-emerald-400 font-bold text-sm">{formatValue(hoveredPoint.value)}</div>
            {hoveredPoint.status && (
              <div className="text-[10px] text-gray-400 mt-0.5">
                {t("status")} : {tStatus.has(hoveredPoint.status) ? tStatus(hoveredPoint.status) : hoveredPoint.status}
              </div>
            )}
          </div>
        )}
      </div>

      {missingYears.length > 0 && (
        <p className="mt-2 text-[11px] text-gray-500">
          {t("missing_years", { years: missingYears.map((p) => p.year).join(", ") })}
        </p>
      )}
    </div>
  );
}
