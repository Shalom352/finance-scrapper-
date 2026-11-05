"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { FinancialDataExplorerItem } from "@/types";
import type { ExplorerSort } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { displayCurrency, MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";

interface ExplorerTableProps {
  items: FinancialDataExplorerItem[];
  sort: ExplorerSort | undefined;
  order: "asc" | "desc";
  onSort: (sort: ExplorerSort) => void;
  onProvenance: (dataId: string) => void;
  /** Optional last column linking each row to a page (review queue -> observation detail). */
  rowLink?: { label: string; href: (row: FinancialDataExplorerItem) => string };
}

/**
 * Stored observations, one row each, exactly as stored (normalized value + unit + currency).
 * No total, no average, no conversion: rows of different currencies are only listed.
 */
export function ExplorerTable({ items, sort, order, onSort, onProvenance, rowLink }: ExplorerTableProps) {
  const t = useTranslations("data_explorer.table");
  const tq = useTranslations("data_explorer.qualification");
  const labels = useLabels();
  const fmt = useFormatters();
  const hasSourceValue = (value: string | null | undefined) => {
    const raw = value?.trim() ?? "";
    return raw.length > 0 && !/^[-—–]+$/.test(raw);
  };

  const header = (key: ExplorerSort, label: string, align = "") => {
    const active = sort === key;
    return (
      <th
        className={`py-3 px-3 ${align}`}
        aria-sort={active ? (order === "asc" ? "ascending" : "descending") : "none"}
      >
        <button
          type="button"
          onClick={() => onSort(key)}
          className={`inline-flex items-center gap-1 uppercase tracking-wider ${active ? "text-emerald-700" : ""}`}
          data-testid={`sort-${key}`}
        >
          {label}
          <span aria-hidden="true">{active ? (order === "asc" ? "▲" : "▼") : "↕"}</span>
        </button>
      </th>
    );
  };

  return (
    <div className="overflow-x-auto rounded-2xl border border-gray-200">
      <table className="w-full text-left text-xs border-collapse" data-testid="explorer-table">
        <thead>
          <tr className="border-b border-gray-200 bg-gray-50/80 text-gray-500 font-semibold">
            {header("institution", t("institution"))}
            {header("country", t("country"))}
            {header("indicator", t("indicator"))}
            {header("year", t("year"))}
            <th className="py-3 px-3 uppercase tracking-wider">{t("period_type")}</th>
            <th className="py-3 px-3 uppercase tracking-wider">{t("scope")}</th>
            {header("value", t("value"), "text-right")}
            <th className="py-3 px-3 uppercase tracking-wider">{t("unit")}</th>
            <th className="py-3 px-3 uppercase tracking-wider">{t("currency")}</th>
            <th className="py-3 px-3 uppercase tracking-wider">{t("status")}</th>
            <th className="py-3 px-3 uppercase tracking-wider">{t("source")}</th>
            {rowLink && <th className="py-3 px-3" aria-label={rowLink.label} />}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {items.map((row) => (
            <tr key={row.id} className="hover:bg-gray-50 transition-colors" data-testid="explorer-row">
              <td className="py-2.5 px-3 font-semibold text-gray-800">
                <Link href={`/institutions/${row.institution_id}`} className="hover:text-emerald-700 underline-offset-2 hover:underline">
                  {row.institution_name ?? MISSING}
                </Link>
              </td>
              <td className="py-2.5 px-3 text-gray-700">{row.country_code ? labels.country(null, row.country_code) : MISSING}</td>
              <td className="py-2.5 px-3 text-gray-800">{labels.metric(row.metric_code)}</td>
              <td className="py-2.5 px-3 text-gray-700">{row.period_year}</td>
              <td className="py-2.5 px-3 text-gray-500">{labels.periodType(row.period_type)}</td>
              <td className="py-2.5 px-3 text-gray-500">
                <span>{row.scope_evidence_class === "D" ? tq("scope_provisional") : labels.scope(row.scope)}</span>
                {row.scope_evidence_class === "D" && (
                  <span className="block text-[10px] text-amber-700">{tq("scope_provisional")}</span>
                )}
              </td>
              <td className="py-2.5 px-3 text-right font-mono font-bold text-emerald-700" data-testid="explorer-value">
                {row.value_normalized === null
                  ? hasSourceValue(row.value_original) ? row.value_original : MISSING
                  : fmt.number(row.value_normalized, Number.isInteger(row.value_normalized) ? 0 : 2)}
                {row.value_normalized === null && hasSourceValue(row.value_original) && (
                  <span className="block font-sans text-[10px] font-normal text-amber-700">
                    {t("source_value_pending")}
                  </span>
                )}
              </td>
              <td className="py-2.5 px-3 text-gray-500">{row.unit_normalized || row.unit_original || MISSING}</td>
              <td className="py-2.5 px-3 text-gray-500">{displayCurrency(row.currency_normalized || row.currency_original) || MISSING}</td>
              <td className="py-2.5 px-3">
                <div className="flex flex-col items-start gap-1">
                  <StatusBadge status={row.status} size="sm" />
                  {row.qualification && (
                    <span className="text-[10px] text-gray-500" data-testid="explorer-qualification">
                      {tq(row.qualification)}
                    </span>
                  )}
                  {row.scope_evidence_class === "D" && (
                    <span className="max-w-44 text-[10px] text-amber-700" data-testid="explorer-scope-warning">
                      {tq("scope_unconfirmed")}
                    </span>
                  )}
                </div>
              </td>
              <td className="py-2.5 px-3">
                <button
                  type="button"
                  onClick={() => onProvenance(row.id)}
                  className="text-left text-gray-700 hover:text-emerald-700"
                  title={t("source_title")}
                  data-testid="explorer-source"
                >
                  <span className="block">{row.source_name ?? MISSING}</span>
                  <span className="block text-[10px] text-gray-500">
                    {row.document_title ?? MISSING}
                    {row.page_number !== null ? ` · ${t("page", { page: row.page_number })}` : ""}
                  </span>
                </button>
              </td>
              {rowLink && (
                <td className="py-2.5 px-3">
                  <Link
                    href={rowLink.href(row)}
                    className="px-2 py-1 rounded-lg bg-gray-100 hover:bg-emerald-600 text-gray-800 hover:text-white whitespace-nowrap"
                    data-testid="row-link"
                  >
                    {rowLink.label}
                  </Link>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
