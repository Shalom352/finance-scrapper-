"use client";

import React from "react";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { buildLocaleHref } from "@/lib/url";

interface YearSelectProps {
  /** Years that actually hold data (from the API), newest first. */
  years: number[];
  value: number | null;
  /** Query parameter holding the year (kept in the URL so it survives a locale switch). */
  param?: string;
  className?: string;
}

/** Explicit fiscal-year selector restricted to years returned by the backend. */
export function YearSelect({ years, value, param = "year", className = "" }: YearSelectProps) {
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
    <label className={`flex items-center gap-2 text-xs text-gray-400 ${className}`}>
      <span className="font-medium">{t("fiscal_year")}</span>
      <select
        value={value ?? ""}
        onChange={onChange}
        className="px-3 py-1.5 rounded-xl border border-gray-800 bg-gray-950 text-xs text-gray-200 focus:border-emerald-500 focus:outline-none"
      >
        {years.map((y) => (
          <option key={y} value={y}>
            {y}
          </option>
        ))}
      </select>
    </label>
  );
}
