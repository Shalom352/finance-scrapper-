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
    <div className={`flex flex-wrap items-center justify-between gap-2 px-4 py-3 border-t border-gray-200 text-sm ${className}`}>
      <div className="text-gray-500 text-xs sm:text-sm">{t("range", { start, end, total })}</div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={!hasPrev}
          className="min-h-10 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 text-xs font-medium hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
        >
          {t("previous")}
        </button>

        <span className="px-2 text-xs text-gray-500 font-medium">
          {currentPage} / {totalPages}
        </span>

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={!hasNext}
          className="min-h-10 px-3 py-1.5 rounded-lg border border-gray-200 bg-white text-gray-700 text-xs font-medium hover:bg-gray-50 disabled:opacity-40 disabled:cursor-not-allowed transition-colors shadow-xs"
        >
          {t("next")}
        </button>
      </div>
    </div>
  );
}
