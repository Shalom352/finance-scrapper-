"use client";

import React from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { useLocale, useTranslations } from "next-intl";

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const locale = useLocale();
  const t = useTranslations("nav");
  const tSide = useTranslations("sidebar");

  const navItems = [
    {
      href: "/",
      label: t("home"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
        </svg>
      ),
    },
    {
      href: "/deals",
      label: t("deals"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
        </svg>
      ),
    },
    {
      href: "/rankings",
      label: t("rankings"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
    },
    {
      href: "/analytics",
      label: t("analytics"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
    },
    {
      href: "/comparisons",
      label: t("comparisons"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M8 7h12m0 0l-4-4m4 4l-4 4m0 6H4m0 0l4 4m-4-4l4-4" />
        </svg>
      ),
    },
    {
      href: "/institutions",
      label: t("institutions"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 21V5a2 2 0 00-2-2H7a2 2 0 00-2 2v16m14 0h2m-2 0h-5m-9 0H3m2 0h5M9 7h1m-1 4h1m4-4h1m-1 4h1m-5 10v-5a1 1 0 011-1h2a1 1 0 011 1v5m-4 0h4" />
        </svg>
      ),
    },
    {
      href: "/countries",
      label: t("countries"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M3.055 11H5a2 2 0 012 2v1a2 2 0 002 2 2 2 0 012 2v2.945M8 3.935V5.5A2.5 2.5 0 0010.5 8h.5a2 2 0 012 2 2 2 0 104 0 2 2 0 012-2h1.064M15 20.488V18a2 2 0 012-2h3.064M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      href: "/financial-data",
      label: t("financial_data"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
        </svg>
      ),
    },
    {
      href: "/documents",
      label: t("sources"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 7v10c0 2 1.5 3 3.5 3h9c2 0 3.5-1 3.5-3V7c0-2-1.5-3-3.5-3h-9C5.5 4 4 5 4 7zm0 5h16M8 8h.01M8 16h.01" />
        </svg>
      ),
    },
    {
      href: "/data-quality",
      label: t("data_quality"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
        </svg>
      ),
    },
    {
      href: "/targeting",
      label: t("targeting"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <circle cx="12" cy="12" r="9" />
          <circle cx="12" cy="12" r="5" />
          <circle cx="12" cy="12" r="1.2" fill="currentColor" />
        </svg>
      ),
    },
    {
      href: "/syndication",
      label: t("syndication"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
    {
      href: "/settings",
      label: t("settings"),
      icon: (
        <svg className="w-4 h-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.8}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
          <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
        </svg>
      ),
    },
  ];

  const isActive = (item: (typeof navItems)[number]) =>
    item.href === "/"
      ? pathname === "/"
      : pathname === item.href || pathname.startsWith(`${item.href}/`);

  const homeItem = navItems[0];
  const navGroups = [
    {
      id: "activity",
      label: tSide("groups.activity"),
      items: navItems.filter((item) => ["/deals", "/targeting", "/syndication"].includes(item.href)),
    },
    {
      id: "data",
      label: tSide("groups.data"),
      items: navItems.filter((item) => ["/institutions", "/countries", "/financial-data", "/documents"].includes(item.href)),
    },
    {
      id: "analysis",
      label: tSide("groups.analysis"),
      items: navItems.filter((item) => ["/rankings", "/analytics", "/comparisons"].includes(item.href)),
    },
    {
      id: "management",
      label: tSide("groups.management"),
      items: navItems.filter((item) => ["/data-quality", "/settings"].includes(item.href)),
    },
  ];

  const renderNavItem = (item: (typeof navItems)[number]) => {
    const active = isActive(item);
    return (
      <Link
        key={item.href}
        href={item.href}
        locale={locale}
        onClick={onClose}
        aria-current={active ? "page" : undefined}
        className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-medium transition-all ${
          active
            ? "bg-[#EBF7EE] text-[#15803D] font-semibold border border-emerald-100/70 shadow-xs"
            : "text-gray-600 hover:text-gray-900 hover:bg-gray-50 border border-transparent"
        }`}
      >
        <span className={active ? "text-[#15803D]" : "text-gray-400"} aria-hidden="true">
          {item.icon}
        </span>
        <span>{item.label}</span>
      </Link>
    );
  };

  const sidebarContent = (
    <div className="flex flex-col h-full bg-white border-r border-gray-200/90 w-64 p-4 shadow-xs">
      {/* Brand: the product name used in the page titles */}
      <Link href="/" locale={locale} onClick={onClose} className="flex items-center gap-2.5 px-3 py-3 mb-5 group">
        <div className="flex items-center">
          <span className="font-extrabold text-lg leading-tight tracking-tight text-gray-900 group-hover:text-emerald-800 transition-colors">
            UMOA Banking <span className="text-emerald-700">Intelligence</span>
          </span>
        </div>
      </Link>

      {/* Primary navigation: keep the overview visible and group the rest by task. */}
      <nav className="flex-1 space-y-1" aria-label={tSide("navigation_label")}>
        {renderNavItem(homeItem)}
        {navGroups.map((group) => {
          const groupIsActive = group.items.some(isActive);
          return (
            <details key={group.id} className="group rounded-xl" open={groupIsActive}>
              <summary
                className={`flex min-h-10 cursor-pointer list-none items-center justify-between gap-3 rounded-xl px-3.5 py-2.5 text-xs font-semibold transition-colors marker:hidden [&::-webkit-details-marker]:hidden ${
                  groupIsActive ? "text-emerald-800" : "text-gray-600 hover:bg-gray-50 hover:text-gray-900"
                }`}
              >
                <span>{group.label}</span>
                <svg className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
                  <path fillRule="evenodd" d="M5.22 7.47a.75.75 0 011.06 0L10 11.19l3.72-3.72a.75.75 0 111.06 1.06l-4.25 4.25a.75.75 0 01-1.06 0L5.22 8.53a.75.75 0 010-1.06z" clipRule="evenodd" />
                </svg>
              </summary>
              <div className="ml-2 space-y-1 border-l border-gray-200 pl-2">
                {group.items.map(renderNavItem)}
              </div>
            </details>
          );
        })}
      </nav>

      {/* Official Sources Notice Card */}
      <div className="p-3.5 rounded-2xl bg-gray-50 border border-gray-200/80 text-[11px] text-gray-500">
        <div className="flex items-center gap-2 text-emerald-700 font-semibold mb-1">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>{tSide("notice_title")}</span>
        </div>
        <p className="leading-relaxed text-gray-500">
          {tSide("notice_body")}
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop Persistent Sidebar */}
      <aside className="hidden lg:block h-screen sticky top-0 shrink-0 z-30">
        {sidebarContent}
      </aside>

      {/* Mobile Drawer */}
      {isOpen && (
        <div className="fixed inset-0 z-50 lg:hidden flex">
          <div className="fixed inset-0 bg-black/40 backdrop-blur-xs" onClick={onClose} />
          <div className="relative z-10 w-64 h-full animate-slide-right">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
