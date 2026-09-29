"use client";

import React, { Suspense, useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Institution, PaginatedResponse } from "@/types";
import { getInstitutions } from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useDebouncedValue } from "@/lib/debounce";
import { useQueryParams } from "@/lib/useQueryParams";
import { useLabels } from "@/lib/useLabels";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { StateBadge } from "@/components/common/StatusBadge";
import { Pagination } from "@/components/common/Pagination";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";

const PAGE_SIZE = 15;
const INSTITUTION_STATUSES = ["active", "closed", "in_liquidation", "merged"];

export default function InstitutionsListPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={5} />}>
      <InstitutionsContent />
    </Suspense>
  );
}

function InstitutionsContent() {
  const t = useTranslations("institutions");
  const tStatus = useTranslations("institution_status");
  const tCountries = useTranslations("country_names");
  const labels = useLabels();
  const { get, set } = useQueryParams();

  const page = Math.max(Number(get("page")) || 1, 1);
  const country = get("country");
  const status = get("status");
  const q = get("q");

  // Local input, pushed to the URL (and the API) only once typing pauses.
  const [input, setInput] = useState(q);
  const debounced = useDebouncedValue(input);
  const lastPushed = useRef(debounced);
  useEffect(() => {
    if (debounced === lastPushed.current) return;
    lastPushed.current = debounced;
    if (debounced.trim() !== q) set({ q: debounced.trim(), page: null });
  }, [debounced, q, set]);

  const [result, setResult] = useState<PaginatedResponse<Institution> | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setResult(null);
    setError(false);
    getInstitutions({
      page,
      page_size: PAGE_SIZE,
      country_code: country || undefined,
      status: status || undefined,
      search: q || undefined,
    })
      .then((res) => !cancelled && setResult(res))
      .catch(() => !cancelled && setError(true));
    return () => {
      cancelled = true;
    };
  }, [page, country, status, q, attempt]);

  const filtered = Boolean(q || country || status);

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

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 p-4 rounded-2xl border border-gray-800 bg-gray-900/40">
        <label className="text-[11px] text-gray-400 font-medium">
          {t("search_label")}
          <input
            type="search"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder={t("search_placeholder")}
            className="mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:outline-none"
          />
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("country_label")}
          <select
            value={country}
            onChange={(e) => set({ country: e.target.value, page: null })}
            className="mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">{t("filter_country")}</option>
            {UMOA_COUNTRY_CODES.map((c) => (
              <option key={c} value={c}>
                {tCountries(c)} ({c})
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("status_label")}
          <select
            value={status}
            onChange={(e) => set({ status: e.target.value, page: null })}
            className="mt-1 w-full px-3 py-2 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
          >
            <option value="">{t("filter_status")}</option>
            {INSTITUTION_STATUSES.map((s) => (
              <option key={s} value={s}>
                {tStatus(s)}
              </option>
            ))}
          </select>
        </label>
      </div>

      {error ? (
        <ErrorState onRetry={() => setAttempt((a) => a + 1)} />
      ) : !result ? (
        <TableSkeleton rows={8} cols={5} />
      ) : result.items.length === 0 ? (
        <EmptyState
          title={t("empty_title")}
          description={t("empty")}
          actionText={filtered ? t("reset") : undefined}
          onAction={() => {
            setInput("");
            set({ q: null, country: null, status: null, page: null });
          }}
        />
      ) : (
        <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                  <th className="py-3 px-4">{t("columns.name")}</th>
                  <th className="py-3 px-4">{t("columns.country")}</th>
                  <th className="py-3 px-4">{t("columns.group")}</th>
                  <th className="py-3 px-4">{t("columns.type")}</th>
                  <th className="py-3 px-4 text-center">{t("columns.status")}</th>
                  <th className="py-3 px-4 text-right">{t("columns.actions")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-800/60">
                {result.items.map((inst) => (
                  <tr key={inst.id} className="hover:bg-gray-800/30 transition-colors group">
                    <td className="py-3.5 px-4 font-bold text-gray-200">
                      <Link href={`/institutions/${inst.id}`} className="hover:text-emerald-400 transition-colors block">
                        {inst.name_official}
                      </Link>
                      {inst.name_commercial && (
                        <span className="text-[11px] text-gray-400 block font-normal">{inst.name_commercial}</span>
                      )}
                    </td>
                    <td className="py-3.5 px-4 text-gray-300" data-testid="country-cell">
                      <span className="font-semibold text-emerald-400 mr-1.5">{inst.country?.code ?? MISSING}</span>
                      <span>{inst.country ? labels.country(inst.country) : ""}</span>
                    </td>
                    <td className="py-3.5 px-4 text-gray-400">{inst.banking_group?.name ?? MISSING}</td>
                    <td className="py-3.5 px-4 text-gray-400">{labels.institutionType(inst.institution_type) || MISSING}</td>
                    <td className="py-3.5 px-4 text-center">
                      <StateBadge
                        label={tStatus.has(inst.status) ? tStatus(inst.status) : inst.status}
                        tone={inst.status === "active" ? "ok" : "warn"}
                      />
                    </td>
                    <td className="py-3.5 px-4 text-right">
                      <Link
                        href={`/institutions/${inst.id}`}
                        className="px-3 py-1.5 rounded-lg border border-gray-700 bg-gray-800/60 group-hover:bg-emerald-600 text-gray-300 group-hover:text-white transition-all text-xs font-semibold"
                      >
                        {t("open")}
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <Pagination currentPage={page} pageSize={PAGE_SIZE} total={result.total} onPageChange={(p) => set({ page: p })} />
        </div>
      )}
    </div>
  );
}
