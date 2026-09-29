"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ComparisonRow, CountryComparison, InstitutionsComparison, SectorComparison } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { useIndicatorValue } from "@/lib/useIndicatorValue";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

/**
 * Numerical difference with the reference (first) row — only when both values exist
 * and the comparison is homogeneous. Descriptive: a signed number, never a judgement.
 */
export function differenceFromReference(result: InstitutionsComparison, row: ComparisonRow): number | null {
  if (result.status === "needs_review" || result.status === "unavailable") return null;
  const ref = result.rows[0];
  if (!ref || ref.institution_id === row.institution_id) return null;
  if (ref.value === null || row.value === null) return null;
  if (result.unit !== "%" && ref.currency !== row.currency) return null;
  return row.value - ref.value;
}

export function ComparisonTable({
  result,
  onProvenance,
}: {
  result: InstitutionsComparison;
  onProvenance: (row: ComparisonRow) => void;
}) {
  const t = useTranslations("comparisons.table");
  const labels = useLabels();
  const reason = useReasonLabel();
  const formatValue = useIndicatorValue();
  const reference = result.rows[0]?.institution_name ?? "";

  return (
    <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-x-auto">
      <table className="w-full text-left text-xs border-collapse" data-testid="comparison-table">
        <thead>
          <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
            <th className="py-3 px-4">{t("institution")}</th>
            <th className="py-3 px-4">{t("country")}</th>
            <th className="py-3 px-4 text-right">{t("value")}</th>
            <th className="py-3 px-4 text-right">{t("difference", { reference })}</th>
            <th className="py-3 px-4 text-center">{t("status")}</th>
            <th className="py-3 px-4 text-center">{t("provenance")}</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-800/60">
          {result.rows.map((row) => {
            const diff = differenceFromReference(result, row);
            return (
              <tr key={row.institution_id} data-testid="comparison-row">
                <td className="py-3 px-4 font-semibold text-gray-200">{row.institution_name}</td>
                <td className="py-3 px-4 text-gray-400">{row.country_code ? labels.country(null, row.country_code) : MISSING}</td>
                <td className="py-3 px-4 text-right font-bold text-white" data-testid="comparison-value">
                  {formatValue(row.value, result.unit, row.currency)}
                  {row.value === null && row.reason && (
                    <span className="block text-[11px] font-normal text-gray-500">{reason(row.reason)}</span>
                  )}
                </td>
                <td className="py-3 px-4 text-right text-gray-300" data-testid="comparison-diff">
                  {diff === null ? MISSING : `${diff > 0 ? "+" : ""}${formatValue(diff, result.unit, row.currency)}`}
                </td>
                <td className="py-3 px-4 text-center">
                  <StatusBadge status={row.status} size="sm" />
                </td>
                <td className="py-3 px-4 text-center">
                  {row.data_id || row.provenance.length > 0 ? (
                    <button
                      onClick={() => onProvenance(row)}
                      className="p-1 px-2 rounded-lg bg-gray-800 hover:bg-emerald-600 text-gray-300 hover:text-white text-xs"
                      title={t("provenance")}
                    >
                      🔍
                    </button>
                  ) : (
                    MISSING
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Not computable for this indicator: explicit status and reason, no numeric line at all. */
function NotSupportedCard({ title, reason, testId }: { title: string; reason: string; testId: string }) {
  return (
    <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs space-y-1.5" data-testid={testId}>
      <div className="flex items-center justify-between">
        <span className="font-bold text-gray-200">{title}</span>
        <StatusBadge status="unavailable" size="sm" />
      </div>
      <p className="text-[11px] text-amber-400/90" data-testid="not-supported-reason">
        {reason}
      </p>
    </div>
  );
}

export function SectorComparisonCard({ result, institutionName }: { result: SectorComparison; institutionName?: string }) {
  const t = useTranslations("comparisons.sector");
  const fmt = useFormatters();
  const reason = useReasonLabel();
  const inst = result.institution;

  if (result.reason === "aggregate_not_supported") {
    return (
      <NotSupportedCard
        title={inst?.institution_name ?? institutionName ?? MISSING}
        reason={reason(result.reason)}
        testId="sector-card"
      />
    );
  }

  return (
    <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs space-y-1.5" data-testid="sector-card">
      <div className="flex items-center justify-between">
        <span className="font-bold text-gray-200">{inst?.institution_name ?? MISSING}</span>
        <StatusBadge status={result.status} size="sm" />
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("institution_value")}</span>
        <span className="text-gray-200">{fmt.compact(inst?.value, inst?.currency)}</span>
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("sector_total")}</span>
        <span className="text-gray-200">{fmt.compact(result.sector_total, result.sector_currency)}</span>
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("share")}</span>
        <span className="font-bold text-emerald-400" data-testid="sector-share">
          {fmt.percent(result.share_percent, 2)}
        </span>
      </div>
      {result.reason && <p className="text-[11px] text-amber-400/90">{reason(result.reason)}</p>}
    </div>
  );
}

export function CountryComparisonCard({ result, countryName }: { result: CountryComparison; countryName: string }) {
  const t = useTranslations("comparisons.country");
  const fmt = useFormatters();
  const reason = useReasonLabel();

  if (result.reason === "aggregate_not_supported") {
    return <NotSupportedCard title={countryName} reason={reason(result.reason)} testId="country-card" />;
  }

  return (
    <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 text-xs space-y-1.5" data-testid="country-card">
      <div className="flex items-center justify-between">
        <span className="font-bold text-gray-200">
          {countryName} {result.period_year !== null ? `(${result.period_year})` : ""}
        </span>
        <StatusBadge status={result.status} size="sm" />
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("country_total")}</span>
        <span className="text-gray-200">{fmt.compact(result.country_total, result.currency)}</span>
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("umoa_total")}</span>
        <span className="text-gray-200">{fmt.compact(result.umoa_total, result.currency)}</span>
      </div>
      <div className="flex justify-between text-gray-400">
        <span>{t("share")}</span>
        <span className="font-bold text-emerald-400" data-testid="country-share">
          {fmt.percent(result.share_percent, 2)}
        </span>
      </div>
      {result.reason && <p className="text-[11px] text-amber-400/90">{reason(result.reason)}</p>}
    </div>
  );
}
