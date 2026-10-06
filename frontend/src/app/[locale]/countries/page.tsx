import React, { Suspense } from "react";
import { Link } from "@/i18n/navigation";
import { getLocale, getTranslations } from "next-intl/server";
import { getAggregations, getAvailableYears, getInstitutions, resolveSectorYear } from "@/lib/api";
import { formatCompactCurrency, formatNumber, MISSING } from "@/lib/formatters";
import { parseYearParam } from "@/lib/url";
import { COUNTRY_FLAGS, UMOA_COUNTRY_CODES } from "@/lib/countries";
import { resolveKpi, SECTOR_KPI_BINDINGS } from "@/lib/countryKpis";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { YearSelect } from "@/components/common/YearSelect";
import type { SectorAggregation } from "@/types";

const CARD_BINDINGS = SECTOR_KPI_BINDINGS.filter((b) => b.labelKey !== "total_loans");

export default async function CountriesListPage({
  searchParams,
}: {
  searchParams: Promise<{ [key: string]: string | string[] | undefined }>;
}) {
  const t = await getTranslations("countries");
  const tKpi = await getTranslations("kpi");
  const tCountries = await getTranslations("country_names");
  const locale = await getLocale();
  const { year: yearParam } = await searchParams;

  const years = await getAvailableYears().catch(() => null);
  const availableYears = years ?? [];
  const year = await resolveSectorYear(parseYearParam(yearParam), availableYears);

  const cards = await Promise.all(
    UMOA_COUNTRY_CODES.map(async (code) => {
      const [institutionsCount, ...aggs] = await Promise.all([
        getInstitutions({ country_code: code, page_size: 1 })
          .then((r) => r.total)
          .catch(() => null),
        ...CARD_BINDINGS.map((b) =>
          year === null
            ? Promise.resolve<SectorAggregation[] | null>(null)
            : getAggregations({ year, metric_code: b.metric_code, country_code: code }).catch(() => null),
        ),
      ]);
      const flat = (aggs as (SectorAggregation[] | null)[]).flatMap((a) => a ?? []);
      return {
        code,
        institutionsCount: institutionsCount as number | null,
        kpis: CARD_BINDINGS.map((b) => ({ binding: b, agg: year === null ? null : resolveKpi(b, year, flat) })),
      };
    }),
  );

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
          <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
        </div>
        <Suspense fallback={null}>
          <YearSelect years={availableYears} value={year} />
        </Suspense>
      </div>

      {years === null && (
        <div role="alert" className="p-4 rounded-2xl border border-rose-800/60 bg-rose-950/30 text-sm text-rose-200">
          {t("years_error")}
        </div>
      )}
      {years !== null && year === null && (
        <p className="p-4 rounded-2xl border border-dashed border-gray-800 text-sm text-gray-400">{t("no_years")}</p>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {cards.map((c) => {
          const assets = c.kpis.find((k) => k.binding.labelKey === "total_assets")?.agg ?? null;
          return (
            <Link
              key={c.code}
              href={year === null ? `/countries/${c.code}` : `/countries/${c.code}?year=${year}`}
              className="group flex flex-col justify-between p-6 rounded-3xl border border-gray-800 bg-gray-900/40 hover:border-emerald-600/60 hover:bg-gray-900 transition-all shadow-lg"
            >
              <div>
                <div className="flex items-center justify-between mb-4">
                  <span className="text-4xl group-hover:scale-110 transition-transform">{COUNTRY_FLAGS[c.code]}</span>
                  <span className="px-2.5 py-0.5 rounded-lg border border-gray-700 bg-gray-800 text-xs font-mono font-bold text-gray-300">
                    {c.code}
                  </span>
                </div>

                <h3 className="text-lg font-bold text-white group-hover:text-emerald-400 transition-colors mb-4">
                  {tCountries(c.code)}
                </h3>

                <div className="space-y-2 py-3 border-t border-b border-gray-800/80 text-xs">
                  <div className="flex justify-between">
                    <span className="text-gray-400">{t("card.institutions")}</span>
                    <span className="font-semibold text-gray-200">
                      {c.institutionsCount === null ? MISSING : formatNumber(c.institutionsCount, locale)}
                    </span>
                  </div>
                  {c.kpis.map(({ binding, agg }) => (
                    <div key={binding.labelKey} className="flex justify-between">
                      <span className="text-gray-400">
                        {tKpi(binding.labelKey)}
                        {year !== null ? ` (${year})` : ""}
                      </span>
                      <span className="font-bold text-emerald-400">
                        {formatCompactCurrency(agg?.total_value, agg?.currency, locale)}
                      </span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-4 pt-2">
                <CoverageIndicator
                  coverageRatio={assets?.coverage_ratio}
                  isPartial={assets?.is_partial}
                  representedCount={assets?.institution_count}
                  totalCount={assets?.total_institutions}
                  label={t("card.coverage")}
                />
                <div className="flex justify-end mt-3">
                  <span className="text-xs font-semibold text-emerald-400 group-hover:translate-x-1 transition-transform">
                    {t("card.open")}
                  </span>
                </div>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
