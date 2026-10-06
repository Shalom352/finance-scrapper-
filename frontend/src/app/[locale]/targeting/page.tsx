"use client";

import React, { Suspense, useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { TargetingResponse } from "@/types";
import { DEAL_TYPES, SECTORS } from "@/types";
import { CURRENCIES, KINDS, parseTargetingParams } from "@/lib/targeting";
import { getTargeting } from "@/lib/api";
import { useQueryParams } from "@/lib/useQueryParams";
import { UMOA_COUNTRY_CODES } from "@/lib/countries";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { TargetingResults } from "@/components/targeting/TargetingResults";

export default function TargetingPage() {
  return (
    <Suspense fallback={<TableSkeleton rows={8} cols={6} />}>
      <TargetingContent />
    </Suspense>
  );
}

type Load = { status: "idle" } | { status: "loading" } | { status: "error" } | { status: "ready"; data: TargetingResponse };
function TargetingContent() {
  const t = useTranslations("targeting");
  const tTypes = useTranslations("deals.types");
  const tCountries = useTranslations("country_names");
  const { get, set } = useQueryParams();
  const query = parseTargetingParams(get);
  const key = JSON.stringify(query);
  const ready = Boolean(query.country || query.sector || query.deal_type);
  const [result, setResult] = useState<Load>({ status: "idle" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    setResult({ status: "loading" });
    getTargeting(query)
      .then((data) => !cancelled && setResult({ status: "ready", data }))
      .catch(() => !cancelled && setResult({ status: "error" }));
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- key is the stable form of query
  }, [key, reload, ready]);

  const select = (name: string, value: string | undefined, options: { value: string; label: string }[]) => (
    <label className="flex flex-col gap-1 text-xs text-gray-400">
      {t(`form.${name}`)}
      <select
        className="bg-gray-900 border border-gray-800 rounded-lg px-2 py-1.5 text-gray-100"
        value={value ?? ""}
        onChange={(e) => set({ [name]: e.target.value || null })}
        data-testid={`targeting-${name}`}
      >
        <option value="">{t("form.any")}</option>
        {options.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </label>
  );

  return (
    <div className="space-y-6 animate-fade-in pb-12">
      <div>
        <h1 className="text-2xl md:text-3xl font-black text-white tracking-tight">{t("title")}</h1>
        <p className="text-xs text-gray-400 mt-1">{t("subtitle")}</p>
      </div>

      <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 grid grid-cols-1 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {select("country", query.country, UMOA_COUNTRY_CODES.map((c) => ({ value: c, label: tCountries(c) })))}
        {select("sector", query.sector, SECTORS.map((s) => ({ value: s, label: t(`sectors.${s}`) })))}
        {select("deal_type", query.deal_type, DEAL_TYPES.map((d) => ({ value: d, label: tTypes(d) })))}
        <label className="flex flex-col gap-1 text-xs text-gray-400">
          {t("form.amount")}
          <input
            type="number"
            min={0}
            className="bg-gray-900 border border-gray-800 rounded-lg px-2 py-1.5 text-gray-100"
            defaultValue={query.amount ?? ""}
            onBlur={(e) => set({ amount: e.target.value || null })}
            data-testid="targeting-amount"
          />
        </label>
        {select("currency", query.currency, CURRENCIES.map((c) => ({ value: c, label: c })))}
        {select("kind", query.kind, KINDS.filter((k) => k !== "all").map((k) => ({ value: k, label: t(`kinds.${k}`) })))}
      </section>

      {!ready ? (
        <EmptyState title={t("start_title")} description={t("start_hint")} icon="🎯" />
      ) : result.status === "loading" || result.status === "idle" ? (
        <TableSkeleton rows={8} cols={6} />
      ) : result.status === "error" ? (
        <ErrorState onRetry={() => setReload((n) => n + 1)} />
      ) : result.data.items.length === 0 ? (
        <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="🎯" />
      ) : (
        <section className="space-y-3">
          <p className="text-[11px] text-gray-500" data-testid="targeting-method">{t("method")}</p>
          <p className="text-xs text-gray-400" data-testid="targeting-count">{t("count", { total: result.data.total })}</p>
          <TargetingResults items={result.data.items} />
        </section>
      )}
    </div>
  );
}

