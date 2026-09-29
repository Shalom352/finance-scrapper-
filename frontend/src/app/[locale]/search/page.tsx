"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { SearchResults } from "@/types";
import { searchGlobal } from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useDebouncedValue } from "@/lib/debounce";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { StateBadge } from "@/components/common/StatusBadge";
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
  const { get, set } = useQueryParams();
  const q = get("q").trim();

  // Typing → debounce → URL (?q=) → one API request.
  const [input, setInput] = useState(q);
  const debounced = useDebouncedValue(input);
  const lastPushed = useRef(debounced);
  useEffect(() => {
    if (debounced === lastPushed.current) return;
    lastPushed.current = debounced;
    const next = debounced.trim();
    if (next.length >= MIN_QUERY_LENGTH && next !== q) set({ q: next });
  }, [debounced, q, set]);

  const [results, setResults] = useState<SearchResults | null>(null);
  const [status, setStatus] = useState<"idle" | "loading" | "ready" | "error">(q ? "loading" : "idle");
  const [attempt, setAttempt] = useState(0);
  // Only the response of the latest request is applied (out-of-order responses are dropped).
  const requestId = useRef(0);

  useEffect(() => {
    if (!q) return;
    const id = ++requestId.current;
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
    if (!next) return;
    lastPushed.current = input;
    if (next === q) setAttempt((a) => a + 1);
    else set({ q: next });
  };

  const total = results
    ? results.institutions.length + results.documents.length + results.sources.length + results.banking_groups.length
    : 0;

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <form onSubmit={handleSubmit} className="flex gap-3">
        <input
          type="search"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("placeholder")}
          aria-label={t("placeholder")}
          className="flex-1 px-4 py-3 rounded-2xl border border-gray-800 bg-gray-900/60 text-sm text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:bg-gray-900 focus:outline-none transition-all shadow-inner"
        />
        <button
          type="submit"
          disabled={!input.trim()}
          className="px-6 py-3 rounded-2xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold transition-colors disabled:opacity-50 shadow-md"
        >
          {t("submit")}
        </button>
      </form>

      {!q ? null : status === "loading" ? (
        <TableSkeleton rows={6} cols={3} />
      ) : status === "error" ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : results && total === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty", { query: q })} />
      ) : results ? (
        <div className="space-y-8">
          <p className="text-xs text-gray-400">{t("results_for", { query: q })}</p>

          {results.institutions.length > 0 && (
            <Section title={t("institutions_found")} count={results.institutions.length}>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {results.institutions.map((inst) => (
                  <Link
                    key={inst.id}
                    href={`/institutions/${inst.id}`}
                    className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 hover:border-emerald-500/50 hover:bg-gray-900 transition-all flex flex-col justify-between"
                  >
                    <div className="flex items-center justify-between gap-2 mb-1.5">
                      <span className="font-bold text-gray-200 text-xs truncate">{inst.name_official}</span>
                      <StateBadge
                        label={tStatus.has(inst.status) ? tStatus(inst.status) : inst.status}
                        tone={inst.status === "active" ? "ok" : "warn"}
                      />
                    </div>
                    {inst.name_commercial && <span className="text-[11px] text-emerald-400 block">{inst.name_commercial}</span>}
                    <span className="mt-3 pt-2 border-t border-gray-800 text-[11px] text-gray-500">
                      {inst.country ? labels.country(inst.country) : MISSING}
                    </span>
                  </Link>
                ))}
              </div>
            </Section>
          )}

          {results.documents.length > 0 && (
            <Section title={t("documents_found")} count={results.documents.length}>
              <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase">
                      <th className="py-3 px-4">{t("col_title")}</th>
                      <th className="py-3 px-4">{t("col_type")}</th>
                      <th className="py-3 px-4">{t("col_year")}</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-800/60">
                    {results.documents.map((doc) => (
                      <tr key={doc.id} className="hover:bg-gray-800/30 transition-colors">
                        <td className="py-3 px-4 font-semibold text-gray-200">{doc.title}</td>
                        <td className="py-3 px-4 text-gray-400">{labels.documentType(doc.document_type)}</td>
                        <td className="py-3 px-4 font-mono text-gray-300">{doc.period_year ?? MISSING}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>
          )}

          {results.sources.length > 0 && (
            <Section title={t("sources_found")} count={results.sources.length}>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.sources.map((s) => (
                  <li key={s.id} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs text-gray-200">
                    {s.name}
                  </li>
                ))}
              </ul>
            </Section>
          )}

          {results.banking_groups.length > 0 && (
            <Section title={t("groups_found")} count={results.banking_groups.length}>
              <ul className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {results.banking_groups.map((g) => (
                  <li key={g.id} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs text-gray-200">
                    {g.name}
                  </li>
                ))}
              </ul>
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
      <h3 className="text-sm font-bold text-white uppercase tracking-wider flex items-center gap-2">
        <span>{title}</span>
        <span className="px-2 py-0.5 rounded-full bg-emerald-950 text-emerald-400 text-xs border border-emerald-800">{count}</span>
      </h3>
      {children}
    </div>
  );
}
