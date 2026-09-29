"use client";

import React from "react";
import { Link, usePathname } from "@/i18n/navigation";
import { useTranslations } from "next-intl";

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

export function Sidebar({ isOpen = false, onClose }: SidebarProps) {
  const pathname = usePathname();
  const t = useTranslations("nav");
  const tSide = useTranslations("sidebar");

  const navItems = [
    { href: "/", label: t("home"), icon: "📊" },
    { href: "/institutions", label: t("institutions"), icon: "🏛️" },
    { href: "/countries", label: t("countries"), icon: "🌍" },
    { href: "/analytics", label: t("analytics"), icon: "📈" },
    { href: "/rankings", label: t("rankings"), icon: "🔢" },
    { href: "/comparisons", label: t("comparisons"), icon: "⚖️" },
    { href: "/financial-data", label: t("financial_data"), icon: "🗂️" },
    { href: "/documents", label: t("documents"), icon: "📑" },
    { href: "/search", label: t("search"), icon: "🔍" },
  ];

  const sidebarContent = (
    <div className="flex flex-col h-full bg-gray-950 border-r border-gray-800/80 w-64 p-4">
      {/* Brand */}
      <div className="flex items-center gap-3 px-2 py-4 mb-6">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-600 flex items-center justify-center text-white font-black text-base shadow-lg shadow-emerald-950/50">
          U
        </div>
        <div className="flex flex-col">
          <span className="font-bold text-sm text-white tracking-tight leading-none">
            UMOA Banking
          </span>
          <span className="text-[10px] text-emerald-400 font-semibold tracking-wider uppercase mt-1">
            Intelligence
          </span>
        </div>
      </div>

      {/* Nav items */}
      <nav className="flex-1 space-y-1">
        {navItems.map((item) => {
          const isActive =
            item.href === "/"
              ? pathname === "/"
              : pathname === item.href || pathname.startsWith(`${item.href}/`);

          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center gap-3 px-3 py-2.5 rounded-xl text-xs font-semibold transition-all ${
                isActive
                  ? "bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 shadow-sm"
                  : "text-gray-400 hover:text-gray-200 hover:bg-gray-900 border border-transparent"
              }`}
            >
              <span className="text-base" aria-hidden="true">
                {item.icon}
              </span>
              <span>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {/* Platform Status Notice */}
      <div className="p-3.5 rounded-2xl bg-gray-900/60 border border-gray-800 text-[11px] text-gray-400">
        <div className="flex items-center gap-2 text-emerald-400 font-semibold mb-1">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
          <span>{tSide("notice_title")}</span>
        </div>
        <p className="leading-relaxed text-gray-400">
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
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" onClick={onClose} />
          <div className="relative z-10 w-64 h-full animate-slide-right">
            {sidebarContent}
          </div>
        </div>
      )}
    </>
  );
}
