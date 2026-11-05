"use client";

import { useEffect } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";

/** Unexpected rendering error of a page: retry or go back, the shell stays usable. */
export default function PageError({ error, retry }: { error: Error & { digest?: string }; retry: () => void }) {
  const t = useTranslations("errors");
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <section className="p-8 rounded-2xl border border-rose-200 bg-rose-50/60 text-center space-y-3" role="alert">
      <h1 className="text-xl font-bold text-gray-900">{t("error_title")}</h1>
      <p className="text-sm text-gray-600">{t("error_body")}</p>
      {error.digest && <p className="text-[11px] text-gray-400">{t("reference", { digest: error.digest })}</p>}
      <div className="flex flex-wrap justify-center gap-2 pt-2">
        <button type="button" onClick={() => retry()}
          className="min-h-10 px-4 rounded-xl bg-[#0B6E4F] hover:bg-[#095940] text-white text-xs font-semibold">
          {t("retry")}
        </button>
        <Link href="/" className="min-h-10 px-4 inline-flex items-center rounded-xl border border-gray-200 bg-white hover:bg-gray-50 text-gray-700 text-xs font-semibold">
          {t("back_home")}
        </Link>
      </div>
    </section>
  );
}
