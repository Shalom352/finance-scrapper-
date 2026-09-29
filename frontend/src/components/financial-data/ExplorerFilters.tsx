"use client";

import React, { useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import type { FinancialDataFacets, Institution } from "@/types";
import type { FinancialDataExplorerQuery } from "@/lib/api";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { displayCurrency, MISSING } from "@/lib/formatters";
import { useLabels } from "@/lib/useLabels";
import { MAX_SELECTED_INSTITUTIONS } from "@/lib/financialData";
import { selectCls } from "@/components/rankings/IndicatorSelect";

type Updates = Record<string, string | number | null>;

interface ExplorerFiltersProps {
  query: FinancialDataExplorerQuery;
  institutionIds: string[];
  facets: FinancialDataFacets | null;
  institutions: Institution[];
  /** Writes URL params (page reset is handled by the caller). */
  onChange: (updates: Updates) => void;
}

/** Filters of the data explorer. Options list only values really stored (facets). */
export function ExplorerFilters({ query, institutionIds, facets, institutions, onChange }: ExplorerFiltersProps) {
  const t = useTranslations("data_explorer.filters");
  const tStatus = useTranslations("status");
  const tCountries = useTranslations("country_names");
  const labels = useLabels();
  const [search, setSearch] = useState("");

  const byId = useMemo(() => new Map(institutions.map((i) => [i.id, i])), [institutions]);
  const matches = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return [];
    return institutions
      .filter((i) => !institutionIds.includes(i.id))
      .filter((i) => !query.country_code || i.country?.code === query.country_code)
      .filter((i) => [i.name_official, i.name_commercial].some((n) => n?.toLowerCase().includes(q)))
      .slice(0, 8);
  }, [search, institutions, institutionIds, query.country_code]);

  const setIds = (ids: string[]) => onChange({ inst: ids.join(",") || null });
  const statusLabel = (s: string) => (tStatus.has(s) ? tStatus(s) : s);

  return (
    <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3" data-testid="explorer-filters">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        <label className="text-[11px] text-gray-400 font-medium">
          {t("country")}
          <select value={query.country_code ?? ""} onChange={(e) => onChange({ country: e.target.value })} className={selectCls}>
            <option value="">{t("all")}</option>
            {UMOA_COUNTRY_CODES.map((c) => (
              <option key={c} value={c}>
                {tCountries(c)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("indicator")}
          <select value={query.metric_code ?? ""} onChange={(e) => onChange({ metric: e.target.value })} className={selectCls}>
            <option value="">{t("all")}</option>
            {(facets?.metric_codes ?? []).map((m) => (
              <option key={m} value={m}>
                {labels.metric(m)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("year")}
          <select value={query.period_year ?? ""} onChange={(e) => onChange({ year: e.target.value })} className={selectCls}>
            <option value="">{t("all")}</option>
            {(facets?.period_years ?? []).map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("currency")}
          <select
            value={query.currency_normalized ?? ""}
            onChange={(e) => onChange({ currency: e.target.value })}
            className={selectCls}
          >
            <option value="">{t("all")}</option>
            {(facets?.currencies ?? []).map((c) => (
              <option key={c} value={c}>
                {displayCurrency(c)}
              </option>
            ))}
          </select>
        </label>

        {/* Period type and scope always hold ONE value: rows of different periods or scopes are never mixed. */}
        <label className="text-[11px] text-gray-400 font-medium">
          {t("period_type")}
          <select value={query.period_type} onChange={(e) => onChange({ period: e.target.value })} className={selectCls}>
            {withCurrent(facets?.period_types, query.period_type).map((p) => (
              <option key={p} value={p}>
                {labels.periodType(p)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("scope")}
          <select value={query.scope} onChange={(e) => onChange({ scope: e.target.value })} className={selectCls}>
            {withCurrent(facets?.scopes, query.scope).map((s) => (
              <option key={s} value={s}>
                {labels.scope(s)}
              </option>
            ))}
          </select>
        </label>

        <label className="text-[11px] text-gray-400 font-medium">
          {t("status")}
          <select value={query.status ?? ""} onChange={(e) => onChange({ status: e.target.value })} className={selectCls}>
            <option value="">{t("status_all_valid")}</option>
            {(facets?.statuses ?? []).map((s) => (
              <option key={s} value={s}>
                {statusLabel(s)}
              </option>
            ))}
          </select>
        </label>

        <div className="text-[11px] text-gray-400 font-medium relative">
          <label htmlFor="explorer-institution-search">{t("institution")}</label>
          <input
            id="explorer-institution-search"
            type="search"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t("institution_placeholder")}
            disabled={institutionIds.length >= MAX_SELECTED_INSTITUTIONS}
            className={selectCls}
          />
          {matches.length > 0 && (
            <ul
              className="absolute z-20 mt-1 w-full max-h-60 overflow-y-auto rounded-xl border border-gray-800 bg-gray-950 shadow-xl"
              role="listbox"
              aria-label={t("institution")}
            >
              {matches.map((i) => (
                <li key={i.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={false}
                    onClick={() => {
                      setIds([...institutionIds, i.id]);
                      setSearch("");
                    }}
                    className="w-full text-left px-3 py-2 text-xs text-gray-200 hover:bg-gray-800"
                  >
                    {i.name_official} <span className="text-gray-500">({i.country?.code ?? MISSING})</span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {institutionIds.length > 0 && (
        <div className="flex flex-wrap items-center gap-2" data-testid="selected-institutions">
          {institutionIds.map((id) => (
            <span
              key={id}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-lg border border-gray-700 bg-gray-900 text-xs text-gray-200"
            >
              {byId.get(id)?.name_official ?? id}
              <button
                type="button"
                onClick={() => setIds(institutionIds.filter((x) => x !== id))}
                aria-label={t("remove_institution", { name: byId.get(id)?.name_official ?? id })}
                className="text-gray-500 hover:text-rose-300"
              >
                ✕
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

/** Stored values, keeping the current selection listed even when no row has it (shown, not replaced). */
function withCurrent(values: string[] | undefined, current: string | undefined): string[] {
  const list = [...(values ?? [])];
  if (current && !list.includes(current)) list.unshift(current);
  return list;
}
