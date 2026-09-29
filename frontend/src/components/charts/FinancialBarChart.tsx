"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { useFormatters } from "@/lib/useFormatters";

export interface BarChartItem {
  label: string;
  /** null = unavailable: the item is listed with "—" and no bar. */
  value: number | null;
  sublabel?: string;
}

interface FinancialBarChartProps {
  items: BarChartItem[];
  title?: string;
  isPercent?: boolean;
  currency?: string | null;
  className?: string;
}

export function FinancialBarChart({ items, title, isPercent = false, currency = null, className = "" }: FinancialBarChartProps) {
  const t = useTranslations("charts");
  const fmt = useFormatters();
  const known = items.filter((it): it is BarChartItem & { value: number } => it.value !== null);

  if (known.length === 0) {
    return (
      <div className={`p-6 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        {title ? `${title} — ` : ""}
        {t("no_data")}
      </div>
    );
  }

  const maxAbs = Math.max(...known.map((it) => Math.abs(it.value)), Number.EPSILON);

  return (
    <div className={`flex flex-col gap-3 rounded-2xl border border-gray-800 bg-gray-900/40 p-5 ${className}`}>
      {title && <h4 className="text-sm font-semibold text-gray-200">{title}</h4>}

      <div className="space-y-3 pt-1">
        {items.map((item, idx) => {
          const pctWidth = item.value === null ? 0 : (Math.abs(item.value) / maxAbs) * 100;
          const negative = item.value !== null && item.value < 0;

          return (
            <div key={idx} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-300 font-medium truncate max-w-[240px]">
                  {item.label}
                  {item.sublabel && <span className="text-gray-400 font-normal ml-1.5">({item.sublabel})</span>}
                </span>
                <span className={`font-semibold ${negative ? "text-rose-400" : "text-emerald-400"}`}>
                  {isPercent ? fmt.percent(item.value, 1) : fmt.compact(item.value, currency)}
                </span>
              </div>

              <div className="w-full h-2 rounded-full bg-gray-800 overflow-hidden">
                {item.value !== null && (
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${
                      negative ? "bg-rose-500" : "bg-gradient-to-r from-emerald-600 to-teal-500"
                    }`}
                    style={{ width: `${pctWidth.toFixed(1)}%` }}
                  />
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
