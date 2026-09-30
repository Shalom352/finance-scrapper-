"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ReviewObservation } from "@/types";
import { Link } from "@/i18n/navigation";
import { displayCurrency, MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";

interface Props {
  currentId: string;
  rows: ReviewObservation[];
  /** Same logical key: differences shown (same currency + unit only). Other dimension: listed only. */
  comparable: boolean;
  hrefFor: (id: string) => string;
}

/**
 * Side-by-side observations. A difference is shown only when the backend computed one
 * (same currency and unit); otherwise the reason is shown — values are never converted.
 */
export function CompetingObservations({ currentId, rows, comparable, hrefFor }: Props) {
  const t = useTranslations("data_quality.competing");
  const tq = useTranslations("data_explorer.qualification");
  const td = useTranslations("data_quality.detail");
  const labels = useLabels();
  const fmt = useFormatters();
  const num = (v: number | null) => (v === null ? MISSING : fmt.number(v, Number.isInteger(v) ? 0 : 2));

  return (
    <div className="overflow-x-auto rounded-2xl border border-gray-800">
      <table className="w-full text-left text-xs" data-testid={comparable ? "dq-competing" : "dq-not-comparable"}>
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 uppercase tracking-wider">
            <th className="py-2 px-3">{t("observation")}</th>
            <th className="py-2 px-3 text-right">{t("value")}</th>
            <th className="py-2 px-3">{td("currency")}</th>
            <th className="py-2 px-3">{td("unit")}</th>
            <th className="py-2 px-3">{td("year")}</th>
            <th className="py-2 px-3">{td("period_type")}</th>
            <th className="py-2 px-3">{td("scope")}</th>
            <th className="py-2 px-3">{td("document")}</th>
            <th className="py-2 px-3">{td("page")}</th>
            <th className="py-2 px-3">{td("status")}</th>
            {comparable && <th className="py-2 px-3 text-right">{t("difference")}</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {rows.map((o) => (
            <tr key={o.id} data-testid="dq-competing-row" className={o.id === currentId ? "bg-emerald-950/20" : ""}>
              <td className="py-2 px-3">
                {o.id === currentId ? (
                  <span className="font-semibold text-emerald-300">{t("this")}</span>
                ) : (
                  <Link href={hrefFor(o.id)} className="text-gray-200 hover:text-emerald-300 underline-offset-2 hover:underline">
                    {t("open")}
                  </Link>
                )}
              </td>
              <td className="py-2 px-3 text-right font-mono font-bold text-gray-100">{num(o.value_normalized)}</td>
              <td className="py-2 px-3 text-gray-400">{displayCurrency(o.currency_normalized) || MISSING}</td>
              <td className="py-2 px-3 text-gray-400">{o.unit_normalized || MISSING}</td>
              <td className="py-2 px-3 text-gray-300">{o.period_year}</td>
              <td className="py-2 px-3 text-gray-400">{labels.periodType(o.period_type)}</td>
              <td className="py-2 px-3 text-gray-400">{labels.scope(o.scope)}</td>
              <td className="py-2 px-3 text-gray-400">
                <span className="block">{o.document_title ?? MISSING}</span>
                <span className="block text-[10px] text-gray-500">{o.source_name ?? MISSING}</span>
              </td>
              <td className="py-2 px-3 text-gray-400">{o.page_number ?? MISSING}</td>
              <td className="py-2 px-3">
                <StatusBadge status={o.status} size="sm" />
                {o.qualification && <span className="block text-[10px] text-gray-500 mt-1">{tq(o.qualification)}</span>}
              </td>
              {comparable && (
                <td className="py-2 px-3 text-right text-gray-300" data-testid="dq-difference">
                  {o.difference !== null
                    ? `${o.difference > 0 ? "+" : ""}${num(o.difference)}`
                    : o.difference_reason
                      ? t(`reasons.${o.difference_reason}`)
                      : MISSING}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
