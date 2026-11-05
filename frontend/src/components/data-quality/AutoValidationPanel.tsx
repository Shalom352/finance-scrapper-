"use client";

import React, { useState } from "react";
import { useTranslations } from "next-intl";
import type { AutoValidation } from "@/types";
import { postRevokeAutomatic } from "@/lib/api";

const TONE: Record<string, string> = {
  pass: "text-emerald-700",
  fail: "text-rose-700",
  skip: "text-gray-500",
  info: "text-gray-500",
};

interface Props {
  kind: "observation" | "deal";
  id: string;
  status: string;
  method: "human" | "automatic" | null | undefined;
  report: AutoValidation | null | undefined;
  blocked: boolean | undefined;
  onDone: () => void;
}

/** Phase 21 — what the robot checked, and the human switch to withdraw its decision. */
export function AutoValidationPanel({ kind, id, status, method, report, blocked, onDone }: Props) {
  const t = useTranslations("auto_validation");
  const [open, setOpen] = useState(false);
  const [actor, setActor] = useState("");
  const [reason, setReason] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  if (!report) return null;
  const automatic = method === "automatic";
  const headline = automatic
    ? t(status === "verified" ? "automatic_verified" : "automatic_reviewed")
    : blocked && report.revoked_by
      ? t("blocked", { actor: report.revoked_by })
      : t("not_validated");

  const submit = async () => {
    setState("busy");
    try {
      await postRevokeAutomatic(kind, id, { actor: actor.trim(), reason: reason.trim(), expected_status: status });
      setState("done");
      onDone();
    } catch {
      setState("error");
    }
  };

  return (
    <section className="p-4 rounded-2xl border border-sky-200 bg-sky-50 space-y-2 text-xs" data-testid="auto-validation">
      <h2 className="text-sm font-bold text-sky-700">{t("title")}</h2>
      <p className={automatic ? "text-sky-700" : "text-gray-700"} data-testid="auto-validation-headline">{headline}</p>
      <p className="text-gray-500">{t("ruleset", { ruleset: report.ruleset, date: report.checked_at.slice(0, 10) })}</p>
      <ul className="space-y-0.5">
        {report.checks.map((c) => (
          <li key={c.check} data-testid={`auto-check-${c.check}`}>
            <span className={TONE[c.result]}>{t(`result.${c.result}`)}</span> · {t(`checks.${c.check}`)}
            {c.detail && <span className="text-gray-500"> — {c.detail}</span>}
          </li>
        ))}
      </ul>
      {automatic && state !== "done" && (
        !open ? (
          <button type="button" onClick={() => setOpen(true)} data-testid="auto-revoke-open"
                  className="min-h-10 px-3 py-1.5 rounded-lg border border-rose-200 text-rose-700 hover:bg-rose-50">
            {t("revoke")}
          </button>
        ) : (
          <div className="space-y-2" data-testid="auto-revoke-form">
            <p className="text-gray-500">{t("revoke_hint")}</p>
            <input className="w-full bg-white border border-gray-200 rounded-lg px-2 py-1.5 text-gray-900"
                   placeholder={t("actor")} value={actor} onChange={(e) => setActor(e.target.value)}
                   data-testid="auto-revoke-actor" />
            <textarea className="w-full bg-white border border-gray-200 rounded-lg px-2 py-1.5 text-gray-900"
                      placeholder={t("reason")} value={reason} onChange={(e) => setReason(e.target.value)}
                      data-testid="auto-revoke-reason" />
            <div className="flex gap-2">
              <button type="button" disabled={!actor.trim() || !reason.trim() || state === "busy"} onClick={submit}
                      data-testid="auto-revoke-confirm"
                      className="min-h-10 px-3 py-1.5 rounded-lg bg-rose-800 text-white disabled:opacity-40">{t("confirm")}</button>
              <button type="button" onClick={() => setOpen(false)} className="min-h-10 px-3 py-1.5 rounded-lg border border-gray-300 text-gray-700">
                {t("cancel")}
              </button>
            </div>
          </div>
        )
      )}
      {state === "done" && <p className="text-emerald-700" data-testid="auto-revoke-done">{t("done")}</p>}
      {state === "error" && <p className="text-rose-700" role="alert">{t("error")}</p>}
    </section>
  );
}
