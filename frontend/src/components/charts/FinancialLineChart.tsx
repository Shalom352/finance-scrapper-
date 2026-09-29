"use client";

import React, { useState } from "react";
import { formatCompactCurrency, formatPercent } from "@/lib/formatters";

export interface TimeSeriesPoint {
  year: number;
  value: number | null | undefined;
  status?: string;
  unit?: string;
}

interface FinancialLineChartProps {
  data: TimeSeriesPoint[];
  title?: string;
  metricLabel?: string;
  isPercent?: boolean;
  currency?: string;
  height?: number;
  className?: string;
}

export function FinancialLineChart({
  data,
  title,
  metricLabel,
  isPercent = false,
  currency = "XOF",
  height = 240,
  className = "",
}: FinancialLineChartProps) {
  const [hoveredPoint, setHoveredPoint] = useState<TimeSeriesPoint | null>(null);

  // Filter and sort by chronological order
  const sorted = [...data].sort((a, b) => a.year - b.year);
  const validPoints = sorted.filter((d) => d.value !== null && d.value !== undefined && !isNaN(d.value));

  if (validPoints.length === 0) {
    return (
      <div
        className={`flex items-center justify-center border border-gray-800 rounded-2xl bg-gray-900/40 text-gray-400 text-xs p-8 ${className}`}
        style={{ height }}
      >
        <span>Aucun historique disponible pour tracer la courbe</span>
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

  const minYear = sorted[0].year;
  const maxYear = sorted[sorted.length - 1].year;
  const yearSpan = Math.max(maxYear - minYear, 1);

  const getX = (year: number) => paddingX + ((year - minYear) / yearSpan) * innerW;
  const getY = (val: number) => paddingY + innerH - ((val - minVal) / valRange) * innerH;

  // Build segments ensuring gaps are not drawn as zero!
  const segments: string[] = [];
  let currentSegment: { x: number; y: number }[] = [];

  for (let i = 0; i < sorted.length; i++) {
    const pt = sorted[i];
    if (pt.value !== null && pt.value !== undefined && !isNaN(pt.value)) {
      currentSegment.push({ x: getX(pt.year), y: getY(pt.value) });
    } else {
      if (currentSegment.length > 0) {
        segments.push(toSvgPath(currentSegment));
        currentSegment = [];
      }
    }
  }
  if (currentSegment.length > 0) {
    segments.push(toSvgPath(currentSegment));
  }

  function toSvgPath(pts: { x: number; y: number }[]): string {
    if (pts.length === 0) return "";
    if (pts.length === 1) return `M ${pts[0].x} ${pts[0].y} l 0.1 0`;
    return pts.reduce((acc, p, idx) => (idx === 0 ? `M ${p.x} ${p.y}` : `${acc} L ${p.x} ${p.y}`), "");
  }

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
        >
          {/* Horizontal grid lines */}
          <line
            x1={paddingX}
            y1={paddingY}
            x2={chartWidth - paddingX}
            y2={paddingY}
            stroke="#374151"
            strokeDasharray="3 3"
            strokeWidth="0.8"
          />
          <line
            x1={paddingX}
            y1={paddingY + innerH / 2}
            x2={chartWidth - paddingX}
            y2={paddingY + innerH / 2}
            stroke="#374151"
            strokeDasharray="3 3"
            strokeWidth="0.8"
          />
          <line
            x1={paddingX}
            y1={paddingY + innerH}
            x2={chartWidth - paddingX}
            y2={paddingY + innerH}
            stroke="#4b5563"
            strokeWidth="1"
          />

          {/* Y Axis labels */}
          <text x={paddingX - 8} y={paddingY + 4} textAnchor="end" fill="#9ca3af" fontSize="10">
            {isPercent ? formatPercent(maxVal, 1) : formatCompactCurrency(maxVal, currency)}
          </text>
          <text x={paddingX - 8} y={paddingY + innerH} textAnchor="end" fill="#9ca3af" fontSize="10">
            {isPercent ? formatPercent(minVal, 1) : formatCompactCurrency(minVal, currency)}
          </text>

          {/* Chart lines */}
          {segments.map((d, sIdx) => (
            <path
              key={sIdx}
              d={d}
              fill="none"
              stroke="#10b981"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          ))}

          {/* Data points */}
          {validPoints.map((pt, pIdx) => {
            const cx = getX(pt.year);
            const cy = getY(pt.value as number);
            const isHovered = hoveredPoint?.year === pt.year;

            return (
              <g key={pIdx}>
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
                {/* Year label under x axis */}
                <text x={cx} y={paddingY + innerH + 16} textAnchor="middle" fill="#9ca3af" fontSize="10">
                  {pt.year}
                </text>
              </g>
            );
          })}
        </svg>

        {/* Hover Tooltip */}
        {hoveredPoint && (
          <div
            className="absolute top-2 right-2 px-3 py-1.5 rounded-lg border border-emerald-500/40 bg-gray-950/90 text-xs shadow-xl backdrop-blur pointer-events-none"
          >
            <div className="text-gray-400 font-medium mb-0.5">{hoveredPoint.year}</div>
            <div className="text-emerald-400 font-bold text-sm">
              {isPercent
                ? formatPercent(hoveredPoint.value, 2)
                : formatCompactCurrency(hoveredPoint.value, currency)}
            </div>
            {hoveredPoint.status && (
              <div className="text-[10px] text-gray-400 mt-0.5 capitalize">
                Statut : {hoveredPoint.status}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
