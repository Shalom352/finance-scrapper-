"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ReviewCenterCounts } from "@/types";
import { useFormatters } from "@/lib/useFormatters";

const KEYS = [
  "unresolved",
  "needs_review",
  "conflict_keys",
  "conflict_observations",
  "extracted",
  "reviewed",
  "verified",
  "rejected",
  "total",
] as const;

/** Deal counters (Phase 13), shown only when the backend returns them. */
const DEAL_KEYS = ["deals_needs_review", "deals_duplicate_candidates", "deals_verified"] as const;

/** Plain counts read from PostgreSQL. No rate, percentage or grade is derived from them. */
export function SummaryCounts({ counts }: { counts: ReviewCenterCounts }) {
  const t = useTranslations("data_quality.counts");
  const fmt = useFormatters();
  return (
    <section aria-label={t("title")} className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-9 gap-3" data-testid="dq-counts">
      {KEYS.map((k) => (
        <div key={k} className="p-3 rounded-xl border border-gray-800 bg-gray-900/40" data-testid={`dq-count-${k}`}>
          <div className="text-[11px] text-gray-400">{t(k)}</div>
          <div className="text-xl font-black text-white">{fmt.number(counts[k])}</div>
        </div>
      ))}
      {DEAL_KEYS.filter((k) => typeof counts[k] === "number").map((k) => (
        <div key={k} className="p-3 rounded-xl border border-gray-800 bg-gray-900/40" data-testid={`dq-count-${k}`}>
          <div className="text-[11px] text-gray-400">{t(k)}</div>
          <div className="text-xl font-black text-white">{fmt.number(counts[k])}</div>
        </div>
      ))}
    </section>
  );
}
