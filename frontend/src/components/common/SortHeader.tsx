"use client";

import React from "react";
import type { SortDir } from "@/lib/useSort";

interface SortHeaderProps {
  label: React.ReactNode;
  active: boolean;
  dir: SortDir;
  onClick: () => void;
  className?: string;
  testId?: string;
}

/** Sortable column header: a real button (keyboard, touch) with aria-sort on the cell. */
export function SortHeader({ label, active, dir, onClick, className = "", testId }: SortHeaderProps) {
  const right = className.includes("text-right");
  return (
    <th className={className} aria-sort={active ? (dir === "asc" ? "ascending" : "descending") : "none"}>
      <button
        type="button"
        onClick={onClick}
        className={`inline-flex items-center gap-1 min-h-8 -my-1 font-[inherit] uppercase tracking-[inherit] hover:text-gray-800 ${
          right ? "flex-row-reverse" : ""
        } ${active ? "text-emerald-700" : ""}`}
        data-testid={testId}
      >
        <span>{label}</span>
        <span aria-hidden="true" className="text-[10px]">{active ? (dir === "asc" ? "▲" : "▼") : "↕"}</span>
      </button>
    </th>
  );
}

/** Compact sort selector for card/list layouts (no table header to click). */
export function SortSelect<K extends string>({
  options,
  sortKey,
  dir,
  onChange,
  label,
  ascLabel,
  descLabel,
  testId,
}: {
  options: { key: K; label: string }[];
  sortKey: K;
  dir: SortDir;
  onChange: (key: K, dir: SortDir) => void;
  label: string;
  ascLabel: string;
  descLabel: string;
  testId?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500" data-testid={testId}>
      <span>{label}</span>
      <select
        className="min-h-9 rounded-lg border border-gray-200 bg-white px-2 text-gray-800"
        value={sortKey}
        onChange={(e) => onChange(e.target.value as K, dir)}
        aria-label={label}
      >
        {options.map((o) => (
          <option key={o.key} value={o.key}>{o.label}</option>
        ))}
      </select>
      <button
        type="button"
        onClick={() => onChange(sortKey, dir === "asc" ? "desc" : "asc")}
        className="min-h-9 rounded-lg border border-gray-200 bg-white px-3 text-gray-700 hover:bg-gray-50"
      >
        {dir === "asc" ? `▲ ${ascLabel}` : `▼ ${descLabel}`}
      </button>
    </div>
  );
}
