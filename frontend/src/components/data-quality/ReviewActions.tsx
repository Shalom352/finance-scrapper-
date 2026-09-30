"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { ReviewAction } from "@/types";
import { ApiError, postReviewAction, type ReviewDecision } from "@/lib/api";
import { selectCls } from "@/components/rankings/IndicatorSelect";

const ACTIONS: ReviewAction[] = ["review", "verify", "reject"];

interface Props {
  dataId: string;
  /** Computed by the backend from the existing transitions; the backend checks again on submit. */
  allowed: ReviewAction[];
  expectedStatus: string;
  expectedUpdatedAt: string;
  onDone: () => void;
  /** Reload after a 409 (stale view); defaults to onDone. */
  onReload?: () => void;
  /** The previous decision succeeded: kept visible although the form remounts on the new state. */
  done?: boolean;
  /** Where the decision is sent (default: an observation of the Review Center). */
  submitAction?: (action: ReviewAction, decision: ReviewDecision) => Promise<unknown>;
}

type Outcome = { kind: "done" } | { kind: "error"; status: number } | null;

/** Human decision form: identifier + mandatory reason, confirmation, explicit error states. */
export function ReviewActions({ dataId, allowed, expectedStatus, expectedUpdatedAt, onDone, onReload, done = false, submitAction }: Props) {
  const t = useTranslations("data_quality.actions");
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [pending, setPending] = useState<ReviewAction | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<Outcome>(null);
  const ready = actor.trim() !== "" && reason.trim() !== "";

  const submit = async (action: ReviewAction) => {
    setBusy(true);
    try {
      const decision: ReviewDecision = {
        actor: actor.trim(),
        reason: reason.trim(),
        expected_status: expectedStatus,
        expected_updated_at: expectedUpdatedAt,
      };
      await (submitAction ? submitAction(action, decision) : postReviewAction(dataId, action, decision));
      setOutcome({ kind: "done" });
      setReason("");
      onDone();
    } catch (err) {
      setOutcome({ kind: "error", status: err instanceof ApiError ? err.status : 0 });
    } finally {
      setBusy(false);
      setPending(null);
    }
  };

  const errorKey = (status: number) => (status === 404 || status === 409 || status === 422 ? String(status) : "other");

  return (
    <section className="p-4 rounded-2xl border border-gray-800 bg-gray-900/40 space-y-3" data-testid="dq-actions">
      <h2 className="text-sm font-bold text-white">{t("title")}</h2>
      {allowed.length === 0 ? (
        <p className="text-xs text-gray-400" data-testid="dq-no-action">{t("not_allowed")}</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <label className="text-[11px] text-gray-400 font-medium">
            {t("actor")}
            <input value={actor} onChange={(e) => setActor(e.target.value)} placeholder={t("actor_placeholder")}
              className={selectCls} maxLength={255} />
          </label>
          <label className="text-[11px] text-gray-400 font-medium md:col-span-2">
            {t("reason")}
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder={t("reason_placeholder")}
              rows={2} className={selectCls} />
          </label>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        {ACTIONS.map((a) => (
          <button
            key={a}
            type="button"
            onClick={() => setPending(a)}
            disabled={!allowed.includes(a) || !ready || busy}
            data-testid={`dq-action-${a}`}
            className={`px-3 py-2 rounded-xl border text-xs font-semibold disabled:opacity-40 disabled:cursor-not-allowed ${
              a === "reject"
                ? "border-rose-800 text-rose-200 hover:bg-rose-950"
                : "border-gray-700 text-gray-200 hover:border-emerald-500"
            }`}
          >
            {t(a)}
          </button>
        ))}
      </div>
      {allowed.length > 0 && !ready && <p className="text-[11px] text-gray-500">{t("need_fields")}</p>}

      {pending && (
        <div role="alertdialog" aria-modal="true" aria-labelledby="dq-confirm-title" data-testid="dq-confirm"
          className="p-4 rounded-xl border border-amber-800/60 bg-amber-950/30 space-y-3">
          <p id="dq-confirm-title" className="text-sm font-semibold text-amber-100">{t("confirm_title")}</p>
          <p className="text-xs text-amber-200">{t(`confirm.${pending}`)}</p>
          <div className="flex gap-2">
            <button type="button" onClick={() => submit(pending)} disabled={busy} data-testid="dq-confirm-yes"
              className="px-3 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-semibold disabled:opacity-40">
              {t("confirm_yes")}
            </button>
            <button type="button" onClick={() => setPending(null)} data-testid="dq-confirm-no"
              className="px-3 py-1.5 rounded-lg bg-gray-800 text-gray-200 text-xs">
              {t("confirm_no")}
            </button>
          </div>
        </div>
      )}

      {(outcome?.kind === "done" || (done && outcome === null)) && <p className="text-xs text-emerald-300" data-testid="dq-done">{t("done")}</p>}
      {outcome?.kind === "error" && (
        <div role="alert" className="text-xs text-rose-200 space-y-1" data-testid="dq-error">
          <p>{t(`errors.${errorKey(outcome.status)}`)}</p>
          {outcome.status === 409 && (
            <button type="button" onClick={onReload ?? onDone} className="underline" data-testid="dq-reload">{t("reload")}</button>
          )}
        </div>
      )}
    </section>
  );
}
