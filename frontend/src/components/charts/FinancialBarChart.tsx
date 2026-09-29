"use client";

import React from "react";
import { formatCompactCurrency, formatPercent } from "@/lib/formatters";

export interface BarChartItem {
  label: string;
  value: number;
  sublabel?: string;
  color?: string;
}

interface FinancialBarChartProps {
  items: BarChartItem[];
  title?: string;
  isPercent?: boolean;
  currency?: string;
  className?: string;
}

export function FinancialBarChart({
  items,
  title,
  isPercent = false,
  currency = "XOF",
  className = "",
}: FinancialBarChartProps) {
  if (!items || items.length === 0) {
    return (
      <div className={`p-6 text-center text-xs text-gray-500 rounded-2xl border border-gray-800 ${className}`}>
        Aucune donnée à afficher dans le graphique
      </div>
    );
  }

  const maxVal = Math.max(...items.map((it) => it.value), 0.0001);

  return (
    <div className={`flex flex-col gap-3 rounded-2xl border border-gray-800 bg-gray-900/40 p-5 ${className}`}>
      {title && <h4 className="text-sm font-semibold text-gray-200">{title}</h4>}

      <div className="space-y-3 pt-1">
        {items.map((item, idx) => {
          const ratio = Math.min(Math.max(item.value / maxVal, 0), 1);
          const pctWidth = (ratio * 100).toFixed(1);

          return (
            <div key={idx} className="flex flex-col gap-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-gray-300 font-medium truncate max-w-[240px]">
                  {item.label}
                  {item.sublabel && <span className="text-gray-400 font-normal ml-1.5">({item.sublabel})</span>}
                </span>
                <span className="font-semibold text-emerald-400">
                  {isPercent ? formatPercent(item.value, 1) : formatCompactCurrency(item.value, currency)}
                </span>
              </div>

              {/* Bar track */}
              <div className="w-full h-2 rounded-full bg-gray-800 overflow-hidden">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-teal-500 transition-all duration-500"
                  style={{ width: `${pctWidth}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
