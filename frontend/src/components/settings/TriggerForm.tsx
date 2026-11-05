"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import {
  DEAL_SOURCES,
  FINANCIAL_SOURCES,
  INGESTION_SCOPES,
  INGESTION_SOURCES,
  triggerIngestion,
  type IngestionScope,
  type IngestionSource,
} from "@/lib/api";

interface TriggerFormProps {
  /** A run is in progress: launching is disabled (the backend would skip a concurrent run). */
  busy: boolean;
  onStarted: (runId: string | null) => void;
}

const fieldCls =
  "w-full min-h-10 px-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 focus:border-emerald-600 focus:ring-1 focus:ring-emerald-500 focus:outline-none";

export function TriggerForm({ busy, onStarted }: TriggerFormProps) {
  const t = useTranslations("settings.trigger");
  const tSrc = useTranslations("settings.sources");
  const [source, setSource] = useState<IngestionSource>("all");
  const [scope, setScope] = useState<IngestionScope>("all");
  const [since, setSince] = useState("");
  const [until, setUntil] = useState("");
  const [year, setYear] = useState("");
  const [limit, setLimit] = useState("");
  const [force, setForce] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [state, setState] = useState<"idle" | "sending" | "started" | "error">("idle");

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: currentYear - 1899 }, (_, index) => currentYear - index);
  const yearNum = year ? Number(year) : null;
  const limitNum = limit ? Number(limit) : null;
  const yearInvalid = yearNum !== null && (!years.includes(yearNum) || !Number.isInteger(yearNum));
  const limitInvalid = limitNum !== null && !(Number.isInteger(limitNum) && limitNum >= 1 && limitNum <= 100);
  const datesInvalid = scope !== "financial" && Boolean(since && until && since > until);
  // A deal-only source (IFC...) has no bank-statement collection, and the reverse (the backend says 422).
  const scopeUnavailable =
    source !== "all" &&
    ((scope === "financial" && !FINANCIAL_SOURCES.includes(source)) || (scope === "deals" && !DEAL_SOURCES.includes(source)));
  const invalid = yearInvalid || limitInvalid || datesInvalid || scopeUnavailable;

  const period = yearNum !== null ? String(yearNum) : t("configured_period");

  const launch = async () => {
    setState("sending");
    try {
      const annualStart = yearNum === null || scope === "financial" ? null : `${yearNum}-01-01`;
      const annualEnd = yearNum === null || scope === "financial" ? null : `${yearNum}-12-31`;
      const res = await triggerIngestion({
        source,
        scope,
        since: annualStart ?? (since || null),
        until: annualEnd ?? (until || null),
        year: yearNum,
        limit: limitNum,
        force,
      });
      setState("started");
      setConfirming(false);
      onStarted(res.run_id);
    } catch {
      setState("error");
      setConfirming(false);
    }
  };

  return (
    <section className="p-4 sm:p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs space-y-4" data-testid="trigger-form" data-guide="settings">
      <h2 className="text-base font-bold text-gray-900">{t("title")}</h2>

      <form
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3"
        onSubmit={(e) => {
          e.preventDefault();
          if (!busy && !invalid) setConfirming(true);
        }}
      >
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
          {t("source")}
          <select className={fieldCls} value={source} onChange={(e) => setSource(e.target.value as IngestionSource)} data-testid="trigger-source">
            {INGESTION_SOURCES.map((s) => (
              <option key={s} value={s}>{tSrc(s)}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
          {t("scope")}
          <select className={fieldCls} value={scope} onChange={(e) => setScope(e.target.value as IngestionScope)}
            aria-invalid={scopeUnavailable} data-testid="trigger-scope">
            {INGESTION_SCOPES.map((s) => (
              <option key={s} value={s}>{t(`scope_${s}`)}</option>
            ))}
          </select>
          {scopeUnavailable && <span className="text-rose-700">{t("scope_not_available")}</span>}
        </label>
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
          {t("year")}
          <select className={fieldCls} value={year} onChange={(e) => setYear(e.target.value)} aria-invalid={yearInvalid} data-testid="trigger-year">
            <option value="">{t("year_hint")}</option>
            {years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          {yearInvalid && <span className="text-rose-700">{t("invalid_year")}</span>}
        </label>
        {scope !== "financial" && yearNum !== null && (
          <p className="flex items-center rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2 text-xs text-emerald-800" data-testid="trigger-year-range">
            {t("year_range", { year: yearNum })}
          </p>
        )}
        {scope !== "financial" && yearNum === null && (
          <>
            <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
              {t("since")}
              <input type="date" className={fieldCls} value={since} onChange={(e) => setSince(e.target.value)}
                placeholder={t("since_hint")} data-testid="trigger-since" />
            </label>
            <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
              {t("until")}
              <input type="date" className={fieldCls} value={until} onChange={(e) => setUntil(e.target.value)}
                placeholder={t("since_hint")} data-testid="trigger-until" />
            </label>
            {datesInvalid && <p className="text-xs text-rose-700" role="alert">{t("invalid_dates")}</p>}
          </>
        )}
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600">
          {t("limit")}
          <input
            type="number" inputMode="numeric" min={1} max={100} placeholder={t("limit_hint")}
            className={fieldCls} value={limit} onChange={(e) => setLimit(e.target.value)} aria-invalid={limitInvalid}
            data-testid="trigger-limit"
          />
          {limitInvalid && <span className="text-rose-700">{t("invalid_limit")}</span>}
        </label>
        <label className="sm:col-span-2 lg:col-span-3 flex items-start gap-2.5 min-h-10 py-2 text-sm text-gray-700 cursor-pointer">
          <input type="checkbox" className="mt-0.5 w-5 h-5 shrink-0 accent-emerald-600" checked={force} onChange={(e) => setForce(e.target.checked)} />
          <span>{t("force")}</span>
        </label>

        <div className="sm:col-span-2 lg:col-span-3 flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy || invalid || state === "sending" || confirming}
            className="min-h-10 px-5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold shadow-xs disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            data-testid="trigger-submit"
          >
            {t("submit")}
          </button>
          {busy && <p className="text-xs text-amber-700">{t("running_block")}</p>}
          {state === "started" && !busy && <p className="text-xs text-emerald-700" role="status">{t("started")}</p>}
          {state === "error" && <p className="text-xs text-rose-700" role="alert">{t("error")}</p>}
        </div>
      </form>

      {confirming && (
        <div className="p-4 rounded-xl border border-amber-200 bg-amber-50 space-y-3" role="alertdialog" aria-labelledby="trigger-confirm-title" data-testid="trigger-confirm">
          <p id="trigger-confirm-title" className="text-sm font-semibold text-gray-900">{t("confirm_title")}</p>
          <p className="text-xs text-gray-700">{t("confirm_body", { source: tSrc(source), scope: t(`scope_${scope}`), period })}</p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button" onClick={launch} disabled={state === "sending"}
              className="min-h-10 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-semibold disabled:opacity-40"
              data-testid="trigger-confirm-yes"
            >
              {t("confirm")}
            </button>
            <button
              type="button" onClick={() => setConfirming(false)}
              className="min-h-10 px-4 rounded-xl border border-gray-300 bg-white text-gray-700 text-sm font-medium hover:bg-gray-50"
            >
              {t("cancel")}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
