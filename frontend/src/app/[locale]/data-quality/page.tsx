"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type {
  FinancialDataExplorerItem,
  FinancialDataFacets,
  Institution,
  PaginatedResponse,
  ReviewCenterCounts,
} from "@/types";
import {
  getDataQualityCounts,
  getDataQualityQueue,
  getFinancialDataFacets,
  getInstitutionsAll,
  type ExplorerSort,
} from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { EXPLORER_PAGE_SIZE, parseExplorerParams } from "@/lib/financialData";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { Pagination } from "@/components/common/Pagination";
import { ProvenancePanel } from "@/components/provenance/ProvenancePanel";
import { ExplorerFilters } from "@/components/financial-data/ExplorerFilters";
import { ExplorerTable } from "@/components/financial-data/ExplorerTable";
import { SummaryCounts } from "@/components/data-quality/SummaryCounts";

export default function DataQualityPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={8} />}>
      <DataQualityContent />
    </Suspense>
  );
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

function DataQualityContent() {
  const t = useTranslations("data_quality");
  const { get, set, searchParams } = useQueryParams();
  // Review queue: period type and scope stay open (each row shows its own; nothing is merged).
  const { query, page, institutionIds } = parseExplorerParams(get, { dimensionDefaults: false });
  const queryKey = JSON.stringify(query);
  const qs = searchParams.toString();

  const [counts, setCounts] = useState<ReviewCenterCounts | null>(null);
  const [facets, setFacets] = useState<FinancialDataFacets | null>(null);
  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [result, setResult] = useState<Load<PaginatedResponse<FinancialDataExplorerItem>>>({ status: "loading" });
  const [provenance, setProvenance] = useState<string | null>(null);
  const [reload, setReload] = useState(0);

  useEffect(() => {
    getDataQualityCounts()
      .then(setCounts)
      .catch(() => setCounts(null));
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
    getDataQualityQueue({ ...query, page, page_size: EXPLORER_PAGE_SIZE })
      .then((data) => !cancelled && setResult({ status: "ready", data }))
      .catch(() => !cancelled && setResult({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queryKey is the stable form of query
  }, [queryKey, page, reload]);

  const change = (updates: Record<string, string | number | null>) => set({ ...updates, page: null });
  const onSort = (key: ExplorerSort) =>
    change({ sort: key, order: query.sort === key && query.order === "asc" ? "desc" : "asc" });

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      {counts && <SummaryCounts counts={counts} />}

      <ExplorerFilters
        query={query}
        institutionIds={institutionIds}
        facets={facets}
        institutions={institutions}
        onChange={change}
        statusAllLabel={t("status_to_decide")}
        openDimensions
      />

      <div className="text-[11px] text-gray-500 space-y-1">
        <p>{t("note")}</p>
        <p>{t("auth_note")}</p>
      </div>

      {result.status === "loading" ? (
        <TableSkeleton rows={8} cols={8} />
      ) : result.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : result.data.items.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="✅" />
      ) : (
        <section className="space-y-2">
          <p className="text-xs text-gray-400" data-testid="dq-queue-count">
            {t("count", { total: result.data.total })}
          </p>
          <ExplorerTable
            items={result.data.items}
            sort={query.sort}
            order={query.order ?? "asc"}
            onSort={onSort}
            onProvenance={setProvenance}
            rowLink={{
              label: t("open"),
              // The queue filters travel with the link so "back" restores them.
              href: (row) => `/data-quality/${row.id}${qs ? `?${qs}` : ""}`,
            }}
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
