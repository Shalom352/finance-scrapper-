"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { InstitutionProfileCoverage } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

/** Descriptive coverage and data-quality counters — no score, no grade. */
export function CoveragePanel({ coverage }: { coverage: InstitutionProfileCoverage }) {
  const t = useTranslations("explorer");
  const fmt = useFormatters();
  const reason = useReasonLabel();
  const q = coverage.quality;
  // Only a coverage with a defined denominator is shown as a number; otherwise "—" with its reason.
  const ratio = coverage.coverage_ratio;
  const expected = coverage.expected_years_count;
  const known = ratio !== null && expected !== null;

  const counters: [string, number][] = [
    ["q_total", q.total_observations],
    ["q_verified", q.verified],
    ["q_reviewed", q.reviewed],
    ["q_extracted", q.extracted],
    ["q_needs_review", q.needs_review],
    ["q_rejected", q.rejected],
    ["q_conflicts", q.conflicts],
    ["q_missing_years", q.missing_years],
  ];

  return (
    <section className="grid grid-cols-1 lg:grid-cols-2 gap-4" data-testid="coverage-panel">
      <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30 space-y-2">
        <h3 className="text-sm font-semibold text-gray-200">{t("coverage_title")}</h3>
        <p className="text-2xl font-black text-white" data-testid="coverage-years">
          {known
            ? t("years_available", {
                available: coverage.available_years_count,
                expected,
                from: String(coverage.first_year),
                to: String(coverage.last_year),
              })
            : MISSING}
        </p>
        <p className="text-xs text-gray-400" data-testid="coverage-ratio">
          {known ? fmt.percent(ratio * 100, 0) : `${t("coverage_unavailable")} — ${reason(coverage.reason)}`}
        </p>
        {coverage.missing_years.length > 0 && (
          <p className="text-[11px] text-gray-500">{t("missing_years", { years: coverage.missing_years.join(", ") })}</p>
        )}
      </div>

      <div className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30 space-y-2">
        <h3 className="text-sm font-semibold text-gray-200">{t("quality_title")}</h3>
        <p className="text-[11px] text-gray-500">{t("quality_note")}</p>
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
          {counters.map(([key, n]) => (
            <React.Fragment key={key}>
              <dt className="text-gray-400">{t(key)}</dt>
              <dd className="text-right font-semibold text-gray-200" data-testid={`quality-${key}`}>
                {n}
              </dd>
            </React.Fragment>
          ))}
        </dl>
      </div>
    </section>
  );
}
