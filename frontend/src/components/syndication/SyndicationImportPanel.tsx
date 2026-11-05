"use client";

import React, { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { ConflictDecision, SyndicationImport } from "@/types";
import {
  ApiError,
  applySyndicationImport,
  listSyndicationImports,
  previewSyndicationImport,
} from "@/lib/api";

const btn = "min-h-10 px-4 rounded-xl text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed";
const fieldCls =
  "w-full min-h-10 px-3 rounded-xl border border-gray-200 bg-white text-sm text-gray-800 focus:border-emerald-600 focus:outline-none";

function show(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") {
    const v = value as Record<string, unknown>;
    return [v.stage, v.amount_text, v.rate_text].filter(Boolean).join(" · ") || JSON.stringify(value);
  }
  return String(value);
}

/**
 * Settings → import of the syndication Excel. Upload → plan (nothing written) → map the detail sheets
 * → choose, for every conflict, the platform or the Excel value → apply. Nothing is overwritten silently.
 */
export function SyndicationImportPanel() {
  const t = useTranslations("syndication.import");
  const [file, setFile] = useState<File | null>(null);
  const [plan, setPlan] = useState<SyndicationImport | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, ConflictDecision>>({});
  const [state, setState] = useState<"idle" | "busy" | "applied" | "error">("idle");
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<SyndicationImport[]>([]);

  useEffect(() => {
    listSyndicationImports().then(setHistory).catch(() => setHistory([]));
  }, [state]);

  const runPreview = async (map: Record<string, string>) => {
    if (!file) return;
    setState("busy");
    setError(null);
    try {
      const res = await previewSyndicationImport(file, map);
      setPlan(res);
      setDecisions({});
      setState("idle");
    } catch (err) {
      setState("error");
      setError(err instanceof ApiError && err.status === 409 ? t("already_imported") : t("preview_error"));
    }
  };

  const conflicts = plan?.conflicts ?? [];
  const undecided = conflicts.filter((c) => !decisions[c.id]).length;
  const apply = async () => {
    if (!plan) return;
    setState("busy");
    try {
      await applySyndicationImport(plan.id, decisions);
      setPlan(null);
      setFile(null);
      setState("applied");
    } catch {
      setState("error");
      setError(t("apply_error"));
    }
  };

  return (
    <section className="p-4 sm:p-5 rounded-2xl border border-gray-200/90 bg-white shadow-xs space-y-4" data-testid="syndication-import">
      <div>
        <h2 className="text-base font-bold text-gray-900">{t("title")}</h2>
        <p className="text-xs text-gray-500 mt-1">{t("hint")}</p>
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs font-medium text-gray-600 min-w-0 flex-1">
          {t("file")}
          <input type="file" accept=".xlsx,.xlsm" className="text-sm" data-testid="syndication-file"
            onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPlan(null); setMapping({}); }} />
        </label>
        <button type="button" disabled={!file || state === "busy"} onClick={() => runPreview(mapping)}
          className={`${btn} border border-gray-300 bg-white text-gray-700 hover:bg-gray-50`} data-testid="syndication-preview">
          {t("preview")}
        </button>
      </div>

      {state === "applied" && <p className="text-xs text-emerald-700" role="status">{t("applied")}</p>}
      {error && <p className="text-xs text-rose-700" role="alert">{error}</p>}

      {plan && (
        <div className="space-y-4" data-testid="syndication-plan">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
            {(["mandates", "events", "contacts"] as const).map((k) => (
              <div key={k} className="p-3 rounded-xl border border-gray-200 bg-gray-50">
                <div className="font-semibold text-gray-800">{t(`counts.${k}`)}</div>
                <div className="text-gray-600">
                  {Object.entries(plan.counts?.[k] ?? {}).map(([a, n]) => `${t(`actions.${a}`)} ${n}`).join(" · ")}
                </div>
              </div>
            ))}
            <div className="p-3 rounded-xl border border-gray-200 bg-gray-50">
              <div className="font-semibold text-gray-800">{t("counts.file_date")}</div>
              <div className="text-gray-600">{plan.file_updated_on ?? t("not_set")}</div>
            </div>
          </div>

          {Object.keys(plan.detail_sheets ?? {}).length > 0 && (
            <div className="space-y-2" data-testid="syndication-detail-sheets">
              <h3 className="text-sm font-semibold text-gray-900">{t("detail_sheets")}</h3>
              <p className="text-xs text-gray-500">{t("detail_sheets_hint")}</p>
              {Object.entries(plan.detail_sheets ?? {}).map(([sheet, code]) => (
                <label key={sheet} className="flex flex-col sm:flex-row sm:items-center gap-2 text-xs">
                  <span className="font-medium text-gray-700 sm:w-56 break-words">{sheet}</span>
                  <select className={fieldCls} value={mapping[sheet] ?? code ?? ""}
                    onChange={(e) => setMapping({ ...mapping, [sheet]: e.target.value })}>
                    <option value="">{t("not_mapped")}</option>
                    {(plan.mandates ?? []).map((m) => <option key={m.code} value={m.code}>{m.title}</option>)}
                  </select>
                </label>
              ))}
              <button type="button" className={`${btn} border border-gray-300 bg-white text-gray-700`}
                onClick={() => runPreview(mapping)} disabled={state === "busy"}>
                {t("recompute")}
              </button>
            </div>
          )}

          {plan.unresolved_names && plan.unresolved_names.length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer font-semibold text-amber-700">
                {t("unresolved", { count: plan.unresolved_names.length })}
              </summary>
              <p className="text-gray-500 mt-1">{t("unresolved_hint")}</p>
              <p className="text-gray-700 mt-1">{plan.unresolved_names.join(" · ")}</p>
            </details>
          )}

          {conflicts.length > 0 && (
            <div className="space-y-2" data-testid="syndication-conflicts">
              <h3 className="text-sm font-semibold text-gray-900">{t("conflicts", { count: conflicts.length })}</h3>
              <p className="text-xs text-gray-500">{t("conflicts_hint")}</p>
              {conflicts.map((c) => (
                <div key={c.id} className="p-3 rounded-xl border border-amber-200 bg-amber-50 text-xs space-y-1">
                  <div className="font-semibold text-gray-900">{c.label} — {c.field}</div>
                  <div className="flex flex-wrap gap-4">
                    {(["platform", "excel"] as const).map((side) => (
                      <label key={side} className="flex items-center gap-2 cursor-pointer">
                        <input type="radio" name={c.id} checked={decisions[c.id] === side}
                          onChange={() => setDecisions({ ...decisions, [c.id]: side })} />
                        <span>{t(`keep_${side}`)} : <strong>{show(side === "platform" ? c.platform : c.excel_now)}</strong></span>
                      </label>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}

          <button type="button" disabled={undecided > 0 || state === "busy"} onClick={apply}
            className={`${btn} bg-emerald-600 hover:bg-emerald-700 text-white`} data-testid="syndication-apply">
            {undecided > 0 ? t("decide_first", { count: undecided }) : t("apply")}
          </button>
        </div>
      )}

      {history.length > 0 && (
        <div className="overflow-x-auto">
          <table className="w-full text-xs" data-testid="syndication-history">
            <thead>
              <tr className="text-left text-gray-500">
                <th className="py-1 pr-3">{t("history.file")}</th>
                <th className="py-1 pr-3">{t("history.file_date")}</th>
                <th className="py-1 pr-3">{t("history.status")}</th>
                <th className="py-1 pr-3">{t("history.actor")}</th>
              </tr>
            </thead>
            <tbody>
              {history.slice(0, 10).map((h) => (
                <tr key={h.id} className="border-t border-gray-100">
                  <td className="py-1 pr-3 break-all">{h.file_name}</td>
                  <td className="py-1 pr-3">{h.file_updated_on ?? "—"}</td>
                  <td className="py-1 pr-3">{t(`status.${h.status}`)}</td>
                  <td className="py-1 pr-3">{h.actor}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
