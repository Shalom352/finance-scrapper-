"use client";

import React from "react";
import { useTranslations } from "next-intl";

interface StatusBadgeProps {
  status: string | null | undefined;
  className?: string;
  size?: "sm" | "md";
}

const STYLES: Record<string, { cls: string; icon: string }> = {
  verified: { cls: "bg-emerald-50 text-emerald-700 border-emerald-200/80", icon: "✓" },
  calculated_from_verified: { cls: "bg-emerald-50 text-emerald-700 border-emerald-200/80", icon: "✓" },
  reviewed: { cls: "bg-blue-50 text-blue-700 border-blue-200/80", icon: "●" },
  calculated: { cls: "bg-teal-50 text-teal-700 border-teal-200/80", icon: "ƒ" },
  extracted: { cls: "bg-slate-100 text-slate-700 border-slate-200", icon: "◒" },
  needs_review: { cls: "bg-amber-50 text-amber-700 border-amber-200/80", icon: "▲" },
  conflict: { cls: "bg-amber-50 text-amber-700 border-amber-200/80", icon: "≠" },
  partial: { cls: "bg-orange-50 text-orange-700 border-orange-200/80", icon: "◐" },
  rejected: { cls: "bg-rose-50 text-rose-700 border-rose-200/80", icon: "✕" },
  unavailable: { cls: "bg-gray-100 text-gray-500 border-gray-200", icon: "—" },
};

const DEFAULT_STYLE = { cls: "bg-gray-100 text-gray-700 border-gray-200", icon: "•" };

/** Data-quality status badge. Only data/ratio statuses belong here — not document or institution states. */
export function StatusBadge({ status, className = "", size = "md" }: StatusBadgeProps) {
  const t = useTranslations("status");
  const norm = (status ?? "").toLowerCase().trim();
  const style = STYLES[norm] ?? DEFAULT_STYLE;
  const label = norm && t.has(norm) ? t(norm) : status || t("unknown");
  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs font-medium rounded-full" : "px-2.5 py-1 text-xs font-medium rounded-full";

  return (
    <span
      className={`inline-flex items-center gap-1.5 border ${style.cls} ${sizeClasses} ${className}`}
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
    ok: "bg-emerald-50 text-emerald-700 border-emerald-200/80",
    warn: "bg-amber-50 text-amber-700 border-amber-200/80",
    error: "bg-rose-50 text-rose-700 border-rose-200/80",
    neutral: "bg-gray-100 text-gray-700 border-gray-200",
  }[tone];
  return <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium ${cls}`}>{label}</span>;
}
