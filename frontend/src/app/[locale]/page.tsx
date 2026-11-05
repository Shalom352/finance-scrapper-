import React, { Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { formatCompactCurrency, formatNumber, MISSING } from "@/lib/formatters";
import { getSelectableYears, parseYearParam } from "@/lib/url";
import { UMOA_COUNTRY_CODES, COUNTRY_FLAGS } from "@/lib/countries";
import { FinancialBarChart } from "@/components/charts/FinancialBarChart";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { YearSelect } from "@/components/common/YearSelect";
import { YearDataNotice } from "@/components/common/YearDataNotice";
import { StatusBadge } from "@/components/common/StatusBadge";
import {
  getAggregations,
  getAvailableYears,
  getDocuments,
  getFinancialData,
  getInstitutions,
  resolveSelectableSectorYear,
} from "@/lib/api";
import type { SectorAggregation } from "@/types";

const REGIONAL_METRICS = [
  { code: "total_actifs", key: "total_assets" },
  { code: "depots_clients", key: "total_deposits" },
  { code: "creances_clients", key: "total_loans" },
  { code: "capitaux_propres", key: "total_equity" },
  { code: "resultat_net", key: "net_income" },
  { code: "produit_net_bancaire", key: "nbi" },
] as const;

/** Total count from a paginated route, or null when the call failed (displayed "—", never a guess). */
async function countOrNull(p: Promise<{ total: number }>): Promise<number | null> {
  try {
    return (await p).total;
  } catch {
    return null;
  }
}

export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const t = await getTranslations("dashboard");
  const tMetrics = await getTranslations("metrics");
  const tCountries = await getTranslations("country_names");
  const locale = await getLocale();
  const { year: yearParam } = await searchParams;

  const [institutionsCount, documentsCount, financialDataCount, verifiedDataCount, years] = await Promise.all([
    countOrNull(getInstitutions({ page_size: 1 })),
    countOrNull(getDocuments({ page_size: 1 })),
    countOrNull(getFinancialData({ page_size: 1 })),
    countOrNull(getFinancialData({ page_size: 1, status: "verified" })),
    getAvailableYears().catch(() => null),
  ]);

  const availableYears = years ?? [];
  const selectableYears = getSelectableYears(availableYears);
  const requestedYear = parseYearParam(yearParam);
  // The overview opens on the current fiscal year even when its annual statements
  // have not been published yet. A year in the URL remains selected until changed.
  const year = await resolveSelectableSectorYear(requestedYear ?? new Date().getFullYear(), availableYears);

  // One aggregation per metric; a failed or absent aggregation stays null.
  const aggregations: Record<string, SectorAggregation | null> = {};
  let aggregationLoadFailed = false;
  if (year !== null) {
    const results = await Promise.all(
      REGIONAL_METRICS.map(async (m) => {
        try {
          const res = await getAggregations({ year, metric_code: m.code, scope: "umoa" });
          return { aggregation: res.find((a) => a.metric_code === m.code && a.year === year) ?? null, failed: false };
        } catch {
          return { aggregation: null, failed: true };
        }
      }),
    );
    REGIONAL_METRICS.forEach((m, i) => (aggregations[m.code] = results[i].aggregation));
    aggregationLoadFailed = results.some((result) => result.failed);
  }

  const assetsAgg = aggregations.total_actifs ?? null;
  const count = (n: number | null) => (n === null ? MISSING : formatNumber(n, locale));

  const barChartItems = REGIONAL_METRICS.slice(0, 4).map((m) => ({
    label: tMetrics(m.code),
    value: aggregations[m.code]?.total_value ?? null,
  }));

  const kpis = [
    { label: t("kpi.institutions"), value: count(institutionsCount) },
    { label: t("kpi.countries"), value: formatNumber(UMOA_COUNTRY_CODES.length, locale) },
    { label: t("kpi.documents"), value: count(documentsCount) },
    { label: t("kpi.data_points"), value: count(financialDataCount) },
    { label: t("kpi.verified_data"), value: count(verifiedDataCount) },
  ];

  return (
    <div className="space-y-8 animate-fade-in pb-12">
      <div className="relative overflow-hidden rounded-3xl border border-gray-200/90 bg-gradient-to-br from-emerald-50/70 via-white to-gray-50 p-6 md:p-10 shadow-xs">
        <div className="max-w-3xl">
          <h1 className="text-3xl md:text-5xl font-black text-gray-900 tracking-tight mb-4">{t("title")}</h1>
          <p className="text-sm md:text-base text-gray-600 leading-relaxed mb-6">{t("subtitle")}</p>
          <div className="flex flex-wrap gap-3">
            <Link
              href="/institutions"
              className="px-5 py-2.5 rounded-xl bg-[#0B6E4F] hover:bg-[#095940] text-white text-xs font-bold shadow-xs transition-colors"
            >
              {t("quick_links.explore_institutions")}
            </Link>
            <Link
              href="/analytics"
              className="px-5 py-2.5 rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold shadow-xs transition-colors"
            >
              {t("quick_links.view_analytics")}
            </Link>
          </div>
        </div>
      </div>

      <div data-guide="overview" className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {kpis.map((k) => (
          <div key={k.label} className="p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs flex flex-col justify-between">
            <span className="text-xs text-gray-500 font-medium">{k.label}</span>
            <span className="text-2xl font-black text-gray-900 mt-3">{k.value}</span>
          </div>
        ))}
        <div className="p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs">
          <CoverageIndicator
            label={t("kpi.coverage")}
            coverageRatio={assetsAgg?.coverage_ratio}
            isPartial={assetsAgg?.is_partial}
            representedCount={assetsAgg?.institution_count}
            totalCount={assetsAgg?.total_institutions}
          />
        </div>
      </div>

      {years === null && (
        <div role="alert" className="p-4 rounded-2xl border border-rose-200 bg-rose-50 text-sm text-rose-800 shadow-xs">
          {t("years_error")}
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-bold text-gray-900 tracking-tight">{t("regional_aggregates.title")}</h2>
              <p className="text-xs text-gray-500">{t("regional_aggregates.subtitle")}</p>
            </div>
            <Suspense fallback={null}>
              <YearSelect years={selectableYears} value={year} />
            </Suspense>
          </div>

          {year !== null && (
            <YearDataNotice
              year={year}
              availableYears={years}
              loadFailed={aggregationLoadFailed}
              // The broad coverage endpoint may list a year even when the
              // regional aggregation returned no row at all. In both cases,
              // tell the user why the selected year's totals are unavailable.
              hasData={assetsAgg?.total_value != null}
            />
          )}

          {year === null ? (
            <p className="p-6 rounded-2xl border border-dashed border-gray-200 bg-white text-sm text-gray-500">{t("no_years")}</p>
          ) : (
            <div className="grid grid-cols-1 min-[420px]:grid-cols-2 lg:grid-cols-3 gap-3">
              {REGIONAL_METRICS.map((m) => {
                const agg = aggregations[m.code];
                return (
                  <div key={m.code} className="p-3 sm:p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs min-w-0">
                    <span className="text-xs text-gray-500 font-medium block mb-1">
                      {t(`regional_aggregates.${m.key}`)} ({year})
                    </span>
                    <span className="block text-lg sm:text-xl font-black text-gray-900 whitespace-nowrap">
                      {formatCompactCurrency(agg?.total_value, agg?.currency, locale)}
                    </span>
                    {agg?.status === "needs_review" || agg?.status === "unavailable" ? (
                      <StatusBadge status={agg.status} size="sm" className="mt-1" />
                    ) : (
                      agg?.is_partial && <span className="text-[11px] text-amber-600 font-medium block mt-1">{t("partial_badge")}</span>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        <div className="flex flex-col justify-between">
          <FinancialBarChart
            items={barChartItems}
            title={t("structure_title")}
            currency={assetsAgg?.currency ?? null}
          />
        </div>
      </div>

      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-gray-900 tracking-tight">{t("countries_title")}</h2>
          <Link href="/countries" className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 hover:underline">
            {t("countries_link")}
          </Link>
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
          {UMOA_COUNTRY_CODES.map((code) => (
            <Link
              key={code}
              href={`/countries/${code}`}
              className="group p-4 rounded-2xl border border-gray-200/90 bg-white hover:border-emerald-200 hover:shadow-xs transition-all flex flex-col items-center text-center"
            >
              <span className="text-3xl mb-2 group-hover:scale-110 transition-transform">{COUNTRY_FLAGS[code]}</span>
              <span className="text-xs font-bold text-gray-800 group-hover:text-emerald-800">{tCountries(code)}</span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
