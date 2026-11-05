"use client";

import React, { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { DealAnalytics, DealDimension } from "@/types";
import { getDealAnalytics } from "@/lib/api";
import { useFormatters } from "@/lib/useFormatters";
import { selectCls } from "@/components/rankings/IndicatorSelect";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { ErrorState } from "@/components/common/EmptyState";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useDealLabels } from "@/components/deals/DealLabels";
import { useDealAmount } from "@/components/deals/DealAmount";

const DIMENSIONS: DealDimension[] = ["country", "year", "type", "sector", "institution"];

type Load = { status: "loading" } | { status: "error" } | { status: "ready"; data: DealAnalytics };

/** Descriptive counts only: no ranking, no score, amounts per currency and unit (never summed across). */
export function DealAnalyticsPanel({ dimension, onDimension }: { dimension: DealDimension; onDimension: (d: DealDimension) => void }) {
  const t = useTranslations("deals.analytics");
  const tCountries = useTranslations("country_names");
  const fmt = useFormatters();
  const labels = useDealLabels();
  const amount = useDealAmount();
  const [state, setState] = useState<Load>({ status: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for a new dimension
    setState({ status: "loading" });
    getDealAnalytics(dimension)
      .then((data) => !cancelled && setState({ status: "ready", data }))
      .catch(() => !cancelled && setState({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [dimension, reload]);

  const groupLabel = (key: string | null, label: string | null) => {
    if (key === null) return t("not_specified");
    if (dimension === "country") return tCountries.has(key) ? tCountries(key) : key;
    if (dimension === "type") return labels.type(key);
    return label ?? key;
  };

  return (
    <section className="p-4 rounded-2xl border border-gray-200/90 bg-white shadow-xs space-y-3" data-testid="deal-analytics">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <h2 className="text-sm font-bold text-gray-900">{t("title")}</h2>
        <label className="text-[11px] text-gray-600 font-medium w-56">
          {t("dimension")}
          <select value={dimension} onChange={(e) => onDimension(e.target.value as DealDimension)} className={selectCls}
            data-testid="deal-analytics-dimension">
            {DIMENSIONS.map((d) => (
              <option key={d} value={d}>{t(`dimensions.${d}`)}</option>
            ))}
          </select>
        </label>
      </div>
      <p className="text-[11px] text-gray-500">{t("basis")}</p>
      {state.status === "loading" ? (
        <TableSkeleton rows={3} cols={4} />
      ) : state.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : state.data.rows.length === 0 ? (
        <p className="text-xs text-gray-500" data-testid="deal-analytics-empty">{t("empty")}</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead className="text-gray-500 border-b border-gray-100">
              <tr>
                <th className="py-2.5 px-3 text-left font-semibold">{t("group")}</th>
                <th className="py-2.5 px-3 text-right font-semibold">{t("deals")}</th>
                <th className="py-2.5 px-3 text-left font-semibold">{t("by_status")}</th>
                <th className="py-2.5 px-3 text-left font-semibold">{t("amounts")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {state.data.rows.map((r) => (
                <tr key={r.key ?? "none"} data-testid="deal-analytics-row" className="hover:bg-gray-50/70">
                  <td className="py-2.5 px-3 text-gray-900 font-semibold">{groupLabel(r.key, r.label)}</td>
                  <td className="py-2.5 px-3 text-right text-gray-700 font-medium">{fmt.number(r.deals)}</td>
                  <td className="py-2.5 px-3">
                    <div className="flex flex-wrap gap-1">
                      {Object.entries(r.by_status).map(([s, n]) => (
                        <span key={s} className="inline-flex items-center gap-1">
                          <StatusBadge status={s} size="sm" />
                          <span className="text-gray-500 text-[11px] font-medium">{fmt.number(n)}</span>
                        </span>
                      ))}
                    </div>
                  </td>
                  <td className="py-2.5 px-3 text-gray-800">
                    {r.amounts.length === 0 ? (
                      <span className="text-gray-400">{t("no_amount")}</span>
                    ) : (
                      <ul className="space-y-0.5 font-medium" data-testid="deal-analytics-amounts">
                        {r.amounts.map((a) => (
                          <li key={`${a.currency}-${a.unit ?? ""}`}>
                            {amount(a.total, a.currency, a.unit)}{" "}
                            <span className="text-gray-500 font-normal">({t("amount_deals", { count: a.deals })})</span>
                          </li>
                        ))}
                      </ul>
                    )}
                    <span className="block text-[10px] text-gray-400 mt-0.5">{t("without_amount", { count: r.deals_without_amount })}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
