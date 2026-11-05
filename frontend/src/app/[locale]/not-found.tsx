"use client";

import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

/** Unknown page or record: inside the app shell, with a way back (never a dead end). */
export default function NotFound() {
  const t = useTranslations("errors");
  return (
    <section className="p-8 rounded-2xl border border-dashed border-gray-200 bg-white text-center space-y-3" data-testid="not-found">
      <h1 className="text-xl font-bold text-gray-900">{t("not_found_title")}</h1>
      <p className="text-sm text-gray-600">{t("not_found_body")}</p>
      <div className="flex flex-wrap justify-center gap-2 pt-2">
        <Link href="/" className="min-h-10 px-4 inline-flex items-center rounded-xl bg-[#0B6E4F] hover:bg-[#095940] text-white text-xs font-semibold">
          {t("back_home")}
        </Link>
        <Link href="/search" className="min-h-10 px-4 inline-flex items-center rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold">
          {t("search")}
        </Link>
      </div>
    </section>
  );
}
