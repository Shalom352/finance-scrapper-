"use client";

import React, { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { Institution } from "@/types";
import { DEAL_STATUSES, DEAL_TYPES, PARTICIPANT_ROLES } from "@/types";
import type { DealQuery } from "@/lib/api";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { displayCurrency } from "@/lib/formatters";
import { DEAL_CURRENCIES, DEAL_FILTER_KEYS } from "@/lib/deals";
import { selectCls } from "@/components/rankings/IndicatorSelect";
import { useDealLabels } from "@/components/deals/DealLabels";

type Updates = Record<string, string | number | null>;

/** Free-text filter written to the URL on blur / Enter (no request per keystroke). */
function TextFilter({ label, value, onCommit }: { label: string; value: string; onCommit: (v: string) => void }) {
  const t = useTranslations("deals.filters");
  const [draft, setDraft] = useState(value);
  // eslint-disable-next-line react-hooks/set-state-in-effect -- keep the draft in sync with the URL
  useEffect(() => setDraft(value), [value]);
  return (
    <label className="text-[11px] text-gray-400 font-medium">
      {label}
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => draft.trim() !== value && onCommit(draft.trim())}
        onKeyDown={(e) => e.key === "Enter" && onCommit(draft.trim())}
        placeholder={t("text_placeholder")}
        maxLength={255}
        className={selectCls}
      />
    </label>
  );
}

export function DealFilters({
  query,
  institutions,
  onChange,
}: {
  query: DealQuery;
  institutions: Institution[];
  onChange: (updates: Updates) => void;
}) {
  const t = useTranslations("deals.filters");
  const tStatus = useTranslations("status");
  const tCountries = useTranslations("country_names");
  const labels = useDealLabels();
  const currencies = query.currency && !DEAL_CURRENCIES.includes(query.currency as (typeof DEAL_CURRENCIES)[number])
    ? [...DEAL_CURRENCIES, query.currency]
    : [...DEAL_CURRENCIES];

  const select = (key: string, label: string, value: string | undefined, options: [string, string][]) => (
    <label className="text-[11px] text-gray-400 font-medium">
      {label}
      <select value={value ?? ""} onChange={(e) => onChange({ [key]: e.target.value || null })} className={selectCls}
        data-testid={`deal-filter-${key}`}>
        <option value="">{t("all")}</option>
        {options.map(([v, l]) => (
          <option key={v} value={v}>{l}</option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3" data-testid="deal-filters">
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
        {select("country", t("country"), query.country,
          UMOA_COUNTRY_CODES.map((c) => [c, tCountries.has(c) ? tCountries(c) : c]))}
        {select("bank", t("bank"), query.bank, institutions.map((i) => [i.id, i.name_official]))}
        {select("participant_role", t("participant_role"), query.participant_role,
          PARTICIPANT_ROLES.map((r) => [r, labels.role(r)]))}
        {select("deal_type", t("deal_type"), query.deal_type, DEAL_TYPES.map((d) => [d, labels.type(d)]))}
        {select("status", t("status"), query.status, DEAL_STATUSES.map((s) => [s, tStatus.has(s) ? tStatus(s) : s]))}
        {select("currency", t("currency"), query.currency, currencies.map((c) => [c, displayCurrency(c) || c]))}
        <label className="text-[11px] text-gray-400 font-medium">
          {t("year")}
          <input type="number" min={1900} max={2100} defaultValue={query.year ?? ""} key={query.year ?? "none"}
            onBlur={(e) => onChange({ year: e.target.value || null })}
            onKeyDown={(e) => e.key === "Enter" && onChange({ year: (e.target as HTMLInputElement).value || null })}
            className={selectCls} data-testid="deal-filter-year" />
        </label>
        <TextFilter label={t("sector")} value={query.sector ?? ""} onCommit={(v) => onChange({ sector: v || null })} />
        <TextFilter label={t("borrower")} value={query.borrower ?? ""} onCommit={(v) => onChange({ borrower: v || null })} />
        <TextFilter label={t("arranger")} value={query.arranger ?? ""} onCommit={(v) => onChange({ arranger: v || null })} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <label className="flex items-center gap-2 text-[11px] text-gray-400">
          <input type="checkbox" checked={!!query.include_merged}
            onChange={(e) => onChange({ include_merged: e.target.checked ? "true" : null })} />
          {t("include_merged")}
        </label>
        <button type="button" data-testid="deal-filters-reset"
          onClick={() => onChange(Object.fromEntries(DEAL_FILTER_KEYS.map((k) => [k, null])))}
          className="px-3 py-1.5 rounded-lg border border-gray-700 text-xs text-gray-300 hover:border-emerald-500">
          {t("reset")}
        </button>
      </div>
    </div>
  );
}
