"use client";

import React from "react";
import { useTranslations } from "next-intl";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: string;
  actionText?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({ title, description, icon = "📂", actionText, onAction, className = "" }: EmptyStateProps) {
  const t = useTranslations("common");

  return (
    <div
      className={`flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-gray-800 bg-gray-900/30 ${className}`}
    >
      <div className="text-4xl mb-4 opacity-80" aria-hidden="true">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-gray-200 mb-1">{title ?? t("empty_title")}</h3>
      <p className="text-sm text-gray-400 max-w-md mb-6 leading-relaxed">{description ?? t("empty")}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold shadow-md transition-colors"
        >
          {actionText}
        </button>
      )}
    </div>
  );
}

/** Explicit error state: an API failure is never presented as "no data". */
export function ErrorState({ onRetry, className = "" }: { onRetry?: () => void; className?: string }) {
  const t = useTranslations("common");

  return (
    <div
      role="alert"
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl border border-rose-800/60 bg-rose-950/30 text-sm text-rose-200 ${className}`}
    >
      <span>{t("error")}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="px-3 py-1.5 rounded-lg border border-rose-700 bg-rose-900/40 hover:bg-rose-800/60 text-xs font-semibold"
        >
          {t("retry")}
        </button>
      )}
    </div>
  );
}
