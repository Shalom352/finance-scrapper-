"use client";

import React, { useState } from "react";
import { useSearchParams } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname, useRouter } from "@/i18n/navigation";
import { routing } from "@/i18n/routing";
import { buildLocaleHref } from "@/lib/url";

interface TopbarProps {
  onMenuToggle?: () => void;
}

export function Topbar({ onMenuToggle }: TopbarProps) {
  const t = useTranslations("topbar");
  const [searchQuery, setSearchQuery] = useState("");
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const currentLocale = useLocale();

  // Same page, same query string (search, filters, pagination, year) — only the locale changes.
  const localeHref = buildLocaleHref(pathname, searchParams);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="h-16 border-b border-gray-800/80 bg-gray-950/80 backdrop-blur-md sticky top-0 z-20 px-4 sm:px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-900 focus:outline-none"
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
            className="w-full pl-9 pr-4 py-1.5 rounded-xl border border-gray-800 bg-gray-900/60 text-xs text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:bg-gray-900 focus:outline-none transition-all"
          />
          <span className="absolute left-3 top-2 text-xs text-gray-400 pointer-events-none">🔍</span>
        </form>
      </div>

      <div className="flex items-center bg-gray-900 border border-gray-800 rounded-xl p-0.5 text-xs font-semibold">
        {routing.locales.map((loc) => (
          <Link
            key={loc}
            href={localeHref}
            locale={loc}
            className={`px-2.5 py-1 rounded-lg transition-colors ${
              currentLocale === loc ? "bg-emerald-500 text-white font-bold" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            {loc.toUpperCase()}
          </Link>
        ))}
      </div>
    </header>
  );
}
