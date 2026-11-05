"use client";

import { externalHref } from "@/lib/url";
import React, { Suspense, useEffect, useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { DealAnalyticsRow, DealDimension, DealListItem, Institution, PaginatedResponse } from "@/types";
import { getDealSummary, getDeals, getInstitutionsAll } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { DEAL_PAGE_SIZE, parseDealParams } from "@/lib/deals";
import { amountValue, formatCompactCurrency, MISSING } from "@/lib/formatters";
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

const RECENT_SOURCES: { name: string; descKey: string; url: string }[] = [
  {
    name: "BCEAO",
    descKey: "bceao",
    url: "https://www.bceao.int",
  },
  {
    name: "BRVM",
    descKey: "brvm",
    url: "https://www.brvm.org",
  },
  {
    name: "UMOA-Titres",
    descKey: "umoa_titres",
    url: "https://www.umoatitres.org",
  },
  {
    name: "IFC",
    descKey: "ifc",
    url: "https://www.ifc.org",
  },
];

function DealsContent() {
  const t = useTranslations("deals");
  const locale = useLocale();
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
  const [summary, setSummary] = useState<Load<DealAnalyticsRow>>({ status: "loading" });
  const [showImportNotice, setShowImportNotice] = useState(false);

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

  // Tiles: ALL the deals matching the filters (server-side), never only the displayed page.
  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for new filters
    setSummary({ status: "loading" });
    getDealSummary(query)
      .then((data) => !cancelled && setSummary({ status: "ready", data }))
      .catch(() => !cancelled && setSummary({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- queryKey is the stable form of query
  }, [queryKey, reload]);

  const change = (updates: Record<string, string | number | null>) => set({ ...updates, page: null });

  // KPI values from the server summary. Amounts: reviewed / verified deals, one total per currency
  // (figure x scale of its unit), currencies never added together.
  const ready = summary.status === "ready" ? summary.data : null;
  const totalDeals = ready ? ready.deals : null;
  const dealsToReview = ready ? ready.by_status.needs_review : null; // every status is counted by the API, 0 included
  const volumes: [string, number][] = [];
  for (const a of ready?.amounts ?? []) {
    const value = amountValue(a.total, a.unit);
    if (value === null) continue;
    const i = volumes.findIndex(([c]) => c === a.currency);
    if (i >= 0) volumes[i][1] += value;
    else volumes.push([a.currency, value]);
  }

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Header with Title and "Importer un deal" action button */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-gray-900 tracking-tight">{t("title")}</h1>
          <p className="text-xs text-gray-500 mt-1">{t("subtitle")}</p>
        </div>

        <button
          type="button"
          onClick={() => setShowImportNotice(!showImportNotice)}
          className="inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-[#0B6E4F] hover:bg-[#095940] text-white text-xs font-semibold shadow-xs transition-colors shrink-0"
        >
          <span className="text-sm font-bold">+</span>
          <span>{t("import_button")}</span>
        </button>
      </div>

      {showImportNotice && (
        <div className="p-4 rounded-2xl border border-emerald-200 bg-emerald-50 text-xs text-emerald-900 animate-fade-in">
          <p className="font-semibold mb-1">ℹ️ {t("import_button")}</p>
          <p className="leading-relaxed">{t("import_note")}</p>
        </div>
      )}

      {/* Filter Row */}
      <DealFilters query={query} institutions={institutions} onChange={change} />
      {institutionsError && <ErrorState />}

      {/* KPI Summary Cards from Mockup */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs">
          <span className="text-xs text-gray-500 font-medium">{t("kpi_deals_tracked")}</span>
          <div className="text-xl sm:text-2xl font-black text-gray-900 mt-2 break-words">
            {totalDeals !== null ? totalDeals : MISSING}
          </div>
        </div>

        <div className="p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs">
          <span className="text-xs text-gray-500 font-medium">{t("kpi_published_amount")}</span>
          <div className="text-xl sm:text-2xl font-black text-gray-900 mt-2 break-words">
            {volumes.length === 0
              ? MISSING
              : volumes.map(([cur, value]) => (
                  <div key={cur} data-testid="deal-volume">{formatCompactCurrency(value, cur, locale)}</div>
                ))}
          </div>
        </div>

        <div className="p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs">
          <span className="text-xs text-gray-500 font-medium">{t("kpi_to_review")}</span>
          <div className="text-xl sm:text-2xl font-black text-gray-900 mt-2 break-words">
            {dealsToReview !== null ? dealsToReview : MISSING}
          </div>
        </div>
      </div>

      {/* Table Results */}
      {result.status === "loading" ? (
        <TableSkeleton rows={8} cols={8} />
      ) : result.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : result.data.items.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="🤝" />
      ) : (
        <section className="space-y-3">
          <p className="text-xs text-gray-500 font-medium" data-testid="deal-count">
            {t("count", { total: result.data.total })}
          </p>
          <DealTable items={result.data.items} hrefFor={(d) => `/deals/${d.id}${qs ? `?${qs}` : ""}`} />
          <Pagination
            currentPage={page}
            pageSize={DEAL_PAGE_SIZE}
            total={result.data.total}
            onPageChange={(p) => set({ page: p > 1 ? p : null })}
          />
        </section>
      )}

      {/* Descriptive Analytics Panel */}
      <DealAnalyticsPanel dimension={dimension} onDimension={(d) => set({ dim: d === "country" ? null : d })} />

      {/* Dernières sources Section from Mockup */}
      <section className="space-y-3 pt-4">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-bold text-gray-900 tracking-tight">{t("sources_title")}</h2>
          <Link
            href="/documents"
            className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 hover:underline flex items-center gap-1"
          >
            <span>{t("sources_link")}</span>
            <span>→</span>
          </Link>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {RECENT_SOURCES.map((source) => (
            <a
              key={source.name}
              href={externalHref(source.url)}
              target="_blank"
              rel="noopener noreferrer"
              className="group p-4 rounded-2xl border border-gray-200/90 bg-white hover:border-emerald-200 hover:shadow-sm transition-all flex flex-col justify-between"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2">
                  <div className="w-8 h-8 rounded-lg bg-gray-50 group-hover:bg-emerald-50 flex items-center justify-center text-gray-600 group-hover:text-emerald-700 transition-colors">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                    </svg>
                  </div>
                  <span className="font-bold text-xs text-gray-900 group-hover:text-emerald-800 transition-colors">
                    {source.name}
                  </span>
                </div>
                <svg className="w-3.5 h-3.5 text-gray-500 group-hover:text-emerald-600 transition-colors" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                </svg>
              </div>
              <p className="text-[11px] text-gray-500 mt-2 line-clamp-2 leading-relaxed">
                {t(`recent_sources_desc.${source.descKey}`)}
              </p>
            </a>
          ))}
        </div>
      </section>
    </div>
  );
}
