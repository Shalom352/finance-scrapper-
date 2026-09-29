"use client";

import React, { useState } from "react";
import { usePathname, useRouter } from "@/i18n/navigation";
import { Link } from "@/i18n/navigation";
import { useLocale } from "next-intl";

interface TopbarProps {
  onMenuToggle?: () => void;
}

export function Topbar({ onMenuToggle }: TopbarProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const router = useRouter();
  const pathname = usePathname();
  const currentLocale = useLocale();

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  return (
    <header className="h-16 border-b border-gray-800/80 bg-gray-950/80 backdrop-blur-md sticky top-0 z-20 px-4 sm:px-6 flex items-center justify-between">
      <div className="flex items-center gap-3">
        {/* Mobile menu trigger */}
        <button
          onClick={onMenuToggle}
          className="lg:hidden p-2 rounded-lg text-gray-400 hover:text-white hover:bg-gray-900 focus:outline-none"
          aria-label="Ouvrir le menu de navigation"
        >
          <span className="text-xl">☰</span>
        </button>

        {/* Quick Search */}
        <form onSubmit={handleSearchSubmit} className="relative hidden sm:block w-72 md:w-96">
          <input
            type="search"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Rechercher une banque, un document..."
            className="w-full pl-9 pr-4 py-1.5 rounded-xl border border-gray-800 bg-gray-900/60 text-xs text-gray-200 placeholder-gray-500 focus:border-emerald-500 focus:bg-gray-900 focus:outline-none transition-all"
          />
          <span className="absolute left-3 top-2 text-xs text-gray-400 pointer-events-none">
            🔍
          </span>
        </form>
      </div>

      {/* Language Switcher & Actions */}
      <div className="flex items-center gap-3">
        <div className="flex items-center bg-gray-900 border border-gray-800 rounded-xl p-0.5 text-xs font-semibold">
          <Link
            href={pathname}
            locale="fr"
            className={`px-2.5 py-1 rounded-lg transition-colors ${
              currentLocale === "fr"
                ? "bg-emerald-500 text-white font-bold"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            FR
          </Link>
          <Link
            href={pathname}
            locale="en"
            className={`px-2.5 py-1 rounded-lg transition-colors ${
              currentLocale === "en"
                ? "bg-emerald-500 text-white font-bold"
                : "text-gray-400 hover:text-gray-200"
            }`}
          >
            EN
          </Link>
        </div>
      </div>
    </header>
  );
}
