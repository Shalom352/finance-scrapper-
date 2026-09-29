"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { SourceDocument } from "@/types";
import { MISSING } from "@/lib/formatters";

/** Documents actually referenced by the provenance of the displayed values — none is invented. */
export function SourcesList({ documents }: { documents: SourceDocument[] }) {
  const t = useTranslations("explorer");

  if (documents.length === 0) {
    return (
      <p className="text-xs text-gray-500" data-testid="sources-empty">
        {t("sources_empty")}
      </p>
    );
  }
  return (
    <ul className="divide-y divide-gray-800/60 rounded-2xl border border-gray-800 bg-gray-900/30 text-xs" data-testid="sources-list">
      {documents.map((d) => (
        <li key={d.document_id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2" data-testid="source-row">
          <span>
            <span className="font-semibold text-gray-200">{d.title || MISSING}</span>
            <span className="block text-gray-500">{d.source_name || MISSING}</span>
          </span>
          <span className="text-gray-400 text-right">
            {t("source_years", { years: d.period_years.join(", ") })}
            <span className="block">
              {d.pages.length > 0 ? t("source_pages", { pages: d.pages.join(", ") }) : t("source_pages_unknown")} ·{" "}
              {t("source_values", { count: d.values_count })}
            </span>
          </span>
        </li>
      ))}
    </ul>
  );
}
