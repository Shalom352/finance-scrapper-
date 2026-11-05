"use client";

import React, { useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { buildLocaleHref } from "@/lib/url";

interface TopbarProps {
  onMenuToggle?: () => void;
  onGuideOpen?: () => void;
}

export function Topbar({ onMenuToggle, onGuideOpen }: TopbarProps) {
  const t = useTranslations("topbar");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentLocale = useLocale();
  // On the search page the field shows the query being displayed.
  const currentQuery = pathname === "/search" ? (searchParams.get("q") ?? "") : "";
  const [searchQuery, setSearchQuery] = useState(currentQuery);
  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- follow the URL (back / forward)
    setSearchQuery(currentQuery);
  }, [currentQuery]);

  // Same page, same query string (search, filters, pagination, year) — only the locale changes.
  const localeHref = buildLocaleHref(pathname, searchParams);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim().length >= 2) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="h-16 border-b border-gray-200/90 bg-white/80 backdrop-blur-md sticky top-0 z-20 px-4 sm:px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="lg:hidden w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100 focus:outline-none"
          aria-label={t("open_menu")}
        >
          <span className="text-xl">☰</span>
        </button>

        <form onSubmit={handleSearchSubmit} className="relative hidden sm:block w-72 md:w-96">
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder={t("search_placeholder")}
            aria-label={t("search_placeholder")}
            minLength={2}
            className="w-full pl-9 pr-4 py-2 rounded-xl border border-gray-200 bg-gray-50/70 text-xs text-gray-800 placeholder-gray-400 focus:bg-white focus:border-emerald-600 focus:ring-1 focus:ring-emerald-500 focus:outline-none transition-all shadow-xs"
          />
          <svg
            className="absolute left-3 top-2.5 w-3.5 h-3.5 text-gray-400 pointer-events-none"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </form>
        {/* Below sm the search field is hidden: a touch-sized link opens the search page instead. */}
        <Link
          href="/search"
          className="sm:hidden w-10 h-10 flex items-center justify-center rounded-lg text-gray-500 hover:text-gray-900 hover:bg-gray-100"
          aria-label={t("search_placeholder")}
        >
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
        </Link>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <button
          id="open-welcome-guide"
          type="button"
          onClick={onGuideOpen}
          className="inline-flex min-h-9 items-center gap-1.5 rounded-lg px-2.5 text-xs font-semibold text-gray-600 transition-colors hover:bg-emerald-50 hover:text-emerald-800 focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:ring-offset-2"
          aria-label={t("open_guide")}
        >
          <svg className="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M9.1 9a3 3 0 015.8 1c0 2-3 3-3 3m8.1-1a8 8 0 11-16 0 8 8 0 0116 0z" />
          </svg>
          <span>{t("guide")}</span>
        </button>
        <div className="flex items-center bg-gray-100 border border-gray-200/80 rounded-lg p-0.5 text-xs font-semibold">
          {routing.locales.map((loc) => (
            <Link
              key={loc}
              href={localeHref}
              locale={loc}
              className={`px-2.5 min-h-9 min-w-9 inline-flex items-center justify-center rounded-md transition-colors ${
                currentLocale === loc ? "bg-white text-emerald-800 font-bold shadow-xs" : "text-gray-500 hover:text-gray-800"
              }`}
            >
              {loc.toUpperCase()}
            </Link>
          ))}
        </div>
      </div>
    </header>
  );
}
