"use client";

import React from "react";
import { useTranslations } from "next-intl";

interface PaginationProps {
  currentPage: number;
  pageSize: number;
  total: number;
  onPageChange: (newPage: number) => void;
  className?: string;
}

export function Pagination({ currentPage, pageSize, total, onPageChange, className = "" }: PaginationProps) {
  const t = useTranslations("common.pagination");
  const totalPages = Math.max(Math.ceil(total / pageSize), 1);
  const hasPrev = currentPage > 1;
  const hasNext = currentPage < totalPages;

  const start = total === 0 ? 0 : (currentPage - 1) * pageSize + 1;
  const end = Math.min(currentPage * pageSize, total);

  return (
    <div className={`flex items-center justify-between px-4 py-3 border-t border-gray-800 text-sm ${className}`}>
      <div className="text-gray-400 text-xs sm:text-sm">{t("range", { start, end, total })}</div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!hasPrev}
          className="px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900 text-gray-300 text-xs font-medium hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {t("previous")}
        </button>

        <span className="px-2 text-xs text-gray-400 font-medium">
          {currentPage} / {totalPages}
        </span>

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!hasNext}
          className="px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-900 text-gray-300 text-xs font-medium hover:bg-gray-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          {t("next")}
        </button>
      </div>
    </div>
  );
}
