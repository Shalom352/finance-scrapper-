"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { DealDimension, DealListItem, Institution, PaginatedResponse } from "@/types";
import { getDeals, getInstitutionsAll } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { DEAL_PAGE_SIZE, parseDealParams } from "@/lib/deals";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { Pagination } from "@/components/common/Pagination";
import { DealFilters } from "@/components/deals/DealFilters";
import { DealTable } from "@/components/deals/DealTable";
import { DealAnalyticsPanel } from "@/components/deals/DealAnalyticsPanel";

export default function DealsPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={8} />}>
      <DealsContent />
    </Suspense>
  );
}

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };
const DIMENSIONS: DealDimension[] = ["country", "year", "type", "sector", "institution"];

function DealsContent() {
  const t = useTranslations("deals");
  const { get, set, searchParams } = useQueryParams();
  const { query, page } = parseDealParams(get);
  const queryKey = JSON.stringify(query);
  const qs = searchParams.toString();
  const dimParam = get("dim") as DealDimension;
  const dimension: DealDimension = DIMENSIONS.includes(dimParam) ? dimParam : "country";

  const [institutions, setInstitutions] = useState<Institution[]>([]);
  const [institutionsError, setInstitutionsError] = useState(false);
  const [result, setResult] = useState<Load<PaginatedResponse<DealListItem>>>({ status: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    getInstitutionsAll()
      .then(setInstitutions)
      .catch(() => setInstitutionsError(true));
  }, []);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for new filters
    setResult({ status: "loading" });
    getDeals({ ...query, page, page_size: DEAL_PAGE_SIZE })
      .then((data) => !cancelled && setResult({ status: "ready", data }))
      .catch(() => !cancelled && setResult({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queryKey is the stable form of query
  }, [queryKey, page, reload]);

  const change = (updates: Record<string, string | number | null>) => set({ ...updates, page: null });

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
        <p className="text-[11px] text-gray-500 mt-1">{t("import_note")}</p>
      </div>

      <DealFilters query={query} institutions={institutions} onChange={change} />
      {institutionsError && <ErrorState />}

      {result.status === "loading" ? (
        <TableSkeleton rows={8} cols={8} />
      ) : result.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : result.data.items.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="🤝" />
      ) : (
        <section className="space-y-2">
          <p className="text-xs text-gray-400" data-testid="deal-count">{t("count", { total: result.data.total })}</p>
          <DealTable items={result.data.items} hrefFor={(d) => `/deals/${d.id}${qs ? `?${qs}` : ""}`} />
          <Pagination
            currentPage={page}
            pageSize={DEAL_PAGE_SIZE}
            total={result.data.total}
            onPageChange={(p) => set({ page: p > 1 ? p : null })}
          />
        </section>
      )}

      <DealAnalyticsPanel dimension={dimension} onDimension={(d) => set({ dim: d === "country" ? null : d })} />
    </div>
  );
}
