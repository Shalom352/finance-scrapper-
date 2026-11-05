"use client";

import React from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { buildLocaleHref } from "@/lib/url";

interface YearSelectProps {
  /** Years offered to the user, newest first, including the current and previous calendar years. */
  years: number[];
  value: number | null;
  /** Query parameter holding the year (kept in the URL so it survives a locale switch). */
  param?: string;
  /** Optional anchor used by the interactive platform tour. */
  guideId?: string;
  className?: string;
}

/** Fiscal-year selector that can also show years whose data has not arrived yet. */
export function YearSelect({ years, value, param = "year", guideId, className = "" }: YearSelectProps) {
  const t = useTranslations("common");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();

  if (years.length === 0) return null;

  const onChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const next = new URLSearchParams(searchParams.toString());
    next.set(param, e.target.value);
    next.delete("page");
    router.replace(buildLocaleHref(pathname, next), { scroll: false });
  };

  return (
    <label data-guide={guideId} className={`flex items-center gap-2 text-xs text-gray-500 ${className}`}>
      <span className="font-medium">{t("fiscal_year")}</span>
      <select
        value={value ?? ""}
        onChange={onChange}
        className="px-3 py-1.5 rounded-xl border border-gray-200 bg-white text-xs text-gray-800 focus:border-emerald-500 focus:outline-none"
      >
        {value === null && <option value="" disabled>{t("choose_fiscal_year")}</option>}
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </label>
  );
}
