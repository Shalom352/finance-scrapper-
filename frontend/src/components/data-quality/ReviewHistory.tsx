"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ReviewEvent } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { StatusBadge } from "@/components/common/StatusBadge";

/** Audit trail of the human decisions on one observation or deal (append-only on the backend). */
export function ReviewHistory({ events }: { events: ReviewEvent[] }) {
  const t = useTranslations("data_quality.history");
  const tAction = useTranslations("data_quality.action_names");
  const fmt = useFormatters();
  const num = (v: number | null) => (v === null ? MISSING : fmt.number(v, Number.isInteger(v) ? 0 : 2));

  if (events.length === 0) return <p className="text-xs text-gray-500" data-testid="dq-history-empty">{t("empty")}</p>;
  return (
    <ol className="space-y-2" data-testid="dq-history">
      {events.map((e) => (
        <li key={e.id} className="p-3 rounded-xl border border-gray-800 bg-gray-900/40 text-xs" data-testid="dq-history-item">
          <div className="flex flex-wrap items-center gap-2 text-gray-300">
            {/* An unknown action code is shown as recorded, never guessed. */}
            <span className="font-semibold text-white">{tAction.has(e.action) ? tAction(e.action) : e.action}</span>
            {e.previous_status === "none" ? (
              <span className="text-gray-500">{t("created")}</span>
            ) : (
              <StatusBadge status={e.previous_status} size="sm" />
            )}
            <span aria-hidden="true">→</span>
            <StatusBadge status={e.new_status} size="sm" />
            <span className="text-gray-400">{t("by", { actor: e.actor ?? t("unknown_actor") })}</span>
            <span className="text-gray-500">{fmt.date(e.created_at)}</span>
          </div>
          {e.reason && <p className="mt-1 text-gray-300 italic">{e.reason}</p>}
          {e.previous_status !== "none" && e.value_before !== e.value_after && (
            <p className="mt-1 text-amber-300">{t("value_change", { before: num(e.value_before), after: num(e.value_after) })}</p>
          )}
        </li>
      ))}
    </ol>
  );
}
