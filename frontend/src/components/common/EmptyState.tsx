"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: string;
  actionText?: string;
  onAction?: () => void;
  /** A way back (list page) when the requested item does not exist. */
  backHref?: string;
  backText?: string;
  className?: string;
}

export function EmptyState({
  title, description, icon = "📂", actionText, onAction, backHref, backText, className = "",
}: EmptyStateProps) {
  const t = useTranslations("common");

  return (
    <div
      className={`flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-gray-200 bg-white shadow-xs ${className}`}
    >
      <div className="text-4xl mb-4 opacity-80" aria-hidden="true">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-gray-800 mb-1">{title ?? t("empty_title")}</h3>
      <p className="text-sm text-gray-500 max-w-md mb-6 leading-relaxed">{description ?? t("empty")}</p>
      {actionText && onAction && (
        <button
          onClick={onAction}
          className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold shadow-xs transition-colors"
        >
          {actionText}
        </button>
      )}
      {backHref && backText && (
        <Link href={backHref} className="text-xs font-semibold text-emerald-700 hover:text-emerald-800" data-testid="empty-back">
          ← {backText}
        </Link>
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
      className={`flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-4 rounded-2xl border border-rose-200 bg-rose-50 text-sm text-rose-800 shadow-xs ${className}`}
    >
      <span>{t("error")}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className="min-h-10 px-3 py-1.5 rounded-lg border border-rose-300 bg-white hover:bg-rose-100 text-xs font-semibold text-rose-800 shadow-xs"
        >
          {t("retry")}
        </button>
      )}
    </div>
  );
}
