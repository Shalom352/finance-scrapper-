"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { RankHistory, RankingEntry, RankingUnavailableEntry } from "@/types";
import { MISSING, displayCurrency } from "@/lib/formatters";
import { useLabels } from "@/lib/useLabels";
import { useIndicatorValue } from "@/lib/useIndicatorValue";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";
import { SortHeader } from "@/components/common/SortHeader";
import { useSort } from "@/lib/useSort";

/** Descriptive ranking table: rank = numerical order of the value only. */
export function RankingTable({
  items,
  onProvenance,
  onHistory,
}: {
  items: RankingEntry[];
  onProvenance: (entry: RankingEntry) => void;
  onHistory?: (institutionId: string) => void;
}) {
  const t = useTranslations("rankings.table");
  const labels = useLabels();
  const formatValue = useIndicatorValue();

  return (
    <div className="rounded-2xl border border-gray-200 bg-white overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse" data-testid="ranking-table">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold uppercase tracking-wider">
            <th className="py-3 px-4">{t("rank")}</th>
            <th className="py-3 px-4">{t("institution")}</th>
            <th className="py-3 px-4">{t("country")}</th>
            <th className="py-3 px-4 text-right">{t("value")}</th>
            <th className="py-3 px-4">{t("currency")}</th>
            <th className="py-3 px-4 text-center">{t("status")}</th>
            <th className="py-3 px-4 text-center">{t("provenance")}</th>
            {onHistory && <th className="py-3 px-4 text-center">{t("history")}</th>}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((e) => (
            <tr key={e.institution_id} className="hover:bg-gray-50 transition-colors" data-testid="ranking-row">
              <td className="py-3 px-4 font-black text-gray-900" data-testid="rank-cell">
                {e.rank}
              </td>
              <td className="py-3 px-4 font-semibold text-gray-800">
                <Link href={`/institutions/${e.institution_id}`} className="hover:text-emerald-700">
                  {e.institution_name}
                </Link>
              </td>
              <td className="py-3 px-4 text-gray-500">{e.country_code ? labels.country(null, e.country_code) : MISSING}</td>
              <td className="py-3 px-4 text-right font-bold text-emerald-700" data-testid="value-cell">
                {formatValue(e.value, e.unit, e.currency)}
              </td>
              <td className="py-3 px-4 text-gray-500">{e.unit === "%" ? "%" : displayCurrency(e.currency) || MISSING}</td>
              <td className="py-3 px-4 text-center">
                <StatusBadge status={e.status} size="sm" />
              </td>
              <td className="py-3 px-4 text-center">
                {e.data_id || e.provenance.length > 0 ? (
                  <button
                    onClick={() => onProvenance(e)}
                    data-testid="provenance-button"
                    className="p-1 px-2 rounded-lg bg-gray-100 hover:bg-emerald-600 text-gray-700 hover:text-white text-xs"
                    title={t("provenance")}
                  >
                    🔍
                  </button>
                ) : (
                  MISSING
                )}
              </td>
              {onHistory && (
                <td className="py-3 px-4 text-center">
                  <button
                    onClick={() => onHistory(e.institution_id)}
                    className="px-2 py-1 rounded-lg border border-gray-300 text-gray-700 hover:border-emerald-600 text-[11px]"
                  >
                    {t("history")}
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Institutions without an admissible value: listed with the reason, never ranked. */
export function UnavailableList({ entries }: { entries: RankingUnavailableEntry[] }) {
  const t = useTranslations("rankings");
  const labels = useLabels();
  const reason = useReasonLabel();
  if (entries.length === 0) return null;

  return (
    <section className="space-y-2" data-testid="unavailable-section">
      <h3 className="text-sm font-bold text-gray-900">
        {t("unavailable_title")} ({entries.length})
      </h3>
      <p className="text-[11px] text-gray-500">{t("unavailable_hint")}</p>
      <ul className="divide-y divide-gray-100 rounded-2xl border border-gray-200 bg-white text-xs">
        {entries.map((u) => (
          <li key={u.institution_id} className="flex flex-wrap items-center justify-between gap-2 px-4 py-2.5" data-testid="unavailable-row">
            <span className="font-semibold text-gray-800">
              {u.institution_name}
              <span className="ml-2 font-normal text-gray-500">{u.country_code ? labels.country(null, u.country_code) : MISSING}</span>
            </span>
            <span className="flex items-center gap-2 text-gray-500">
              <span>{reason(u.reason)}</span>
              {u.currency && <span className="font-mono text-[11px]">{displayCurrency(u.currency)}</span>}
              <StatusBadge status={u.status} size="sm" />
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Observed rank per year — descriptive only, no wording of improvement or decline. */
export function RankHistoryTable({ history, unit }: { history: RankHistory; unit: string }) {
  const t = useTranslations("rankings");
  const reason = useReasonLabel();
  const formatValue = useIndicatorValue();
  const { sorted, sortKey, dir, toggle } = useSort(
    history.points,
    { year: (p) => p.period_year, rank: (p) => p.rank, value: (p) => p.value },
    { key: "year", dir: "desc" },
  );
  const head = (key: "year" | "rank" | "value", first: "asc" | "desc", cls = "") => (
    <SortHeader label={t(`table.${key}`)} active={sortKey === key} dir={dir} onClick={() => toggle(key, first)}
      className={`py-2 px-4 ${cls}`} testId={`rank-history-sort-${key}`} />
  );

  return (
    <section className="space-y-2" data-testid="rank-history">
      <h3 className="text-sm font-bold text-gray-900">{t("history_title", { institution: history.institution_name })}</h3>
      {history.points.length === 0 ? (
        <p className="text-xs text-gray-500">{t("history_empty")}</p>
      ) : (
        <div className="overflow-x-auto rounded-2xl border border-gray-200 bg-white">
        <table className="w-full min-w-[480px] text-left text-xs border-collapse">
          <thead>
            <tr className="border-b border-gray-200 text-gray-500 uppercase tracking-wider">
              {head("year", "desc")}
              {head("rank", "asc")}
              {head("value", "desc", "text-right")}
              <th className="py-2 px-4">{t("table.universe")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {sorted.map((p) => (
              <tr key={p.period_year} data-testid="history-row">
                <td className="py-2 px-4 text-gray-700">{p.period_year}</td>
                <td className="py-2 px-4 font-bold text-gray-900">
                  {p.rank ?? MISSING}
                  {p.rank === null && p.reason && <span className="ml-2 font-normal text-gray-500">{reason(p.reason)}</span>}
                </td>
                <td className="py-2 px-4 text-right text-gray-700">{formatValue(p.value, unit, p.currency)}</td>
                <td className="py-2 px-4 text-gray-500">
                  {p.coverage_ratio === null || p.ranked_count == null || p.expected_count == null
                    ? MISSING
                    : `${p.ranked_count} / ${p.expected_count}`}
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
