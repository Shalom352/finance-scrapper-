"use client";

import React, { Suspense, useCallback, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import { Sidebar } from "./Sidebar";
import { Topbar } from "./Topbar";
import { WelcomeGuide } from "./WelcomeGuide";

const GUIDE_STORAGE_KEY = "umoa-banking-intelligence:welcome-guide:v2";

interface ShellProps {
  children: React.ReactNode;
}

export function Shell({ children }: ShellProps) {
  const t = useTranslations("footer");
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);

  useEffect(() => {
    let shouldShow = true;
    try {
      shouldShow = window.localStorage.getItem(GUIDE_STORAGE_KEY) !== "complete";
    } catch {
      // Keep the guide available when browser storage is disabled.
    }
    if (shouldShow) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- first-visit state is browser-only
      setGuideOpen(true);
    }
  }, []);

  const closeGuide = useCallback(() => {
    setGuideOpen(false);
    try {
      window.localStorage.setItem(GUIDE_STORAGE_KEY, "complete");
    } catch {
      // The guide can still be dismissed for this session without storage.
    }
    document.getElementById("open-welcome-guide")?.focus();
  }, []);

  return (
    <div className="flex min-h-screen bg-[#f8fafc] text-gray-900 font-sans selection:bg-emerald-100 selection:text-emerald-900">
      <Sidebar isOpen={mobileMenuOpen} onClose={() => setMobileMenuOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        {/* Topbar reads useSearchParams: Next 16 requires a Suspense boundary for prerendered routes. */}
        <Suspense fallback={<div className="h-16 border-b border-gray-200/80 bg-white" />}>
          <Topbar onMenuToggle={() => setMobileMenuOpen(true)} onGuideOpen={() => setGuideOpen(true)} />
        </Suspense>
        {guideOpen && <WelcomeGuide onClose={closeGuide} />}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">{children}</main>

        <footer className="border-t border-gray-200/80 py-6 px-4 sm:px-6 text-center text-xs text-gray-500 bg-white/50">
          <p>{t("disclaimer")}</p>
        </footer>
      </div>
    </div>
  );
}
