"use client";

import React from "react";

interface EmptyStateProps {
  title?: string;
  description?: string;
  icon?: string;
  actionText?: string;
  onAction?: () => void;
  className?: string;
}

export function EmptyState({
  title = "Aucune donnée disponible",
  description = "Aucune observation ne correspond aux critères sélectionnés.",
  icon = "📂",
  actionText,
  onAction,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center p-12 text-center rounded-2xl border border-dashed border-gray-800 bg-gray-900/30 ${className}`}
    >
      <div className="text-4xl mb-4 opacity-80" aria-hidden="true">
        {icon}
      </div>
      <h3 className="text-lg font-semibold text-gray-200 mb-1">{title}</h3>
      <p className="text-sm text-gray-400 max-w-md mb-6 leading-relaxed">
        {description}
      </p>
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
