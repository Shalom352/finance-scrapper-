"use client";

import React from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

interface YearDataNoticeProps {
  year: number;
  availableYears: number[] | null;
  /** Whether this view has usable data for the selected year (overrides broad coverage years). */
  hasData?: boolean | null;
  /** Whether the aggregation request failed, which is different from missing data. */
  loadFailed?: boolean;
}

export function YearDataNotice({ year, availableYears, hasData, loadFailed = false }: YearDataNoticeProps) {
  const t = useTranslations("common");

  if (!loadFailed && (hasData === true || (hasData == null && (availableYears === null || availableYears.includes(year))))) return null;

  return (
    <div role={loadFailed ? "alert" : "status"} className="flex flex-col gap-1 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-xs text-amber-900 sm:flex-row sm:items-center sm:justify-between">
      <p>{t(loadFailed ? "aggregate_load_error" : hasData === false ? "missing_aggregate_data" : "missing_year_data", { year })}</p>
      {!loadFailed && (
        <Link href="/settings" className="font-semibold text-amber-900 underline underline-offset-2 hover:text-amber-700">
          {t("open_collection_settings")}
        </Link>
      )}
    </div>
  );
}
