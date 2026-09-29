"use client";

import React, { Suspense, useState } from "react";
import { useTranslations } from "next-intl";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";

interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const t = useTranslations("footer");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex min-h-screen bg-gray-950 text-gray-100 font-sans selection:bg-emerald-800 selection:text-white">
      <Sidebar isOpen={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar reads useSearchParams: Next 16 requires a Suspense boundary for prerendered routes. */}
        <Suspense fallback={<div className="h-16 border-b border-gray-800/80" />}>
          <Topbar onMenuToggle={() => setMobileMenuOpen(true)} />
        </Suspense>
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">{children}</main>

        <footer className="border-t border-gray-800/60 py-6 px-4 sm:px-6 text-center text-xs text-gray-500">
          <p>{t("disclaimer")}</p>
        </footer>
      </div>
    </div>
  );
}
