"use client";

import React from "react";
import { useTranslations } from "next-intl";

interface StatusBadgeProps {
  status: string | null | undefined;
  className?: string;
  size?: "sm" | "md";
}

const STYLES: Record<string, { cls: string; icon: string }> = {
  verified: { cls: "bg-emerald-950/80 text-emerald-300 border-emerald-700/60", icon: "✓" },
  calculated_from_verified: { cls: "bg-emerald-950/80 text-emerald-300 border-emerald-700/60", icon: "✓" },
  reviewed: { cls: "bg-blue-950/80 text-blue-300 border-blue-700/60", icon: "●" },
  calculated: { cls: "bg-teal-950/80 text-teal-300 border-teal-700/60", icon: "ƒ" },
  extracted: { cls: "bg-slate-800/80 text-slate-300 border-slate-700", icon: "◒" },
  needs_review: { cls: "bg-amber-950/80 text-amber-300 border-amber-700/60", icon: "▲" },
  conflict: { cls: "bg-amber-950/80 text-amber-300 border-amber-700/60", icon: "≠" },
  partial: { cls: "bg-orange-950/80 text-orange-300 border-orange-700/60", icon: "◐" },
  rejected: { cls: "bg-rose-950/80 text-rose-300 border-rose-700/60", icon: "✕" },
  unavailable: { cls: "bg-gray-900 text-gray-400 border-gray-800", icon: "—" },
};

const DEFAULT_STYLE = { cls: "bg-gray-800 text-gray-300 border-gray-700", icon: "•" };

/** Data-quality status badge. Only data/ratio statuses belong here — not document or institution states. */
export function StatusBadge({ status, className = "", size = "md" }: StatusBadgeProps) {
  const t = useTranslations("status");
  const norm = (status ?? "").toLowerCase().trim();
  const style = STYLES[norm] ?? DEFAULT_STYLE;
  const label = norm && t.has(norm) ? t(norm) : status || t("unknown");
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs font-medium";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border ${style.cls} ${sizeClasses} ${className}`}
      aria-label={t("aria", { label })}
    >
      <span className="font-bold text-[11px] leading-none" aria-hidden="true">
        {style.icon}
      </span>
      <span>{label}</span>
    </span>
  );
}

/** Neutral badge for non-quality states (document download/extraction, institution status). */
export function StateBadge({ label, tone = "neutral" }: { label: string; tone?: "ok" | "warn" | "error" | "neutral" }) {
  const cls = {
    ok: "bg-emerald-950/60 text-emerald-300 border-emerald-800/60",
    warn: "bg-amber-950/60 text-amber-300 border-amber-800/60",
    error: "bg-rose-950/60 text-rose-300 border-rose-800/60",
    neutral: "bg-gray-800 text-gray-300 border-gray-700",
  }[tone];
  return <span className={`inline-flex items-center rounded-md border px-2 py-0.5 text-xs ${cls}`}>{label}</span>;
}
