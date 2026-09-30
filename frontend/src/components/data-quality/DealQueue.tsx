"use client";

import React, { useEffect, useState } from "react";
import { useTranslations } from "next-intl";
import type { DealDuplicate, DealListItem, PaginatedResponse } from "@/types";
import { DEAL_STATUSES } from "@/types";
import { getDealQueue, getOpenDealDuplicates } from "@/lib/api";
import { Link } from "@/i18n/navigation";
import { DEAL_PAGE_SIZE } from "@/lib/deals";
import { selectCls } from "@/components/rankings/IndicatorSelect";
import { TableSkeleton } from "@/components/common/LoadingSkeleton";
import { EmptyState, ErrorState } from "@/components/common/EmptyState";
import { Pagination } from "@/components/common/Pagination";
import { DealTable } from "@/components/deals/DealTable";
import { useDealLabels } from "@/components/deals/DealLabels";

type Load<T> = { status: "loading" } | { status: "error" } | { status: "ready"; data: T };

/** Deals tab of the Review Center: deals to decide + open duplicate candidates (never merged automatically). */
export function DealQueue({
  status,
  page,
  onChange,
}: {
  status: string;
  page: number;
  onChange: (updates: Record<string, string | number | null>) => void;
}) {
  const t = useTranslations("data_quality.deals_queue");
  const tStatus = useTranslations("status");
  const tDup = useTranslations("deals.duplicates");
  const labels = useDealLabels();
  const [queue, setQueue] = useState<Load<PaginatedResponse<DealListItem>>>({ status: "loading" });
  const [dups, setDups] = useState<Load<PaginatedResponse<DealDuplicate>>>({ status: "loading" });
  const [reload, setReload] = useState(0);

  useEffect(() => {
    let cancelled = false;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- new request for a new status / page
    setQueue({ status: "loading" });
    getDealQueue({ status, page, page_size: DEAL_PAGE_SIZE })
      .then((data) => !cancelled && setQueue({ status: "ready", data }))
      .catch(() => !cancelled && setQueue({ status: "error" }));
    getOpenDealDuplicates({ page_size: 50 })
      .then((data) => !cancelled && setDups({ status: "ready", data }))
      .catch(() => !cancelled && setDups({ status: "error" }));
    return () => {
      cancelled = true;
    };
  }, [status, page, reload]);

  return (
    <div className="space-y-6" data-testid="dq-deal-queue">
      <section className="space-y-2">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 className="text-sm font-bold text-white">{t("title")}</h2>
          <label className="text-[11px] text-gray-400 font-medium w-56">
            {t("status")}
            <select value={status} onChange={(e) => onChange({ deal_status: e.target.value === "needs_review" ? null : e.target.value, page: null })}
              className={selectCls} data-testid="dq-deal-status">
              {DEAL_STATUSES.map((s) => (
                <option key={s} value={s}>{tStatus.has(s) ? tStatus(s) : s}</option>
              ))}
            </select>
          </label>
        </div>
        {queue.status === "loading" ? (
          <TableSkeleton rows={5} cols={8} />
        ) : queue.status === "error" ? (
          <ErrorState onRetry={() => setReload((n) => n + 1)} />
        ) : queue.data.items.length === 0 ? (
          <EmptyState title={t("empty_title")} description={t("empty_hint")} icon="✅" />
        ) : (
          <>
            <p className="text-xs text-gray-400" data-testid="dq-deal-count">{t("count", { total: queue.data.total })}</p>
            <DealTable items={queue.data.items} hrefFor={(d) => `/data-quality/deals/${d.id}`} />
            <Pagination currentPage={page} pageSize={DEAL_PAGE_SIZE} total={queue.data.total}
              onPageChange={(p) => onChange({ page: p > 1 ? p : null })} />
          </>
        )}
      </section>

      <section className="space-y-2" data-testid="dq-deal-duplicates">
        <h2 className="text-sm font-bold text-white">{t("duplicates_title")}</h2>
        <p className="text-[11px] text-gray-500">{t("duplicates_hint")}</p>
        {dups.status === "loading" ? (
          <TableSkeleton rows={2} cols={3} />
        ) : dups.status === "error" ? (
          <ErrorState onRetry={() => setReload((n) => n + 1)} />
        ) : dups.data.items.length === 0 ? (
          <p className="text-xs text-gray-500">{t("duplicates_empty")}</p>
        ) : (
          <ul className="space-y-2 text-xs">
            {dups.data.items.map((c) => (
              <li key={c.id} className="p-3 rounded-xl border border-amber-800/50 bg-amber-950/20" data-testid="dq-deal-duplicate">
                <span className="font-semibold text-amber-300">{tDup("badge")}</span>{" "}
                <Link href={`/data-quality/deals/${c.other_deal_id}`} className="text-emerald-300 hover:underline">
                  {c.other_deal_title ?? c.other_deal_id}
                </Link>
                <span className="block text-gray-500 mt-1">
                  {tDup("criteria")} {c.matched_criteria.map(labels.criterion).join(" · ")}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
