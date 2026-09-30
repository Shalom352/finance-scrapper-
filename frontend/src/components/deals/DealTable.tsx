"use client";

import React from "react";
import { useLocale, useTranslations } from "next-intl";
import type { DealListItem } from "@/types";
import { Link } from "@/i18n/navigation";
import { MISSING } from "@/lib/formatters";
import { dealDate, formatDay } from "@/lib/deals";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useDealLabels } from "@/components/deals/DealLabels";
import { useDealAmount } from "@/components/deals/DealAmount";

/** Deals as stored. Order comes from the backend (date, then title) — never a value-based ordering. */
export function DealTable({ items, hrefFor }: { items: DealListItem[]; hrefFor: (d: DealListItem) => string }) {
  const t = useTranslations("deals.table");
  const td = useTranslations("deals.duplicates");
  const tCountries = useTranslations("country_names");
  const locale = useLocale();
  const labels = useDealLabels();
  const amount = useDealAmount();
  const names = (list: string[]) => (list.length ? list.join(", ") : MISSING);

  return (
    <div className="overflow-x-auto rounded-2xl border border-gray-800">
      <table className="w-full text-xs" data-testid="deal-table">
        <thead className="bg-gray-900/80 text-gray-400">
          <tr>
            <th className="py-3 px-3 text-left">{t("deal")}</th>
            <th className="py-3 px-3 text-left">{t("type")}</th>
            <th className="py-3 px-3 text-left">{t("country")}</th>
            <th className="py-3 px-3 text-left">{t("borrower")}</th>
            <th className="py-3 px-3 text-left">{t("arranger")}</th>
            <th className="py-3 px-3 text-right">{t("amount")}</th>
            <th className="py-3 px-3 text-left">{t("date")}</th>
            <th className="py-3 px-3 text-left">{t("status")}</th>
            <th className="py-3 px-3 text-left">{t("open")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {items.map((d) => (
            <tr key={d.id} className="hover:bg-gray-800/30" data-testid="deal-row">
              <td className="py-2.5 px-3 font-semibold text-gray-100">
                {d.title}
                {d.duplicate_candidates > 0 && (
                  <span className="ml-2 px-1.5 py-0.5 rounded border border-amber-700/60 bg-amber-950/40 text-[10px] text-amber-300"
                    data-testid="deal-duplicate-badge">
                    {td("badge")}
                  </span>
                )}
              </td>
              <td className="py-2.5 px-3 text-gray-300">{labels.type(d.deal_type)}</td>
              <td className="py-2.5 px-3 text-gray-300">
                {d.country_code ? (tCountries.has(d.country_code) ? tCountries(d.country_code) : d.country_code) : MISSING}
              </td>
              <td className="py-2.5 px-3 text-gray-300">{names(d.borrowers)}</td>
              <td className="py-2.5 px-3 text-gray-300">{names(d.arrangers)}</td>
              <td className="py-2.5 px-3 text-right text-gray-200 whitespace-nowrap">{amount(d.amount, d.currency, d.unit)}</td>
              <td className="py-2.5 px-3 text-gray-400 whitespace-nowrap">{formatDay(dealDate(d), locale)}</td>
              <td className="py-2.5 px-3"><StatusBadge status={d.status} size="sm" /></td>
              <td className="py-2.5 px-3">
                <Link href={hrefFor(d)} className="text-emerald-300 hover:underline" data-testid="deal-open">
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
