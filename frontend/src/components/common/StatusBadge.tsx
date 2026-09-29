"use client";

import React from "react";
import type { DataStatus, RatioStatus } from "@/types";

interface StatusBadgeProps {
  status: DataStatus | RatioStatus | string;
  className?: string;
  size?: "sm" | "md";
}

export function StatusBadge({ status, className = "", size = "md" }: StatusBadgeProps) {
  const norm = (status || "").toLowerCase().trim();

  let label = status;
  let bgClass = "bg-gray-800 text-gray-300 border-gray-700";
  let icon = "•";

  switch (norm) {
    case "verified":
    case "calculated_from_verified":
      label = norm === "calculated_from_verified" ? "Certifié vérifié" : "Vérifié";
      bgClass = "bg-emerald-950/80 text-emerald-300 border-emerald-700/60";
      icon = "✓";
      break;

    case "reviewed":
      label = "Revu";
      bgClass = "bg-blue-950/80 text-blue-300 border-blue-700/60";
      icon = "●";
      break;

    case "calculated":
      label = "Calculé";
      bgClass = "bg-teal-950/80 text-teal-300 border-teal-700/60";
      icon = "ƒ";
      break;

    case "extracted":
      label = "Extrait";
      bgClass = "bg-slate-800/80 text-slate-300 border-slate-700";
      icon = "◒";
      break;

    case "needs_review":
      label = "À réviser";
      bgClass = "bg-amber-950/80 text-amber-300 border-amber-700/60";
      icon = "▲";
      break;

    case "rejected":
      label = "Rejeté";
      bgClass = "bg-rose-950/80 text-rose-300 border-rose-700/60";
      icon = "✕";
      break;

    case "partial":
      label = "Partiel";
      bgClass = "bg-orange-950/80 text-orange-300 border-orange-700/60";
      icon = "◐";
      break;

    case "unavailable":
      label = "N/A";
      bgClass = "bg-gray-900 text-gray-400 border-gray-800";
      icon = "—";
      break;

    default:
      label = status || "Inconnu";
      bgClass = "bg-gray-800 text-gray-300 border-gray-700";
      icon = "•";
      break;
  }

  const sizeClasses = size === "sm" ? "px-2 py-0.5 text-xs" : "px-2.5 py-1 text-xs font-medium";

  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-md border ${bgClass} ${sizeClasses} ${className}`}
      role="status"
      aria-label={`Statut de qualité: ${label}`}
    >
      <span className="font-bold text-[11px] leading-none" aria-hidden="true">
        {icon}
      </span>
      <span>{label}</span>
    </span>
  );
}
