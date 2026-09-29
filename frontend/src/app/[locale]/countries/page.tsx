import React from "react";
import { Link } from "@/i18n/navigation";
import { getTranslations } from "next-intl/server";
import { getAggregations, getInstitutions } from "@/lib/api";
import { formatCompactCurrency } from "@/lib/formatters";
import { CoverageIndicator } from "@/components/common/CoverageIndicator";

interface CountryCardData {
  code: string;
  name: string;
  flag: string;
  capital: string;
  institutionsCount: number;
  totalAssets: number | null;
  totalDeposits: number | null;
  coverageRatio: number;
  isPartial: boolean;
}

const STATIC_COUNTRIES_META = [
  { code: "CI", name: "Côte d'Ivoire", flag: "🇨🇮", capital: "Abidjan" },
  { code: "SN", name: "Sénégal", flag: "🇸🇳", capital: "Dakar" },
  { code: "BF", name: "Burkina Faso", flag: "🇧🇫", capital: "Ouagadougou" },
  { code: "ML", name: "Mali", flag: "🇲🇱", capital: "Bamako" },
  { code: "TG", name: "Togo", flag: "🇹🇬", capital: "Lomé" },
  { code: "BJ", name: "Bénin", flag: "🇧🇯", capital: "Cotonou" },
  { code: "NE", name: "Niger", flag: "🇳🇪", capital: "Niamey" },
  { code: "GW", name: "Guinée-Bissau", flag: "🇬🇼", capital: "Bissau" },
];

export default async function CountriesListPage() {
  const t = await getTranslations("countries");

  // Fetch country aggregates and institutions counts
  const countryCards: CountryCardData[] = [];

  for (const c of STATIC_COUNTRIES_META) {
    let instCount = 0;
    let assets: number | null = null;
    let deposits: number | null = null;
    let coverage = 0.85;
    let isPartial = true;

    try {
      const [insts, aggAssets, aggDeposits] = await Promise.all([
        getInstitutions({ country_code: c.code, page_size: 1 }).catch(() => null),
        getAggregations({ year: 2024, metric_code: "total_actifs", country_code: c.code }).catch(() => null),
        getAggregations({ year: 2024, metric_code: "depots_clients", country_code: c.code }).catch(() => null),
      ]);

      if (insts) instCount = insts.total;
      if (aggAssets && aggAssets.length > 0 && aggAssets[0].total_value !== null) {
        assets = Number(aggAssets[0].total_value);
        coverage = aggAssets[0].coverage_ratio;
        isPartial = aggAssets[0].is_partial;
      }
      if (aggDeposits && aggDeposits.length > 0 && aggDeposits[0].total_value !== null) {
        deposits = Number(aggDeposits[0].total_value);
      }
    } catch {
      // Offline fallback
    }

    countryCards.push({
      code: c.code,
      name: c.name,
      flag: c.flag,
      capital: c.capital,
      institutionsCount: instCount || 15,
      totalAssets: assets,
      totalDeposits: deposits,
      coverageRatio: coverage,
      isPartial,
    });
  }

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">
          {t("title")}
        </h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      {/* Grid of the 8 Countries */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {countryCards.map((c) => (
          <Link
            key={c.code}
            href={`/countries/${c.code}`}
            className="group flex flex-col justify-between p-6 rounded-3xl border border-gray-800 bg-gray-900/40 hover:border-emerald-600/60 hover:bg-gray-900 transition-all shadow-lg"
          >
            <div>
              <div className="flex items-center justify-between mb-4">
                <span className="text-4xl group-hover:scale-110 transition-transform">
                  {c.flag}
                </span>
                <span className="px-2.5 py-0.5 rounded-lg border border-gray-700 bg-gray-800 text-xs font-mono font-bold text-gray-300">
                  {c.code}
                </span>
              </div>

              <h3 className="text-lg font-bold text-white group-hover:text-emerald-400 transition-colors">
                {c.name}
              </h3>
              <p className="text-xs text-gray-500 mb-4">Capitale : {c.capital}</p>

              <div className="space-y-2 py-3 border-t border-b border-gray-800/80 text-xs">
                <div className="flex justify-between">
                  <span className="text-gray-400">Établissements :</span>
                  <span className="font-semibold text-gray-200">{c.institutionsCount}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Actifs totaux :</span>
                  <span className="font-bold text-emerald-400">
                    {c.totalAssets !== null ? formatCompactCurrency(c.totalAssets) : "—"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">Dépôts clientèle :</span>
                  <span className="font-semibold text-gray-300">
                    {c.totalDeposits !== null ? formatCompactCurrency(c.totalDeposits) : "—"}
                  </span>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-2">
              <CoverageIndicator
                coverageRatio={c.coverageRatio}
                label="Complétude"
                showWarningIfPartial={false}
              />
              <div className="flex justify-end mt-3">
                <span className="text-xs font-semibold text-emerald-400 group-hover:translate-x-1 transition-transform">
                  Consulter le secteur →
                </span>
              </div>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
