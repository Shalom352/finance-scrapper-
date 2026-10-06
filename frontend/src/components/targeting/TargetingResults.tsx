"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { Criterion, CriterionKey, TargetingCandidate, TargetingDeal } from "@/types";
import { Link } from "@/i18n/navigation";
import { useFormatters } from "@/lib/useFormatters";

const KEYS: CriterionKey[] = ["presence", "experience", "capacity", "relationship", "via_sgi"];
const TONE: Record<string, string> = {
  met: "bg-emerald-900/60 text-emerald-200 border-emerald-700/60",
  not_met: "bg-gray-800 text-gray-300 border-gray-700",
  unknown: "bg-gray-900 text-gray-500 border-gray-800 border-dashed",
};

function Badge({ k, c }: { k: CriterionKey; c: Criterion }) {
  const t = useTranslations("targeting");
  return (
    <span className={`px-2 py-0.5 rounded-full border text-[10px] ${TONE[c.status]}`} data-testid={`criterion-${k}`}
          data-status={c.status}>
      {t(`criteria.${k}`)} · {t(`status.${c.status}`)}
    </span>
  );
}

function DealList({ deals }: { deals: TargetingDeal[] }) {
  const t = useTranslations("targeting");
  const tRoles = useTranslations("deals.roles");
  const fmt = useFormatters();
  return (
    <ul className="space-y-1">
      {deals.map((d) => (
        <li key={d.deal_id}>
          <Link href={`/deals/${d.deal_id}`} className="text-emerald-300 hover:underline">{d.title}</Link>
          <span className="text-gray-500">
            {" "}· {d.roles.map((r) => tRoles(r)).join(", ")}
            {d.year !== null && <> · {d.year}</>}
            {d.amount !== null && d.currency && <> · {fmt.number(d.amount)} {d.unit && d.unit !== "units" ? d.unit : ""} {d.currency}</>}
            {" "}· {d.matches.map((m) => t(`matches.${m}`)).join(" + ")}
            {d.status !== "reviewed" && d.status !== "verified" && <> · {t("to_confirm")}</>}
          </span>
        </li>
      ))}
    </ul>
  );
}

function Evidence({ k, c }: { k: CriterionKey; c: Criterion }) {
  const t = useTranslations("targeting");
  const fmt = useFormatters();
  if (c.status === "unknown") return <p className="text-gray-500">{t(`reasons.${c.reason ?? "unknown"}`)}</p>;
  if (k === "experience" || k === "via_sgi") {
    return (
      <div className="space-y-1">
        {k === "via_sgi" && <p className="text-gray-400">{t("via_sgi_detail", { sgi: String(c.sgi) })}</p>}
        <p className="text-gray-400">{t("experience_detail", { comparable: Number(c.comparable_deals), total: Number(c.financing_deals) })}</p>
        <DealList deals={(c.deals as TargetingDeal[]) ?? []} />
      </div>
    );
  }
  if (k === "capacity") {
    return (
      <p className="text-gray-300">
        {t("capacity_detail", {
          ceiling: fmt.number(Number(c.indicative_ceiling)), currency: String(c.currency),
          ratio: Math.round(Number(c.ratio) * 100), year: Number(c.equity_year),
        })}
        {Boolean(c.to_confirm) && <span className="text-amber-300"> · {t("to_confirm")}</span>}
        <span className="block text-gray-500">{t("capacity_caveat")}</span>
      </p>
    );
  }
  if (k === "relationship") {
    const history = (c.history as { mandate_code: string; mandate_title: string; stage: string }[]) ?? [];
    return (
      <ul className="space-y-0.5">
        {history.map((h) => (
          <li key={h.mandate_code} className="text-gray-300">{h.mandate_title} ({h.mandate_code}) · {t(`stages.${h.stage}`)}</li>
        ))}
      </ul>
    );
  }
  return <p className="text-gray-300">{c.status === "met" ? t("presence_met") : t("presence_not_met")}</p>;
}

export function TargetingResults({ items }: { items: TargetingCandidate[] }) {
  const t = useTranslations("targeting");
  const tCountries = useTranslations("country_names");
  return (
    <ul className="space-y-2">
      {items.map((c) => (
        <li key={`${c.kind}-${c.id}`} className="p-3 rounded-xl border border-gray-800 bg-gray-950/40 text-xs" data-testid="targeting-candidate">
          <details>
            <summary className="cursor-pointer list-none flex flex-wrap items-center gap-2">
              <span className="font-semibold text-gray-100">
                {c.kind === "bank" ? <Link href={`/institutions/${c.id}`} className="hover:underline">{c.name}</Link> : c.name}
              </span>
              <span className="text-gray-500">
                {t(`kinds_one.${c.kind}`)}
                {c.country_code && <> · {tCountries(c.country_code)}</>}
              </span>
              <span className="text-gray-400" data-testid="criteria-met">{t("criteria_met", { met: c.criteria_met, known: c.criteria_known })}</span>
              <span className="flex flex-wrap gap-1">
                {KEYS.filter((k) => c.criteria[k]).map((k) => <Badge key={k} k={k} c={c.criteria[k] as Criterion} />)}
              </span>
            </summary>
            <dl className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
              {KEYS.filter((k) => c.criteria[k]).map((k) => (
                <div key={k}>
                  <dt className="text-gray-500">{t(`criteria.${k}`)}</dt>
                  <dd><Evidence k={k} c={c.criteria[k] as Criterion} /></dd>
                </div>
              ))}
            </dl>
            {c.website && (
              <a href={c.website} target="_blank" rel="noreferrer" className="inline-block mt-2 text-emerald-400 hover:underline">
                {t("official_site")} ↗
              </a>
            )}
          </details>
        </li>
      ))}
    </ul>
  );
}
