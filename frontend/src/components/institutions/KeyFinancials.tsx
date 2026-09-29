"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { InstitutionFinancials } from "@/types";
import { MISSING, displayCurrency } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { useLabels } from "@/lib/useLabels";
import { StatusBadge } from "@/components/common/StatusBadge";
import { useReasonLabel } from "@/components/rankings/ReasonLabel";

const PRIORITY = [
  "total_actifs",
  "depots_clients",
  "creances_clients",
  "capitaux_propres",
  "produit_net_bancaire",
  "resultat_net",
];

/** Key figures of the selected year: a qualified value, or an explicit reason — never a number by default. */
export function KeyFinancials({
  financials,
  onProvenance,
}: {
  financials: InstitutionFinancials;
  onProvenance: (dataId: string) => void;
}) {
  const t = useTranslations("explorer");
  const fmt = useFormatters();
  const labels = useLabels();
  const reason = useReasonLabel();

  return (
    <section className="space-y-2" data-testid="key-financials">
      <h2 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
        {financials.period_year === null ? t("key_title_none") : t("key_title", { year: financials.period_year })}
      </h2>
      {financials.period_year === null && (
        <p className="text-xs text-gray-500" data-testid="key-unavailable">
          {reason(financials.reason)}
        </p>
      )}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {PRIORITY.map((code) => {
          const v = financials.values.find((x) => x.metric_code === code);
          const u = financials.unavailable.find((x) => x.metric_code === code);
          return (
            <div key={code} className="p-4 rounded-2xl border border-gray-800 bg-gray-900/30" data-testid={`key-${code}`}>
              <span className="text-[11px] text-gray-400 font-medium block mb-1">{labels.metric(code)}</span>
              {v ? (
                <>
                  <span className="text-lg font-black text-white block">{fmt.compact(v.value_normalized, v.currency)}</span>
                  <span className="flex items-center justify-between mt-1 text-[11px] text-gray-500">
                    <span>{displayCurrency(v.currency) || MISSING}</span>
                    <button
                      onClick={() => onProvenance(v.data_id)}
                      className="text-emerald-400 hover:text-emerald-300"
                      title={t("open_provenance")}
                      data-testid="key-provenance"
                    >
                      🔍
                    </button>
                  </span>
                </>
              ) : (
                <>
                  <span className="text-lg font-black text-gray-500 block">{MISSING}</span>
                  <span className="text-[11px] text-gray-500 block mt-1">{reason(u?.reason ?? "missing")}</span>
                  {u && u.status !== "unavailable" && <StatusBadge status={u.status} size="sm" className="mt-1" />}
                </>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
