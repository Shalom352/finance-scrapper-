"use client";

import React, { Suspense, useEffect, useState, use } from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import type { Institution, SectorAggregation, SectorStructure } from "@/types";
import { getAggregations, getAvailableYears, getInstitutions, getSectorStructure } from "@/lib/api";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { parseYearParam, resolveYear } from "@/lib/url";
import { COUNTRY_FLAGS, isUmoaCountry } from "@/lib/countries";
import { resolveKpi, SECTOR_KPI_BINDINGS, type KpiBinding } from "@/lib/countryKpis";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";
import { FinancialBarChart } from "@/components/charts/FinancialBarChart";
import { CardSkeleton, TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { YearSelect } from "@/components/common/YearSelect";
import { StatusBadge } from "@/components/common/StatusBadge";

interface PageProps {
  params: Promise<{ country: string; locale: string }>;
}

export default function CountryDetailPage({ params }: PageProps) {
  const { country } = use(params);
  return (
    <Suspense fallback={<CardSkeleton />}>
      <CountryDetail countryCode={country.toUpperCase()} />
    </Suspense>
  );
}

interface CountryData {
  years: number[];
  institutions: Institution[];
  institutionsTotal: number | null;
  aggregations: SectorAggregation[];
}

function CountryDetail({ countryCode }: { countryCode: string }) {
  const t = useTranslations("countries.detail");
  const tKpi = useTranslations("kpi");
  const tCountries = useTranslations("country_names");
  const fmt = useFormatters();
  const labels = useLabels();
  const searchParams = useSearchParams();
  const requestedYear = parseYearParam(searchParams.get("year"));

  const [data, setData] = useState<CountryData | null>(null);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [shareBinding, setShareBinding] = useState<KpiBinding>(SECTOR_KPI_BINDINGS[1]);
  const [structure, setStructure] = useState<SectorStructure | null>(null);
  const [structureState, setStructureState] = useState<"loading" | "ready" | "unavailable">("loading");

  const known = isUmoaCountry(countryCode);
  const year = data ? resolveYear(requestedYear, data.years) : null;

  // Years, institutions and one aggregation per KPI binding.
  useEffect(() => {
    if (!known) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setError(false);

    (async () => {
      const years = await getAvailableYears({ country_code: countryCode });
      const y = resolveYear(requestedYear, years);
      const [insts, ...aggs] = await Promise.all([
        getInstitutions({ country_code: countryCode, page_size: 100 }).catch(() => null),
        ...SECTOR_KPI_BINDINGS.map((b) =>
          y === null
            ? Promise.resolve<SectorAggregation[]>([])
            : getAggregations({ year: y, metric_code: b.metric_code, country_code: countryCode }).catch(() => []),
        ),
      ]);
      return {
        years,
        institutions: (insts as { items: Institution[] } | null)?.items ?? [],
        institutionsTotal: (insts as { total: number } | null)?.total ?? null,
        aggregations: (aggs as SectorAggregation[][]).flat(),
      };
    })()
      .then((d) => !cancelled && setData(d))
      .catch(() => !cancelled && setError(true));

    return () => {
      cancelled = true;
    };
  }, [countryCode, known, requestedYear, attempt]);

  // Market shares for the selected metric; the response must match that metric.
  useEffect(() => {
    if (year === null) return;
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- reset before refetch
    setStructureState("loading");
    getSectorStructure({ country_code: countryCode, year, metric_code: shareBinding.metric_code })
      .then((res) => {
        if (cancelled) return;
        const matches = res.aggregation.metric_code === shareBinding.metric_code && res.aggregation.year === year;
        setStructure(matches ? res : null);
        setStructureState(matches ? "ready" : "unavailable");
      })
      .catch(() => {
        if (cancelled) return;
        setStructure(null);
        setStructureState("unavailable");
      });
    return () => {
      cancelled = true;
    };
  }, [countryCode, year, shareBinding]);

  if (!known) {
    return <EmptyState title={t("unknown_country")} description={countryCode} />;
  }
  if (error) return <ErrorState onRetry={() => setAttempt((a) => a + 1)} />;
  if (!data) {
    return (
      <div className="space-y-6">
        <CardSkeleton />
        <TableSkeleton rows={6} cols={4} />
      </div>
    );
  }

  const kpis = SECTOR_KPI_BINDINGS.map((b) => ({
    binding: b,
    agg: year === null ? null : resolveKpi(b, year, data.aggregations),
  }));
  const assetsAgg = kpis.find((k) => k.binding.labelKey === "total_assets")?.agg ?? null;
  const shares = structure?.market_shares ?? [];

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <Link href="/countries" className="inline-flex text-xs font-semibold text-gray-400 hover:text-emerald-400 transition-colors">
        ← {t("back")}
      </Link>

      <div className="p-6 md:p-8 rounded-3xl border border-gray-800 bg-gray-900/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="flex items-center gap-4">
            <span className="text-5xl">{COUNTRY_FLAGS[countryCode]}</span>
            <div>
              <span className="px-2.5 py-0.5 rounded-lg border border-emerald-800/60 bg-emerald-950/40 text-emerald-400 text-xs font-bold font-mono">
                {countryCode}
              </span>
              <h1 className="text-2xl md:text-4xl font-black text-white tracking-tight mt-1">{tCountries(countryCode)}</h1>
            </div>
          </div>
          <div className="w-full md:w-72 space-y-3">
            <YearSelect years={data.years} value={year} />
            <CoverageIndicator
              coverageRatio={assetsAgg?.coverage_ratio}
              isPartial={assetsAgg?.is_partial}
              representedCount={assetsAgg?.institution_count}
              totalCount={assetsAgg?.total_institutions}
              label={t("coverage_label")}
            />
          </div>
        </div>
      </div>

      {year === null ? (
        <EmptyState title={t("no_years_title")} description={t("no_years")} />
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {kpis.map(({ binding, agg }) => (
              <div key={binding.labelKey} className="p-5 rounded-2xl border border-gray-800 bg-gray-900/30" data-testid={`kpi-${binding.labelKey}`}>
                <span className="text-xs text-gray-400 font-medium block mb-1">
                  {tKpi(binding.labelKey)} ({year})
                </span>
                <span className="text-2xl font-black text-emerald-400">{fmt.compact(agg?.total_value, agg?.currency)}</span>
                {agg === null && <span className="text-[11px] text-gray-500 block mt-1">{t("kpi_unavailable")}</span>}
                {agg?.status === "needs_review" || agg?.status === "unavailable" ? (
                  <StatusBadge status={agg.status} size="sm" className="mt-1" />
                ) : (
                  agg?.is_partial && <span className="text-[11px] text-amber-400 block mt-1">{t("partial_badge")}</span>
                )}
              </div>
            ))}
            <div className="p-5 rounded-2xl border border-gray-800 bg-gray-900/30">
              <span className="text-xs text-gray-400 font-medium block mb-1">{t("institutions_counted")}</span>
              <span className="text-2xl font-black text-white">
                {assetsAgg ? `${assetsAgg.institution_count} / ${assetsAgg.total_institutions}` : MISSING}
              </span>
              <span className="text-[11px] text-gray-500 block mt-1">{t("institutions_counted_hint")}</span>
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h3 className="text-lg font-bold text-white tracking-tight">{t("market_share_title")}</h3>
                <p className="text-[11px] text-gray-500">{t("scope_note")}</p>
              </div>
              <label className="flex items-center gap-2 text-xs text-gray-400">
                {t("market_share_metric")}
                <select
                  value={shareBinding.metric_code}
                  onChange={(e) =>
                    setShareBinding(SECTOR_KPI_BINDINGS.find((b) => b.metric_code === e.target.value) ?? SECTOR_KPI_BINDINGS[1])
                  }
                  className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200"
                >
                  {SECTOR_KPI_BINDINGS.map((b) => (
                    <option key={b.metric_code} value={b.metric_code}>
                      {labels.metric(b.metric_code)}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              <FinancialBarChart
                title={t("market_share_chart", { metric: labels.metric(shareBinding.metric_code) })}
                isPercent
                items={shares.slice(0, 8).map((ms) => ({
                  label: ms.institution_name ?? ms.institution_id,
                  value: ms.market_share_percent,
                }))}
              />

              <div className="rounded-2xl border border-gray-800 bg-gray-900/30 overflow-hidden">
                {structureState === "loading" ? (
                  <TableSkeleton rows={4} cols={3} />
                ) : shares.length === 0 ? (
                  <div className="p-8 text-center text-xs text-gray-500">{t("market_share_empty")}</div>
                ) : (
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-gray-800 bg-gray-900/60 text-gray-400 font-semibold uppercase tracking-wider">
                        <th className="py-3 px-4">{t("col_institution")}</th>
                        <th className="py-3 px-4 text-right">{labels.metric(shareBinding.metric_code)}</th>
                        <th className="py-3 px-4 text-right">{t("col_share")}</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-800/60">
                      {shares.map((ms) => (
                        <tr key={ms.institution_id} className="hover:bg-gray-800/30 transition-colors">
                          <td className="py-3 px-4 font-semibold text-gray-200">
                            <Link href={`/institutions/${ms.institution_id}`} className="hover:text-emerald-400">
                              {ms.institution_name ?? ms.institution_id}
                            </Link>
                          </td>
                          <td className="py-3 px-4 text-right text-gray-300">{fmt.compact(ms.institution_value, ms.currency)}</td>
                          <td className="py-3 px-4 text-right font-bold text-emerald-400">{fmt.percent(ms.market_share_percent, 2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>
          </div>
        </>
      )}

      <div className="space-y-4">
        <h3 className="text-lg font-bold text-white tracking-tight">
          {t("institutions_title")} ({data.institutionsTotal ?? MISSING})
        </h3>
        {data.institutions.length === 0 ? (
          <p className="text-xs text-gray-500">{t("institutions_empty")}</p>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.institutions.map((inst) => (
              <Link
                key={inst.id}
                href={`/institutions/${inst.id}`}
                className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 hover:border-emerald-600/50 hover:bg-gray-900 transition-all flex flex-col justify-between"
              >
                <span className="text-xs font-bold text-gray-200 block mb-1">{inst.name_official}</span>
                {inst.banking_group && <span className="text-[11px] text-gray-400 block">{inst.banking_group.name}</span>}
                <span className="text-[11px] text-gray-500 mt-3 pt-2 border-t border-gray-800/60">{labels.institutionType(inst.institution_type) || MISSING}</span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
