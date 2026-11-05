"use client";

import { externalHref } from "@/lib/url";
import React, { Suspense, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { SearchResults, SearchType } from "@/types";
import { searchGlobal } from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useDebouncedValue } from "@/lib/debounce";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { StateBadge, StatusBadge } from "@/components/common/StatusBadge";
import { useDealLabels } from "@/components/deals/DealLabels";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";

/** Minimum length before a query is sent while typing. */
const MIN_QUERY_LENGTH = 2;

export default function SearchPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={6} cols={3} />}>
      <SearchContent />
    </Suspense>
  );
}

function SearchContent() {
  const t = useTranslations("search");
  const tStatus = useTranslations("institution_status");
  const labels = useLabels();
  const dealLabels = useDealLabels();
  const { get, set } = useQueryParams();
  const q = get("q").trim();
  const [input, setInput] = useState(q);
  const debounced = useDebouncedValue(input);
  const previousQuery = useRef(q);

  const [results, setResults] = useState<SearchResults | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(q ? "loading" : "idle");
  const [attempt, setAttempt] = useState(0);
  const [pages, setPages] = useState<Partial<Record<SearchType, number>>>({});
  const [moreError, setMoreError] = useState(false);
  const [loadingMore, setLoadingMore] = useState<Partial<Record<SearchType, boolean>>>({});
  // Only the response of the latest request is applied (out-of-order responses are dropped).
  const requestId = useRef(0);
  const latestQuery = useRef(q);

  // The URL is the source of truth for the displayed search and browser back/forward navigation.
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- synchronize the field to URL navigation
    setInput(q);
  }, [q]);

  // Typing → debounce → URL (?q=) → one API request.
  useEffect(() => {
    if (previousQuery.current !== q) {
      previousQuery.current = q;
      return;
    }
    const next = debounced.trim();
    if (next === q) return;
    if (next.length >= MIN_QUERY_LENGTH) set({ q: next });
    else if (q) set({ q: null });
  }, [debounced, q, set]);


  useEffect(() => {
    latestQuery.current = q;
  }, [q]);

  useEffect(() => {
    const id = ++requestId.current;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset paging state for a new query
    setPages({});
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset paging state for a new query
    setLoadingMore({});
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset paging state for a new query
    setMoreError(false);
    if (!q || q.length < MIN_QUERY_LENGTH) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear results for an empty/short URL query
      setResults(null);
      // eslint-disable-next-line react-hooks/set-state-in-effect -- clear status for a short query
      setStatus("idle");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- loading state for the new query
    setStatus("loading");
    searchGlobal(q)
      .then((res) => {
        if (id !== requestId.current) return;
        setResults(res);
        setStatus("ready");
      })
      .catch(() => {
        if (id !== requestId.current) return;
        setResults(null);
        setStatus("error");
      });
  }, [q, attempt]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const next = input.trim();
    if (next.length < MIN_QUERY_LENGTH) return;
    if (next === q) setAttempt((a) => a + 1);
    else set({ q: next });
  };

  const total = results ? results.total : 0;

  // "Show more": next page of ONE result type, appended (each type has its own real total).
  const loadMore = async (type: SearchType) => {
    if (!results || loadingMore[type]) return;
    const next = (pages[type] ?? 1) + 1;
    const queryAtStart = q;
    const requestAtStart = requestId.current;
    setLoadingMore((current) => ({ ...current, [type]: true }));
    setMoreError(false);
    try {
      const res = await searchGlobal(queryAtStart, { types: type, page: next });
      if (requestAtStart !== requestId.current || queryAtStart !== latestQuery.current) return;
      setPages((current) => ({ ...current, [type]: next }));
      setResults((current) => (current ? { ...current, [type]: [...current[type], ...res[type]] } : current));
    } catch {
      if (requestAtStart === requestId.current && queryAtStart === latestQuery.current) setMoreError(true);
    } finally {
      if (requestAtStart === requestId.current && queryAtStart === latestQuery.current) {
        setLoadingMore((current) => ({ ...current, [type]: false }));
      }
    }
  };
  const more = (type: SearchType) =>
    results && results[type].length < results.totals[type] ? (
      <button type="button" onClick={() => loadMore(type)} data-testid={`search-more-${type}`}
        disabled={Boolean(loadingMore[type])} aria-busy={Boolean(loadingMore[type])}
        className="min-h-9 px-4 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-xs font-semibold text-gray-700 disabled:opacity-50">
        {loadingMore[type] ? t("loading_more") : t("show_more", { shown: results[type].length, total: results.totals[type] })}
      </button>
    ) : null;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-gray-900 tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-500 mt-1">{t("subtitle")}</p>
      </div>

      <form data-guide="search" onSubmit={handleSubmit} className="flex flex-col sm:flex-row gap-3">
        <input
          type="search"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("placeholder")}
          aria-label={t("placeholder")}
          minLength={MIN_QUERY_LENGTH}
          className="flex-1 min-w-0 px-4 py-3 rounded-2xl border border-gray-200 bg-gray-50/80 text-sm text-gray-800 placeholder-gray-400 focus:border-emerald-500 focus:bg-white focus:outline-none transition-all shadow-inner"
        />
        <button
          type="submit"
          disabled={input.trim().length < MIN_QUERY_LENGTH}
          className="px-6 py-3 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors disabled:opacity-50 shadow-md"
        >
          {t("submit")}
        </button>
      </form>
      {input.trim().length > 0 && input.trim().length < MIN_QUERY_LENGTH && (
        <p className="text-xs text-gray-500">{t("query_min_length")}</p>
      )}

      {!q ? null : status === "loading" ? (
        <TableSkeleton rows={6} cols={3} />
      ) : status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : results && total === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty", { query: q })} />
      ) : results ? (
        <div className="space-y-8">
          <p className="text-xs text-gray-500">{t("results_for", { query: q })}</p>
          {moreError && <p className="text-xs text-rose-700">{t("more_error")}</p>}

          {results.institutions.length > 0 && (
            <Section title={t("institutions_found")} count={results.totals.institutions}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {results.institutions.map((inst) => (
                  <Link
                    key={inst.id}
                    href={`/institutions/${inst.id}`}
                    className="p-4 rounded-2xl border border-gray-200 bg-white hover:border-emerald-200 hover:bg-white transition-all flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="min-w-0 font-bold text-gray-800 text-xs break-words">{inst.name_official}</span>
                      <StateBadge
                        label={tStatus.has(inst.status) ? tStatus(inst.status) : inst.status}
                        tone={inst.status === "active" ? "ok" : "warn"}
                      />
                    </div>
                    {inst.name_commercial && <span className="text-[11px] text-emerald-700 block">{inst.name_commercial}</span>}
                    <span className="mt-3 pt-2 border-t border-gray-200 text-[11px] text-gray-500">
                      {inst.country ? labels.country(inst.country) : MISSING}
                    </span>
                  </Link>
                ))}
              </div>
              {more("institutions")}
            </Section>
          )}

          {results.deals.length > 0 && (
            <Section title={t("deals_found")} count={results.totals.deals}>
              <ul className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                {results.deals.map((d) => (
                  <li key={d.id}>
                    <Link href={`/deals/${d.id}`} data-testid="search-deal"
                      className="block p-4 rounded-2xl border border-gray-200 bg-white hover:border-emerald-200 transition-all">
                      <div className="flex items-start justify-between gap-2">
                        <span className="min-w-0 font-bold text-gray-800 text-xs break-words">{d.title}</span>
                        <StatusBadge status={d.status} size="sm" />
                      </div>
                      <span className="mt-2 block text-[11px] text-gray-500">
                        {[dealLabels.type(d.deal_type), d.country_code ? labels.country(null, d.country_code) : null, d.isin]
                          .filter(Boolean).join(" · ")}
                      </span>
                    </Link>
                  </li>
                ))}
              </ul>
              {more("deals")}
            </Section>
          )}

          {results.documents.length > 0 && (
            <Section title={t("documents_found")} count={results.totals.documents}>
              <div className="rounded-2xl border border-gray-200 bg-white overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase">
                      <th className="py-3 px-4">{t("col_title")}</th>
                      <th className="py-3 px-4">{t("col_type")}</th>
                      <th className="py-3 px-4">{t("col_year")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {results.documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                        <td className="py-3 px-4 font-semibold text-gray-800 break-words">
                          {doc.url ? (
                            <a href={externalHref(doc.url)} target="_blank" rel="noopener noreferrer" className="hover:text-emerald-700 hover:underline">
                              {doc.title}
                            </a>
                          ) : doc.title}
                          {doc.institution_id && (
                            <Link href={`/institutions/${doc.institution_id}`} className="block mt-0.5 text-[11px] font-normal text-emerald-700 hover:underline">
                              {t("open_institution")}
                            </Link>
                          )}
                        </td>
                        <td className="py-3 px-4 text-gray-500">{labels.documentType(doc.document_type)}</td>
                        <td className="py-3 px-4 font-mono text-gray-700">{doc.reporting_year ?? doc.period_year ?? MISSING}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              {more("documents")}
            </Section>
          )}

          {results.sources.length > 0 && (
            <Section title={t("sources_found")} count={results.totals.sources}>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.sources.map((s) => (
                  <li key={s.id} className="p-4 rounded-2xl border border-gray-200 bg-white text-xs text-gray-800 space-y-1">
                    <Link href={`/documents?source=${s.id}`} className="font-semibold hover:text-emerald-700 hover:underline">
                      {s.name}
                    </Link>
                    {s.url && (
                      <a href={externalHref(s.url)} target="_blank" rel="noopener noreferrer" className="block text-[11px] text-gray-500 hover:underline break-all">
                        {s.url}
                      </a>
                    )}
                  </li>
                ))}
              </ul>
              {more("sources")}
            </Section>
          )}

          {results.banking_groups.length > 0 && (
            <Section title={t("groups_found")} count={results.totals.banking_groups}>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.banking_groups.map((g) => (
                  <li key={g.id} className="p-4 rounded-2xl border border-gray-200 bg-white text-xs text-gray-800">
                    {g.name}
                  </li>
                ))}
              </ul>
              {more("banking_groups")}
            </Section>
          )}
        </div>
      ) : null}
    </div>
  );
}

function Section({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  return (
    <div className="space-y-3">
      <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wider flex items-center gap-2">
        <span>{title}</span>
        <span className="px-2 py-0.5 rounded-full bg-emerald-50 text-emerald-700 text-xs border border-emerald-200">{count}</span>
      </h3>
      {children}
    </div>
  );
}
