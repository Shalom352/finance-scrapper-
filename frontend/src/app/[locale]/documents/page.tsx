"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { Document, PaginatedResponse } from "@/types";
import { getDocuments, getDocumentYears } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { parseYearParam } from "@/lib/url";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { DocumentsTable } from "@/components/tables/DocumentsTable";

const PAGE_SIZE = 15;
const DOCUMENT_TYPES = ["annual_report", "financial_statement", "regulatory_report", "press_release", "web_page", "other"];

export default function DocumentsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={6} />}>
      <DocumentsContent />
    </Suspense>
  );
}

function DocumentsContent() {
  const t = useTranslations("documents");
  const labels = useLabels();
  const { get, set } = useQueryParams();

  const page = Math.max(Number(get("page")) || 1, 1);
  const type = get("type");
  const year = parseYearParam(get("year"));

  const [result, setResult] = useState<PaginatedResponse<Document> | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [years, setYears] = useState<number[]>([]);

  useEffect(() => {
    getDocumentYears()
      .then(setYears)
      .catch(() => setYears([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setResult(null);
    setError(false);
    getDocuments({ page, page_size: PAGE_SIZE, document_type: type || undefined, period_year: year ?? undefined })
      .then((res) => !cancelled && setResult(res))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [page, type, year, attempt]);

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
          <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
        </div>
        {result && (
          <span className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-900/60 text-xs font-semibold text-gray-300">
            {t("count", { count: result.total })}
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <label className="text-[11px] text-gray-400 font-medium">
          {t("filter_type")}
          <select
            value={type}
            onChange={(e) => set({ type: e.target.value, page: null })}
            className="mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">{t("all_types")}</option>
            {DOCUMENT_TYPES.map((d) => (
              <option key={d} value={d}>
                {labels.documentType(d)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("filter_year")}
          <select
            value={year ?? ""}
            onChange={(e) => set({ year: e.target.value, page: null })}
            className="mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">{t("all_years")}</option>
            {years.map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : !result ? (
        <TableSkeleton rows={8} cols={6} />
      ) : result.items.length === 0 ? (
        <EmptyState
          title={t("empty_title")}
          description={t("empty")}
          actionText={type || year ? t("reset") : undefined}
          onAction={() => set({ type: null, year: null, page: null })}
        />
      ) : (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          <DocumentsTable documents={result.items} emptyText={t("empty")} showInstitution />
          <Pagination currentPage={page} pageSize={PAGE_SIZE} total={result.total} onPageChange={(p) => set({ page: p })} />
        </div>
      )}
    </div>
  );
}
