"use client";

import React from "react";
import { useLocale, useTranslations } from "next-intl";
import type { DealListItem } from "@/types";
import { Link } from "@/i18n/navigation";
import { MISSING } from "@/lib/formatters";
import { dealDate, formatDay } from "@/lib/deals";
import { COUNTRY_FLAGS } from "@/lib/countries";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useDealLabels } from "@/components/deals/DealLabels";
import { useDealAmount } from "@/components/deals/DealAmount";
import { SortHeader } from "@/components/common/SortHeader";
import { dateKey, useSort, type SortDir } from "@/lib/useSort";

type DealSortKey = "deal" | "type" | "country" | "borrower" | "arranger" | "date" | "status";
const FIRST_DIR: Record<DealSortKey, SortDir> = {
  deal: "asc", type: "asc", country: "asc", borrower: "asc", arranger: "asc", date: "desc", status: "asc",
};

/**
 * Deals as stored. The backend orders by date then title; the headers re-sort the rows of the
 * current page (newest first by default). Amounts are not sortable: currencies are never mixed.
 */
export function DealTable({ items, hrefFor }: { items: DealListItem[]; hrefFor: (d: DealListItem) => string }) {
  const t = useTranslations("deals.table");
  const td = useTranslations("deals.duplicates");
  const tCountries = useTranslations("country_names");
  const locale = useLocale();
  const labels = useDealLabels();
  const amount = useDealAmount();
  const names = (list: string[]) => (list.length ? list.join(", ") : MISSING);
  const country = (code: string | null) => (code ? (tCountries.has(code) ? tCountries(code) : code) : null);
  const { sorted, sortKey, dir, toggle } = useSort(
    items,
    {
      deal: (d) => d.title,
      type: (d) => labels.type(d.deal_type),
      country: (d) => country(d.country_code),
      borrower: (d) => d.borrowers[0] ?? null,
      arranger: (d) => d.arrangers[0] ?? null,
      date: (d) => dateKey(dealDate(d)),
      status: (d) => d.status,
    },
    { key: "date", dir: "desc" },
  );
  const head = (key: DealSortKey, cls = "text-left") => (
    <SortHeader label={t(key)} active={sortKey === key} dir={dir} onClick={() => toggle(key, FIRST_DIR[key])}
      className={`py-3 px-3.5 ${cls}`} testId={`deal-sort-${key}`} />
  );

  return (
    <div className="overflow-x-auto rounded-2xl border border-gray-200/90 bg-white shadow-xs">
      <table className="w-full min-w-[960px] text-xs" data-testid="deal-table">
        <thead className="bg-gray-50/80 text-gray-500 font-semibold border-b border-gray-200/80">
          <tr>
            {head("deal")}
            {head("type")}
            {head("country")}
            {head("borrower")}
            {head("arranger")}
            <th className="py-3 px-3.5 text-right">{t("amount")}</th>
            {head("date")}
            {head("status")}
            <th className="py-3 px-3.5 text-left">{t("open")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {sorted.map((d) => (
            <tr key={d.id} className="hover:bg-gray-50/70 transition-colors" data-testid="deal-row">
              <td className="py-3 px-3.5 font-semibold text-gray-900">
                <div className="flex flex-col items-start gap-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span>{d.title}</span>
                    {d.duplicate_candidates > 0 && (
                      <span className="px-1.5 py-0.5 rounded border border-amber-200 bg-amber-50 text-[10px] font-medium text-amber-700"
                        data-testid="deal-duplicate-badge">
                        {td("badge")}
                      </span>
                    )}
                  </div>
                  <span className="px-2 py-0.5 rounded-md bg-gray-100 text-gray-600 text-[10px] font-medium">
                    {labels.type(d.deal_type)}
                  </span>
                </div>
              </td>
              <td className="py-3 px-3.5 text-gray-700">{labels.type(d.deal_type)}</td>
              <td className="py-3 px-3.5 text-gray-800">
                <span className="inline-flex items-center gap-1.5">
                  <span className="text-sm">{d.country_code && COUNTRY_FLAGS[d.country_code] ? COUNTRY_FLAGS[d.country_code] : ""}</span>
                  <span>{country(d.country_code) ?? MISSING}</span>
                </span>
              </td>
              <td className="py-3 px-3.5 text-gray-700 font-medium">{names(d.borrowers)}</td>
              <td className="py-3 px-3.5 text-gray-600">{names(d.arrangers)}</td>
              <td className="py-3 px-3.5 text-right text-gray-900 font-semibold whitespace-nowrap">
                {amount(d.amount, d.currency, d.unit)}
              </td>
              <td className="py-3 px-3.5 text-gray-500 whitespace-nowrap">{formatDay(dealDate(d), locale)}</td>
              <td className="py-3 px-3.5">
                <StatusBadge status={d.status} size="sm" />
              </td>
              <td className="py-3 px-3.5 whitespace-nowrap">
                <Link href={hrefFor(d)} className="text-emerald-700 hover:text-emerald-900 font-semibold hover:underline" data-testid="deal-open">
                  {t("open")} →
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
