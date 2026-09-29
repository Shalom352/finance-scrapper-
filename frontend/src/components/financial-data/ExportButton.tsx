"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import { exportFinancialDataCsv, type FinancialDataExplorerQuery } from "@/lib/api";
import { EXPORT_MAX_ROWS } from "@/lib/financialData";

type ExportState = "idle" | "running" | "too_large" | "error";

/** CSV export of exactly the filtered rows (rejected excluded), bounded by the backend. */
export function ExportButton({ query, total }: { query: FinancialDataExplorerQuery; total: number | null }) {
  const t = useTranslations("data_explorer.export");
  const [state, setState] = useState<ExportState>("idle");
  const tooLarge = state === "too_large" || (total !== null && total > EXPORT_MAX_ROWS);

  const run = async () => {
    setState("running");
    try {
      const res = await exportFinancialDataCsv(query);
      if (res.status === "too_large") {
        setState("too_large");
        return;
      }
      const url = URL.createObjectURL(res.blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "financial-data.csv";
      a.click();
      URL.revokeObjectURL(url);
      setState("idle");
    } catch {
      setState("error");
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        type="button"
        onClick={run}
        disabled={tooLarge || total === 0 || state === "running"}
        className="px-3 py-2 rounded-xl border border-gray-700 bg-gray-900 text-xs font-semibold text-gray-200 hover:border-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed"
        data-testid="export-csv"
      >
        {state === "running" ? t("running") : t("button")}
      </button>
      {tooLarge && (
        <p className="text-[11px] text-amber-300" data-testid="export-too-large">
          {t("too_large", { max: EXPORT_MAX_ROWS })}
        </p>
      )}
      {state === "error" && <p className="text-[11px] text-rose-300">{t("error")}</p>}
    </div>
  );
}
