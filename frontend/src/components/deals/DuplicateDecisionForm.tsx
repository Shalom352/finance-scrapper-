"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { DealDuplicate, DuplicateDecision } from "@/types";
import { ApiError, postDuplicateDecision } from "@/lib/api";
import { selectCls } from "@/components/rankings/IndicatorSelect";

const DECISIONS: DuplicateDecision[] = ["same_deal", "distinct_deals", "same_deal_multi_source"];

/** Human decision on one duplicate candidate: identifier + reason + confirmation. Never automatic. */
export function DuplicateDecisionForm({
  candidate,
  dealId,
  dealTitle,
  onDone,
}: {
  candidate: DealDuplicate;
  dealId: string;
  dealTitle: string;
  onDone: () => void;
}) {
  const t = useTranslations("deals.duplicates.decide");
  const ta = useTranslations("data_quality.actions");
  const [decision, setDecision] = useState<DuplicateDecision>("distinct_deals");
  const [primary, setPrimary] = useState(dealId);
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<number | null>(null);
  const ready = actor.trim() !== "" && reason.trim() !== "";
  const needsPrimary = decision !== "distinct_deals";

  const submit = async () => {
    setBusy(true);
    setError(null);
    try {
      await postDuplicateDecision(candidate.id, {
        decision,
        primary_deal_id: needsPrimary ? primary : undefined,
        actor: actor.trim(),
        reason: reason.trim(),
      });
      onDone();
    } catch (err) {
      setError(err instanceof ApiError ? err.status : 0);
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };

  const errorKey = (s: number) => (s === 404 || s === 409 || s === 422 ? String(s) : "other");

  return (
    <div className="mt-2 p-3 rounded-xl border border-gray-800 bg-gray-950/60 space-y-2" data-testid="dup-decide">
      <div className="text-xs font-semibold text-white">{t("title")}</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <label className="text-[11px] text-gray-400">
          {t("decision")}
          <select value={decision} onChange={(e) => setDecision(e.target.value as DuplicateDecision)} className={selectCls}
            data-testid="dup-decision">
            {DECISIONS.map((d) => <option key={d} value={d}>{t(d)}</option>)}
          </select>
        </label>
        {needsPrimary && (
          <label className="text-[11px] text-gray-400">
            {t("primary")}
            <select value={primary} onChange={(e) => setPrimary(e.target.value)} className={selectCls} data-testid="dup-primary">
              <option value={dealId}>{dealTitle}</option>
              <option value={candidate.other_deal_id}>{candidate.other_deal_title ?? candidate.other_deal_id}</option>
            </select>
          </label>
        )}
        <label className="text-[11px] text-gray-400">
          {ta("actor")}
          <input value={actor} onChange={(e) => setActor(e.target.value)} maxLength={255} placeholder={ta("actor_placeholder")}
            className={selectCls} data-testid="dup-actor" />
        </label>
        <label className="text-[11px] text-gray-400">
          {ta("reason")}
          <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder={ta("reason_placeholder")}
            className={selectCls} data-testid="dup-reason" />
        </label>
      </div>
      {!confirming ? (
        <button type="button" disabled={!ready || busy} onClick={() => setConfirming(true)} data-testid="dup-submit"
          className="px-3 py-1.5 rounded-lg border border-gray-700 text-xs text-gray-200 hover:border-emerald-500 disabled:opacity-40">
          {t("submit")}
        </button>
      ) : (
        <div role="alertdialog" aria-modal="true" aria-label={t("title")} className="p-3 rounded-lg border border-amber-800/60 bg-amber-950/30 space-y-2">
          <p className="text-xs text-amber-200">{t("confirm")}</p>
          <div className="flex gap-2">
            <button type="button" onClick={submit} disabled={busy} data-testid="dup-confirm-yes"
              className="px-3 py-1.5 rounded-lg bg-emerald-700 text-white text-xs font-semibold disabled:opacity-40">
              {ta("confirm_yes")}
            </button>
            <button type="button" onClick={() => setConfirming(false)} className="px-3 py-1.5 rounded-lg bg-gray-800 text-gray-200 text-xs">
              {ta("confirm_no")}
            </button>
          </div>
        </div>
      )}
      {!ready && <p className="text-[11px] text-gray-500">{ta("need_fields")}</p>}
      {error !== null && (
        <p role="alert" className="text-xs text-rose-200" data-testid="dup-error">{ta(`errors.${errorKey(error)}`)}</p>
      )}
    </div>
  );
}
