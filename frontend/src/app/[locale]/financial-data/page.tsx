"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { FinancialDataExplorerItem, FinancialDataFacets, Institution, PaginatedResponse } from "@/types";
import { getFinancialDataExplorer, getFinancialDataFacets, getInstitutionsAll, type ExplorerSort } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { EXPLORER_PAGE_SIZE, parseExplorerParams } from "@/lib/financialData";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { Pagination } from "@/components/common/Pagination";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { ExplorerFilters } from "@/components/financial-data/ExplorerFilters";
import { ExplorerTable } from "@/components/financial-data/ExplorerTable";
import { ExportButton } from "@/components/financial-data/ExportButton";

export default function FinancialDataPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={8} />}>
      <FinancialDataContent />
    </Suspense>
  );
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

function FinancialDataContent() {
  const t = useTranslations("data_explorer");
  const { get, set } = useQueryParams();
  const { query, page, institutionIds } = parseExplorerParams(get);
  const queryKey = JSON.stringify(query);

  const [facets, setFacets] = useState<FinancialDataFacets | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [result, setResult] = useState<Load<PaginatedResponse<FinancialDataExplorerItem>>>({ status: "loading" });
  const [provenance, setProvenance] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    getFinancialDataFacets()
      .then(setFacets)
      .catch(() => setFacets(null));
    getInstitutionsAll()
      .then(setInstitutions)
      .catch(() => setInstitutions([]));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for new filters
    setResult({ status: "loading" });
    getFinancialDataExplorer({ ...query, page, page_size: EXPLORER_PAGE_SIZE })
      .then((data) => !cancelled && setResult({ status: "ready", data }))
      .catch(() => !cancelled && setResult({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queryKey is the stable form of query
  }, [queryKey, page, reload]);

  /** Any filter change goes back to page 1. */
  const change = (updates: Record<string, string | number | null>) => set({ ...updates, page: null });
  const onSort = (key: ExplorerSort) =>
    change({ sort: key, order: query.sort === key && query.order === "asc" ? "desc" : "asc" });

  const total = result.status === "ready" ? result.data.total : null;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
          <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
        </div>
        <ExportButton key={queryKey} query={query} total={total} />
      </div>

      <ExplorerFilters
        query={query}
        institutionIds={institutionIds}
        facets={facets}
        institutions={institutions}
        onChange={change}
      />

      <div className="text-[11px] text-gray-500 space-y-1">
        <p>{t("note_rows")}</p>
        {query.sort === "value" && <p data-testid="value-sort-note">{t("note_value_sort")}</p>}
      </div>

      {result.status === "loading" ? (
        <TableSkeleton rows={8} cols={8} />
      ) : result.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : result.data.items.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="📂" />
      ) : (
        <section className="space-y-2">
          <p className="text-xs text-gray-400" data-testid="explorer-count">
            {t("count", { total: result.data.total })}
          </p>
          <ExplorerTable
            items={result.data.items}
            sort={query.sort}
            order={query.order ?? "asc"}
            onSort={onSort}
            onProvenance={setProvenance}
          />
          <Pagination
            currentPage={page}
            pageSize={EXPLORER_PAGE_SIZE}
            total={result.data.total}
            onPageChange={(p) => set({ page: p > 1 ? p : null })}
          />
        </section>
      )}

      {provenance && <ProvenancePanel dataId={provenance} onClose={() => setProvenance(null)} />}
    </div>
  );
}
