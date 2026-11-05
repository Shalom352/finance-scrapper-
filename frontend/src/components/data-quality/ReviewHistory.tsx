"use client";

import React from "react";
import { useTranslations } from "next-intl";
import type { ReviewEvent } from "@/types";
import { MISSING } from "@/lib/formatters";
import { useFormatters } from "@/lib/useFormatters";
import { StatusBadge } from "@/components/common/StatusBadge";
import { SortSelect } from "@/components/common/SortHeader";
import { dateKey, useSort } from "@/lib/useSort";

/** Audit trail of the human decisions on one observation or deal (append-only on the backend). */
export function ReviewHistory({ events }: { events: ReviewEvent[] }) {
  const t = useTranslations("data_quality.history");
  const tAction = useTranslations("data_quality.action_names");
  const fmt = useFormatters();
  const tSort = useTranslations("common.sort");
  const num = (v: number | null) => (v === null ? MISSING : fmt.number(v, Number.isInteger(v) ? 0 : 2));
  const action = (e: ReviewEvent) => (tAction.has(e.action) ? tAction(e.action) : e.action);
  // Newest decision first by default; the trail itself stays append-only.
  const { sorted, sortKey, dir, setSort } = useSort(
    events,
    { date: (e) => dateKey(e.created_at), action, status: (e) => e.new_status },
    { key: "date", dir: "desc" },
  );

  if (events.length === 0) return <p className="text-xs text-gray-500" data-testid="dq-history-empty">{t("empty")}</p>;
  return (
    <div className="space-y-2">
    {events.length > 1 && (
      <SortSelect
        options={[
          { key: "date", label: t("sort_date") },
          { key: "action", label: t("sort_action") },
          { key: "status", label: t("sort_status") },
        ]}
        sortKey={sortKey} dir={dir} onChange={setSort}
        label={tSort("label")} ascLabel={tSort("asc")} descLabel={tSort("desc")} testId="dq-history-sort"
      />
    )}
    <ol className="space-y-2" data-testid="dq-history">
      {sorted.map((e) => (
        <li key={e.id} className="p-3 rounded-xl border border-gray-200 bg-white text-xs" data-testid="dq-history-item">
          <div className="flex flex-wrap items-center gap-2 text-gray-700">
            {/* An unknown action code is shown as recorded, never guessed. */}
            <span className="font-semibold text-gray-900">{action(e)}</span>
            {e.previous_status === "none" ? (
              <span className="text-gray-500">{t("created")}</span>
            ) : (
              <StatusBadge status={e.previous_status} size="sm" />
            )}
            <span aria-hidden="true">→</span>
            <StatusBadge status={e.new_status} size="sm" />
            <span className="text-gray-500">{t("by", { actor: e.actor ?? t("unknown_actor") })}</span>
            <span className="text-gray-500">{fmt.date(e.created_at)}</span>
          </div>
          {e.reason && <p className="mt-1 text-gray-700 italic">{e.reason}</p>}
          {e.previous_status !== "none" && e.value_before !== e.value_after && (
            <p className="mt-1 text-amber-700">{t("value_change", { before: num(e.value_before), after: num(e.value_after) })}</p>
          )}
        </li>
      ))}
    </ol>
    </div>
  );
}
